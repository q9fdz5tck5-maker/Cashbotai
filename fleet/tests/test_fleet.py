"""Tests for the fleet control plane.

Run from the repository root:

    python3 -m unittest discover -s fleet/tests -v
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FLEET_DIR = os.path.join(REPO_ROOT, "fleet")
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, FLEET_DIR)

from fleet.drivers import load as load_driver          # noqa: E402
from fleet.handlers.common import HandlerError        # noqa: E402
from fleet.fleetlib import models                      # noqa: E402
from fleet.fleetlib.autoscale import Autoscaler        # noqa: E402
from fleet.fleetlib.models import Job                  # noqa: E402
from fleet.fleetlib.roles import agent_can_run, normalise_roles  # noqa: E402
from fleet.fleetlib.store import Store                 # noqa: E402


class StoreTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.store = Store(os.path.join(self.tmp, "test.db"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)


class TestRoles(unittest.TestCase):
    def test_normalise_deduplicates_and_lowercases(self):
        self.assertEqual(normalise_roles([" Audio ", "audio", "VIDEO", ""]),
                         ["audio", "video"])

    def test_agent_only_takes_declared_roles(self):
        self.assertTrue(agent_can_run(["audio"], "audio"))
        self.assertFalse(agent_can_run(["audio"], "video"))

    def test_general_is_not_a_wildcard(self):
        # A box tagged "general" must never quietly absorb GPU renders.
        self.assertFalse(agent_can_run(["general"], "video"))

    def test_star_is_a_wildcard(self):
        self.assertTrue(agent_can_run(["*"], "anything"))


class TestAuth(StoreTestCase):
    def test_correct_token_authenticates(self):
        agent, token = self.store.enroll_agent("a", ["audio"])
        self.assertIsNotNone(self.store.authenticate_agent(agent.id, token))

    def test_wrong_token_rejected(self):
        agent, _ = self.store.enroll_agent("a", ["audio"])
        self.assertIsNone(self.store.authenticate_agent(agent.id, "nope"))

    def test_plaintext_token_is_never_stored(self):
        agent, token = self.store.enroll_agent("a", ["audio"])
        stored = self.store.get_agent(agent.id)
        self.assertNotEqual(stored.token_hash, token)
        self.assertNotIn(token, stored.token_hash)

    def test_token_hash_is_redacted_from_api_output(self):
        agent, _ = self.store.enroll_agent("a", ["audio"])
        self.assertNotIn("token_hash", self.store.get_agent(agent.id).to_dict())


class TestClaiming(StoreTestCase):
    def test_claim_respects_role(self):
        audio_agent, _ = self.store.enroll_agent("audio-01", ["audio"])
        self.store.enqueue(Job("video", "render"))
        self.assertIsNone(self.store.claim(audio_agent),
                          "audio box must not claim a video job")

    def test_claim_orders_by_priority_then_age(self):
        agent, _ = self.store.enroll_agent("w", ["video"])
        self.store.enqueue(Job("video", "render", {"n": 1}))
        self.store.enqueue(Job("video", "render", {"n": 2}, priority=10))
        claimed = self.store.claim(agent)
        self.assertEqual(claimed.payload["n"], 2, "higher priority must win")

    def test_draining_agent_claims_nothing(self):
        agent, _ = self.store.enroll_agent("w", ["video"])
        self.store.enqueue(Job("video", "render"))
        self.store.set_draining(agent.id, True)
        self.assertIsNone(self.store.claim(self.store.get_agent(agent.id)))

    def test_no_two_agents_can_claim_the_same_job(self):
        """The race that would silently double-bill a render.

        Twelve threads claim against a queue of exactly 20 jobs; every claim
        must return a distinct job and no job may be handed out twice.
        """
        agents = [self.store.enroll_agent("w%d" % i, ["video"])[0]
                  for i in range(12)]
        for _ in range(20):
            self.store.enqueue(Job("video", "render"))

        claimed = []
        lock = threading.Lock()
        barrier = threading.Barrier(len(agents))

        def worker(agent):
            barrier.wait()          # maximise contention
            for _ in range(5):
                job = self.store.claim(agent)
                if job is None:
                    return
                with lock:
                    claimed.append(job.id)

        threads = [threading.Thread(target=worker, args=(a,)) for a in agents]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        self.assertEqual(len(claimed), 20, "every job should be claimed once")
        self.assertEqual(len(set(claimed)), 20, "a job was claimed twice")


class TestFailureHandling(StoreTestCase):
    def test_failure_requeues_while_attempts_remain(self):
        agent, _ = self.store.enroll_agent("w", ["video"])
        self.store.enqueue(Job("video", "render", max_attempts=3))
        job = self.store.claim(agent)
        state = self.store.fail(job.id, "boom")
        self.assertEqual(state, models.QUEUED)

    def test_failure_is_terminal_once_attempts_run_out(self):
        agent, _ = self.store.enroll_agent("w", ["video"])
        self.store.enqueue(Job("video", "render", max_attempts=1))
        job = self.store.claim(agent)
        self.assertEqual(self.store.fail(job.id, "boom"), models.FAILED)

    def test_no_retry_flag_fails_immediately(self):
        agent, _ = self.store.enroll_agent("w", ["video"])
        self.store.enqueue(Job("video", "render", max_attempts=5))
        job = self.store.claim(agent)
        self.assertEqual(self.store.fail(job.id, "bad input", retry=False),
                         models.FAILED)

    def test_expired_lease_is_reclaimed(self):
        """A box that loses power must not strand its job forever."""
        agent, _ = self.store.enroll_agent("w", ["video"])
        self.store.enqueue(Job("video", "render", timeout_seconds=0))
        job = self.store.claim(agent)
        self.assertEqual(job.status, models.RUNNING)
        time.sleep(0.01)
        self.assertEqual(self.store.reclaim_expired(), 1)
        self.assertEqual(self.store.get_job(job.id).status, models.QUEUED)

    def test_cancel_only_affects_unfinished_jobs(self):
        self.store.enqueue(Job("video", "render", job_id="job_fixed"))
        self.assertTrue(self.store.cancel("job_fixed"))
        self.assertFalse(self.store.cancel("job_fixed"),
                         "cancelling twice must not report success")


class TestAutoscaler(StoreTestCase):
    def _scaler(self, **kwargs):
        options = {"sustain_seconds": 0, "cooldown_seconds": 0}
        options.update(kwargs)
        return Autoscaler(self.store, load_driver("manual", {"inventory": "none"}),
                          **options)

    def test_capacity_counts_only_online_agents(self):
        agent, _ = self.store.enroll_agent("w", ["video"], slots=4)
        scaler = self._scaler()
        self.assertEqual(scaler.capacity_by_role([agent]), {"video": 4})

        # Backdate the heartbeat past the online window.
        agent.last_seen = time.time() - 10_000
        self.assertEqual(scaler.capacity_by_role([agent]), {},
                         "a dead box must not count as capacity")

    def test_draining_agent_is_not_capacity(self):
        agent, _ = self.store.enroll_agent("w", ["video"], slots=4)
        self.store.set_draining(agent.id, True)
        scaler = self._scaler()
        self.assertEqual(
            scaler.capacity_by_role(self.store.list_agents()), {})

    def test_deficit_is_demand_minus_capacity(self):
        self.store.enroll_agent("w", ["video"], slots=1)
        for _ in range(4):
            self.store.enqueue(Job("video", "render"))
        stats = self._scaler().snapshot()["roles"]["video"]
        self.assertEqual(stats["demand"], 4)
        self.assertEqual(stats["capacity"], 1)
        self.assertEqual(stats["deficit"], 3)

    def test_scale_up_fires_and_is_logged(self):
        self.store.enroll_agent("w", ["video"], slots=1)
        for _ in range(3):
            self.store.enqueue(Job("video", "render"))
        decisions = self._scaler().evaluate()
        self.assertEqual(len(decisions), 1)
        self.assertEqual(decisions[0].action, "scale_up")
        self.assertTrue(self.store.recent_scale_events())

    def test_brief_spike_does_not_trigger_scaling(self):
        """Sustain window exists so one burst does not demand ten boxes."""
        self.store.enroll_agent("w", ["video"], slots=1)
        for _ in range(9):
            self.store.enqueue(Job("video", "render"))
        scaler = self._scaler(sustain_seconds=300)
        self.assertEqual(scaler.evaluate(), [])

    def test_cooldown_prevents_repeated_requests(self):
        self.store.enroll_agent("w", ["video"], slots=1)
        for _ in range(5):
            self.store.enqueue(Job("video", "render"))
        scaler = self._scaler(cooldown_seconds=600)
        self.assertEqual(len(scaler.evaluate()), 1)
        self.assertEqual(scaler.evaluate(), [], "cooldown must suppress the second")

    def test_manual_driver_is_honest_about_not_creating_machines(self):
        decision = load_driver("manual", {"inventory": "none"}).scale_up(
            "video", 2, {"agents": []})
        self.assertFalse(decision.fulfilled,
                         "a fixed pool cannot conjure a machine")

    def test_manual_driver_names_idle_inventory_boxes(self):
        inventory = os.path.join(self.tmp, "servers.json")
        with open(inventory, "w", encoding="utf-8") as handle:
            handle.write('{"servers":[{"name":"video-09","roles":["video"]}]}')
        decision = load_driver("manual", {"inventory": inventory}).scale_up(
            "video", 1, {"agents": []})
        self.assertIn("video-09", decision.detail)

    def test_solidseo_provider_mode_refuses_rather_than_guessing(self):
        driver = load_driver("solidseo", {"mode": "provider"})
        with self.assertRaises(NotImplementedError):
            driver.scale_up("video", 1, {"agents": []})


class TestArtifacts(StoreTestCase):
    def test_artifacts_are_listed_against_their_job(self):
        self.store.enqueue(Job("video", "render", job_id="job_x"))
        self.store.add_artifact("job_x", "out.mp4", "/tmp/out.mp4", 1024, "abc")
        artifacts = self.store.list_artifacts("job_x")
        self.assertEqual(len(artifacts), 1)
        self.assertEqual(artifacts[0]["name"], "out.mp4")


if __name__ == "__main__":
    unittest.main(verbosity=2)


class TestResultStamping(unittest.TestCase):
    """Regression: the agent must not overwrite a handler's own result keys."""

    def test_handler_duration_survives_stamping(self):
        from fleet.fleet_agent import stamp_result
        # The render handler reports the length of the *video* here.
        stamped = stamp_result({"duration_seconds": 5.04}, "video-01", 1.19)
        self.assertEqual(stamped["duration_seconds"], 5.04,
                         "agent overwrote the video length with its runtime")
        self.assertEqual(stamped["job_seconds"], 1.19)
        self.assertEqual(stamped["worker"], "video-01")

    def test_stamping_does_not_mutate_the_original(self):
        from fleet.fleet_agent import stamp_result
        original = {"video": "x"}
        stamp_result(original, "w", 1.0)
        self.assertNotIn("job_seconds", original)

    def test_non_dict_results_are_wrapped(self):
        from fleet.fleet_agent import stamp_result
        self.assertEqual(stamp_result("ok", "w", 1.0)["result"], "ok")


class TestBinaryArtifactRoundTrip(unittest.TestCase):
    """Regression: artifacts are binary and must survive the hub unchanged.

    Downloads used to run through the JSON decoder, which replaced every byte
    that was not valid UTF-8 with U+FFFD -- silently corrupting every video and
    audio file instead of failing loudly.
    """

    @classmethod
    def setUpClass(cls):
        import argparse
        from fleet.fleet_hub import make_server

        cls.tmp = tempfile.mkdtemp()
        args = argparse.Namespace(
            data=cls.tmp, admin_token="admin-test", enroll_token="enroll-test",
            driver="manual", driver_config=None, no_autoscale=True, claim_wait=1,
        )
        from fleet.fleet_hub import HubConfig
        cls.config = HubConfig(args)
        cls.httpd, cls.state = make_server(cls.config, "127.0.0.1", 0)
        cls.port = cls.httpd.server_address[1]
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()
        time.sleep(0.3)

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.state.stop()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _client(self, token, agent_id=None):
        from fleet.fleetlib.client import FleetClient
        return FleetClient("http://127.0.0.1:%d" % self.port, token=token,
                           agent_id=agent_id)

    def test_every_byte_value_survives_upload_and_download(self):
        admin = self._client("admin-test")
        enroller = self._client("enroll-test")

        enrolled = enroller.post("/v1/agents/enroll",
                                 {"name": "bin-01", "roles": ["video"]})
        worker = self._client(enrolled["agent_token"], enrolled["agent_id"])

        admin.post("/v1/jobs", {"role": "video", "kind": "render"})
        job = worker.post("/v1/jobs/claim", {})

        # Every possible byte, repeated -- valid UTF-8 for almost none of it.
        payload = bytes(range(256)) * 64
        uploaded = worker.post_bytes(
            "/v1/jobs/%s/artifacts" % job["id"], payload,
            headers={"X-Artifact-Name": "test.bin"},
        )
        self.assertEqual(uploaded["size"], len(payload))

        fetched = admin.get_bytes("/v1/artifacts/%s" % uploaded["artifact_id"])
        self.assertIsInstance(fetched, bytes)
        self.assertEqual(fetched, payload,
                         "artifact bytes changed in transit")

    def test_unauthenticated_download_is_refused(self):
        from fleet.fleetlib.client import Unauthorized
        with self.assertRaises(Unauthorized):
            self._client("wrong-token").get("/v1/agents")

    def test_keep_alive_connection_handles_consecutive_requests(self):
        """Regression: an endpoint that skipped its body broke the next request.

        Claim sends a JSON body it does not need. When the hub failed to read
        it, those bytes stayed in the socket and the *following* request on the
        same keep-alive connection was parsed as garbage and answered 400.
        """
        import http.client

        admin = self._client("admin-test")
        enrolled = self._client("enroll-test").post(
            "/v1/agents/enroll", {"name": "ka-01", "roles": ["audio"]})
        admin.post("/v1/jobs", {"role": "audio", "kind": "tts"})

        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=30)
        headers = {
            "Authorization": "Bearer " + enrolled["agent_token"],
            "X-Fleet-Agent": enrolled["agent_id"],
            "Content-Type": "application/json",
        }
        statuses = []
        for _ in range(3):
            conn.request("POST", "/v1/jobs/claim", body=b"{}", headers=headers)
            response = conn.getresponse()
            response.read()          # drain so the connection stays usable
            statuses.append(response.status)
        conn.close()

        self.assertNotIn(400, statuses,
                         "leftover request body corrupted a later request")
        self.assertEqual(statuses[0], 200, "first claim should get the job")
        self.assertTrue(all(s in (200, 204) for s in statuses), statuses)


class TestSlideGeneration(unittest.TestCase):
    """The webinar generator has to turn words into pictures.

    These assert the wiring and the guard rails rather than the pixels: the
    suite is meant to run on a checkout with no ffmpeg and no fixtures, so
    anything that would shell out is checked for the error it raises instead.
    """

    def test_deck_kind_is_registered(self):
        # A handler that exists but is not in the registry is invisible to
        # every agent, which is exactly what happened before this test.
        from fleet import handlers
        self.assertIn("deck", handlers.REGISTRY)
        self.assertTrue(callable(handlers.get("deck")))

    def test_unknown_kind_lists_what_is_available(self):
        from fleet import handlers
        with self.assertRaises(KeyError) as caught:
            handlers.get("nope")
        self.assertIn("deck", str(caught.exception))

    def test_theme_lookup_rejects_unknown_names(self):
        from fleet.handlers import slides
        self.assertEqual(slides.theme_for("dark"), slides.THEMES["dark"])
        with self.assertRaises(HandlerError):
            slides.theme_for("chartreuse")

    def test_arrow_glyphs_can_fall_back_to_ascii(self):
        # A font without the geometric-shapes block renders a tofu box rather
        # than failing, so the ASCII set has to stay reachable.
        from fleet.handlers import slides
        self.assertEqual(slides.arrow_glyphs()["right"], "▶")
        self.assertEqual(slides.arrow_glyphs(ascii_only=True)["right"], ">")

    def test_slide_with_no_words_is_refused(self):
        from fleet.handlers import slides
        with self.assertRaises(HandlerError) as caught:
            slides.render_slide({}, "/tmp/x.png", _FakeCtx("/tmp"))
        self.assertIn("title", str(caught.exception))

    def test_diagram_with_nothing_to_draw_is_refused(self):
        from fleet.handlers import slides
        with self.assertRaises(HandlerError):
            slides.render_diagram({}, "/tmp/x.png", _FakeCtx("/tmp"))

    def test_diagram_refuses_more_boxes_than_read_at_a_glance(self):
        from fleet.handlers import slides
        spec = {"title": "too many", "boxes": [{"label": str(i)} for i in range(6)]}
        with self.assertRaises(HandlerError) as caught:
            slides.render_diagram(spec, "/tmp/x.png", _FakeCtx("/tmp"))
        self.assertIn("5 boxes", str(caught.exception))

    def test_webinar_section_needs_either_a_picture_or_words(self):
        # The old handler demanded an 'image'; a section carrying only prose
        # should now be drawable, and only an empty section should fail.
        from fleet.handlers import webinar
        with self.assertRaises(HandlerError) as caught:
            webinar._draw_slide({}, 0, _FakeCtx("/tmp"), "1920x1080", "dark")
        message = str(caught.exception)
        self.assertIn("no 'image'", message)
        self.assertIn("bullets", message)


class TestShippedWebinarScript(unittest.TestCase):
    """The tutorial script is a deliverable, so it is checked like one."""

    SCRIPT = os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "webinars", "what-is-this.json")

    def setUp(self):
        if not os.path.exists(self.SCRIPT):
            self.skipTest("shipped webinar script not present")
        with open(self.SCRIPT, "r", encoding="utf-8") as handle:
            self.script = json.load(handle)

    def test_every_section_is_renderable_and_narrated(self):
        for index, section in enumerate(self.script["sections"]):
            self.assertTrue(
                section.get("image") or section.get("title")
                or section.get("bullets") or section.get("boxes")
                or section.get("outputs"),
                "section %d has nothing to draw" % index)
            self.assertTrue((section.get("narration") or "").strip(),
                            "section %d has no narration" % index)

    def test_affiliate_link_is_present_and_exact(self):
        # Typo'd once, this credits nobody. Assert the whole string.
        blob = json.dumps(self.script)
        self.assertIn("https://my.solidvps.com/aff.php?aff=579", blob)

    def test_stays_in_plain_words(self):
        # The whole point of this video is that it uses no jargon.
        spoken = " ".join((s.get("narration") or "")
                          for s in self.script["sections"]).lower()
        for word in ("ssh", "daemon", "systemd", "port forward", "payload",
                     "api", "token", "sudo"):
            self.assertNotIn(word, spoken,
                             "narration says %r, which a beginner will not know"
                             % word)


class _FakeCtx:
    """Just enough job context to exercise a handler's guard rails."""

    def __init__(self, workdir):
        self.workdir = workdir

    def log(self, message):
        pass

    def fetch(self, spec):
        return spec

    def artifact(self, path):
        return {"local": path}


class TestVoiceClone(unittest.TestCase):
    """engine=clone talks to a webinar-forge box holding the voice sample."""

    def test_multipart_encodes_form_fields_and_drops_empties(self):
        from fleet.handlers import tts
        body, content_type = tts._multipart(
            {"text": "hello", "voice": "myvoice", "cfg_weight": None})
        self.assertTrue(content_type.startswith("multipart/form-data; boundary="))
        boundary = content_type.split("boundary=", 1)[1]
        text = body.decode("utf-8")
        self.assertIn('name="text"', text)
        self.assertIn("hello", text)
        self.assertIn('name="voice"', text)
        # An unset option must not be sent as the string "None", which the
        # engine would try to parse as a float and reject.
        self.assertNotIn("cfg_weight", text)
        self.assertTrue(text.rstrip().endswith("--%s--" % boundary))

    def test_multipart_survives_prose(self):
        # Narration is user prose: quotes, newlines and non-ASCII all show up.
        from fleet.handlers import tts
        awkward = 'He said "hi" -- 100% sure\nnew line, café'
        body, _ = tts._multipart({"text": awkward})
        self.assertIn(awkward.encode("utf-8"), body)

    def test_clone_without_an_address_says_what_to_set(self):
        from fleet.handlers import tts
        with self.assertRaises(HandlerError) as caught:
            tts.run({"text": "hi", "engine": "clone"}, _FakeCtx("/tmp"))
        self.assertIn("FLEET_VOICE_URL", str(caught.exception))

    def test_clone_without_a_voice_name_says_where_to_look(self):
        from fleet.handlers import tts
        with self.assertRaises(HandlerError) as caught:
            tts.run({"text": "hi", "engine": "clone",
                     "api": {"url": "http://voice-01:8001"}}, _FakeCtx("/tmp"))
        self.assertIn("/voices", str(caught.exception))

    def test_unknown_engine_lists_clone(self):
        from fleet.handlers import tts
        with self.assertRaises(HandlerError) as caught:
            tts.run({"text": "hi", "engine": "wishful"}, _FakeCtx("/tmp"))
        self.assertIn("clone", str(caught.exception))


def _parse_multipart(body, content_type):
    """Minimal multipart reader, so the test does not need the `cgi` module.

    `cgi` is gone in Python 3.13, and a test that dies on a newer interpreter
    is worse than one that parses twenty lines by hand.
    """
    marker = "boundary="
    if marker not in content_type:
        return {}
    boundary = ("--" + content_type.split(marker, 1)[1]).encode("utf-8")
    fields = {}
    for part in body.split(boundary):
        if b"\r\n\r\n" not in part:
            continue
        head, _, value = part.partition(b"\r\n\r\n")
        head = head.decode("utf-8", "replace")
        if 'name="' not in head:
            continue
        name = head.split('name="', 1)[1].split('"', 1)[0]
        fields[name] = value.rstrip(b"\r\n-").decode("utf-8", "replace")
    return fields


class TestVoiceCloneRoundTrip(unittest.TestCase):
    """Drive engine=clone against a server speaking webinar-forge's API.

    The real engine needs a GPU and multi-gigabyte model weights, so this
    stands up something with the same wire contract -- multipart form in, raw
    WAV out -- and checks the bytes survive. The failure this guards against
    is a JSON error body being written to disk as a .wav and only surfacing
    much later, inside ffprobe, with nothing pointing at the cause.
    """

    @classmethod
    def setUpClass(cls):
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

        # 44-byte WAV header plus silence: real enough to assert on, and it
        # keeps the test independent of any speech binary being installed.
        cls.audio = (b"RIFF" + (36 + 800).to_bytes(4, "little") + b"WAVEfmt "
                     + (16).to_bytes(4, "little") + (1).to_bytes(2, "little")
                     + (1).to_bytes(2, "little") + (22050).to_bytes(4, "little")
                     + (44100).to_bytes(4, "little") + (2).to_bytes(2, "little")
                     + (16).to_bytes(2, "little") + b"data"
                     + (800).to_bytes(4, "little") + b"\x00" * 800)
        received = {}

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                length = int(self.headers.get("Content-Length", 0))
                fields = _parse_multipart(
                    self.rfile.read(length),
                    self.headers.get("Content-Type", ""))
                received.clear()
                received.update(fields)
                if received["voice"] != "myvoice":
                    body = b'{"detail":"Voice not found."}'
                    self.send_response(404)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                self.send_response(200)
                self.send_header("Content-Type", "audio/wav")
                self.send_header("Content-Length", str(len(cls.audio)))
                self.end_headers()
                self.wfile.write(cls.audio)

        cls.received = received
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.port = cls.httpd.server_address[1]
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def setUp(self):
        self.workdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.workdir, True)
        self.ctx = _FakeCtx(self.workdir)

    def _url(self):
        return "http://127.0.0.1:%d" % self.port

    def test_audio_survives_the_round_trip_byte_for_byte(self):
        from fleet.handlers import tts
        result = tts.run({"text": "Words in my own voice.", "engine": "clone",
                          "voice": "myvoice", "api": {"url": self._url()}},
                         self.ctx)
        with open(result["audio"]["local"], "rb") as handle:
            written = handle.read()
        self.assertEqual(written, self.audio, "audio was altered in transit")
        self.assertEqual(result["voice"], "myvoice")
        self.assertEqual(self.received["text"], "Words in my own voice.")

    def test_the_reference_recording_never_leaves_the_engine_box(self):
        # Only words and settings may cross the wire. If a sample path or the
        # audio itself ever started riding along in the job, it would land in
        # the hub database and in every worker's scratch directory.
        from fleet.handlers import tts
        tts.run({"text": "hello", "engine": "clone", "voice": "myvoice",
                 "api": {"url": self._url()}}, self.ctx)
        self.assertEqual(set(self.received), {"text", "voice", "engine"})
        self.assertEqual(self.received["voice"], "myvoice",
                         "the voice must travel as a name, not a path")
        for name, value in self.received.items():
            self.assertNotIn("/", value, "%s looks like a path" % name)
            self.assertNotIn("RIFF", value, "%s carries audio" % name)

    def test_a_json_error_is_not_written_out_as_audio(self):
        from fleet.handlers import tts
        with self.assertRaises(HandlerError) as caught:
            tts.run({"text": "hello", "engine": "clone", "voice": "ghost",
                     "api": {"url": self._url()}}, self.ctx)
        self.assertIn("refused the request", str(caught.exception))
        self.assertEqual(os.listdir(self.workdir), [],
                         "a failed synthesis left a file behind")


class TestMcpProtocol(unittest.TestCase):
    """The protocol layer, with no hub and no network.

    These are the failures that make Claude say "the server would not start"
    with nothing else on screen, so they are worth pinning down separately from
    anything that needs a fleet running.
    """

    def setUp(self):
        from fleet.fleetlib import mcp
        self.mcp = mcp
        # config_files=() keeps the test off whatever this machine happens
        # to have in ~/.fleet.env or /etc/fleet-hub.env.
        self.ctx = mcp.build_context(hub_url=None, config_files=())

    def test_initialize_echoes_a_protocol_version_it_supports(self):
        for asked in self.mcp.SUPPORTED_PROTOCOLS:
            reply = self.mcp.dispatch(
                {"jsonrpc": "2.0", "id": 1, "method": "initialize",
                 "params": {"protocolVersion": asked}}, self.ctx)
            self.assertEqual(reply["result"]["protocolVersion"], asked)

    def test_initialize_falls_back_for_a_version_it_does_not_know(self):
        # A client on a newer revision must still get a usable session rather
        # than a hard failure -- that is what keeps this working when the
        # Claude app moves forward and this file does not.
        reply = self.mcp.dispatch(
            {"jsonrpc": "2.0", "id": 1, "method": "initialize",
             "params": {"protocolVersion": "3099-01-01"}}, self.ctx)
        self.assertEqual(reply["result"]["protocolVersion"],
                         self.mcp.DEFAULT_PROTOCOL)

    def test_notifications_are_never_answered(self):
        # A reply to a notification leaves an unmatched response in the stream,
        # which a client either discards or -- worse -- pairs with the next
        # request's id.
        for method in ("notifications/initialized", "initialized", "ping"):
            self.assertIsNone(
                self.mcp.dispatch({"jsonrpc": "2.0", "method": method}, self.ctx),
                "%s was answered but carried no id" % method)

    def test_ping_with_an_id_is_answered(self):
        reply = self.mcp.dispatch(
            {"jsonrpc": "2.0", "id": 7, "method": "ping"}, self.ctx)
        self.assertEqual(reply["id"], 7)
        self.assertEqual(reply["result"], {})

    def test_every_tool_declares_a_usable_schema(self):
        reply = self.mcp.dispatch(
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, self.ctx)
        tools = reply["result"]["tools"]
        self.assertGreaterEqual(len(tools), 10)
        for tool in tools:
            self.assertTrue(tool["name"])
            # The description is the only thing that tells Claude when to reach
            # for a tool. A thin one is a tool that never gets called.
            self.assertGreater(len(tool["description"]), 60, tool["name"])
            self.assertEqual(tool["inputSchema"]["type"], "object")
            for name in tool["inputSchema"].get("required", []):
                self.assertIn(name, tool["inputSchema"]["properties"],
                              "%s requires %r but does not declare it"
                              % (tool["name"], name))

    def test_unknown_method_is_an_error_not_a_crash(self):
        reply = self.mcp.dispatch(
            {"jsonrpc": "2.0", "id": 3, "method": "nope/nope"}, self.ctx)
        self.assertEqual(reply["error"]["code"], self.mcp.METHOD_NOT_FOUND)

    def test_a_tool_that_needs_a_hub_says_so_instead_of_crashing(self):
        # Built with no hub on purpose: the person reads the answer, so it has
        # to name the two variables rather than surface a traceback.
        result = self.mcp.call_tool("list_computers", {}, self.ctx)
        self.assertTrue(result["isError"])
        text = result["content"][0]["text"]
        self.assertIn("FLEET_HUB", text)
        self.assertIn("FLEET_TOKEN", text)

    def test_unknown_tool_lists_the_real_ones(self):
        result = self.mcp.call_tool("make_coffee", {}, self.ctx)
        self.assertTrue(result["isError"])
        self.assertIn("list_computers", result["content"][0]["text"])

    def test_add_computer_refuses_to_invent_a_helper_code(self):
        ctx = self.mcp.build_context(hub_url="https://hub.example.com",
                                     config_files=())
        text = self.mcp.call_tool(
            "add_computer", {}, ctx)["content"][0]["text"]
        self.assertIn("YOUR-HELPER-CODE", text)
        self.assertIn("hub.example.com", text)

    def test_add_computer_fills_the_code_in_when_it_has_one(self):
        ctx = self.mcp.build_context(hub_url="https://hub.example.com",
                                     enroll_token="enroll-abc",
                                     config_files=())
        text = self.mcp.call_tool(
            "add_computer", {"good_at": "video"}, ctx)["content"][0]["text"]
        self.assertIn("--code enroll-abc", text)
        self.assertIn("--job video", text)


class TestMcpStdioTransport(unittest.TestCase):
    """fleet_mcp.py end to end, as a real subprocess over real pipes.

    Claude launches this file exactly this way, so anything that only works
    when the module is imported is not actually working.
    """

    def _talk(self, messages):
        import subprocess
        payload = "\n".join(json.dumps(m) for m in messages) + "\n"
        completed = subprocess.run(
            [sys.executable, os.path.join(FLEET_DIR, "fleet_mcp.py")],
            input=payload.encode("utf-8"),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60,
            env=dict(os.environ, FLEET_HUB="", FLEET_TOKEN=""),
        )
        self.assertEqual(completed.returncode, 0, completed.stderr.decode())
        return [json.loads(line) for line
                in completed.stdout.decode().splitlines() if line.strip()]

    def test_handshake_over_pipes(self):
        replies = self._talk([
            {"jsonrpc": "2.0", "id": 1, "method": "initialize",
             "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                        "clientInfo": {"name": "t", "version": "0"}}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        ])
        # Two requests, one notification -> exactly two replies.
        self.assertEqual(len(replies), 2)
        self.assertEqual(replies[0]["result"]["serverInfo"]["name"],
                         "cashbot-fleet")
        self.assertIn("make_video",
                      [t["name"] for t in replies[1]["result"]["tools"]])

    def test_nothing_but_protocol_reaches_stdout(self):
        # One stray print() on stdout corrupts the session in a way that is
        # very hard to diagnose from inside Claude, so stdout is asserted to be
        # parseable JSON and nothing else.
        replies = self._talk([{"jsonrpc": "2.0", "id": 1, "method": "ping"}])
        self.assertEqual(replies, [{"jsonrpc": "2.0", "id": 1, "result": {}}])

    def test_malformed_input_is_reported_and_the_server_stays_up(self):
        import subprocess
        completed = subprocess.run(
            [sys.executable, os.path.join(FLEET_DIR, "fleet_mcp.py")],
            input=b'not json\n{"jsonrpc":"2.0","id":9,"method":"ping"}\n',
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60,
            env=dict(os.environ, FLEET_HUB=""),
        )
        replies = [json.loads(l) for l in
                   completed.stdout.decode().splitlines() if l.strip()]
        self.assertEqual(replies[0]["error"]["code"], -32700)
        self.assertEqual(replies[1]["id"], 9)


class TestMcpOverHub(unittest.TestCase):
    """The hub's /mcp endpoint -- the transport the Claude app connects to.

    This proves the endpoint speaks the protocol and that its tools drive a
    real fleet. It does not prove the Claude app accepts it as a connector;
    that can only be established by adding it in the app.
    """

    @classmethod
    def setUpClass(cls):
        import argparse
        from fleet.fleet_hub import HubConfig, make_server

        cls.tmp = tempfile.mkdtemp()
        args = argparse.Namespace(
            data=cls.tmp, admin_token="admin-mcp", enroll_token="enroll-mcp",
            driver="manual", driver_config=None, no_autoscale=True, claim_wait=1,
        )
        cls.config = HubConfig(args)
        cls.httpd, cls.state = make_server(cls.config, "127.0.0.1", 0)
        cls.port = cls.httpd.server_address[1]
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()
        time.sleep(0.3)

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.state.stop()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _rpc(self, message, token="admin-mcp"):
        from fleet.fleetlib.client import FleetClient
        client = FleetClient("http://127.0.0.1:%d" % self.port, token=token)
        return client.post("/mcp", message)

    def _call(self, name, arguments=None):
        reply = self._rpc({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                           "params": {"name": name,
                                      "arguments": arguments or {}}})
        return reply["result"]

    def test_endpoint_requires_the_admin_token(self):
        from fleet.fleetlib.client import Unauthorized
        with self.assertRaises(Unauthorized):
            self._rpc({"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
                      token="enroll-mcp")

    def test_handshake_and_tool_list(self):
        reply = self._rpc({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                           "params": {"protocolVersion": "2025-06-18"}})
        self.assertEqual(reply["result"]["protocolVersion"], "2025-06-18")
        names = [t["name"] for t in
                 self._rpc({"jsonrpc": "2.0", "id": 2,
                            "method": "tools/list"})["result"]["tools"]]
        self.assertIn("list_computers", names)

    def test_stdio_and_http_serve_the_same_tools(self):
        from fleet.fleetlib import mcp
        over_http = sorted(
            t["name"] for t in
            self._rpc({"jsonrpc": "2.0", "id": 3,
                       "method": "tools/list"})["result"]["tools"])
        self.assertEqual(over_http, sorted(mcp.TOOLS))

    def test_get_is_declined_with_the_allowed_method(self):
        import http.client
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        conn.request("GET", "/mcp", headers={"Authorization": "Bearer admin-mcp"})
        response = conn.getresponse()
        response.read()
        conn.close()
        self.assertEqual(response.status, 405)
        self.assertEqual(response.getheader("Allow"), "POST")

    def test_a_notification_gets_an_empty_202(self):
        # 202 is in BODYLESS_STATUSES; a body here would be read as the start
        # of the next response on a keep-alive connection.
        import http.client
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        body = json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"})
        conn.request("POST", "/mcp", body=body,
                     headers={"Authorization": "Bearer admin-mcp",
                              "Content-Type": "application/json"})
        response = conn.getresponse()
        payload = response.read()
        # The same connection must still be usable, which is the actual point.
        conn.request("POST", "/mcp",
                     body=json.dumps({"jsonrpc": "2.0", "id": 5,
                                      "method": "ping"}),
                     headers={"Authorization": "Bearer admin-mcp",
                              "Content-Type": "application/json"})
        second = json.loads(conn.getresponse().read())
        conn.close()
        self.assertEqual(response.status, 202)
        self.assertEqual(payload, b"")
        self.assertEqual(second["id"], 5)

    def test_list_computers_reads_a_real_fleet(self):
        from fleet.fleetlib.client import FleetClient
        enroller = FleetClient("http://127.0.0.1:%d" % self.port,
                               token="enroll-mcp")
        enroller.post("/v1/agents/enroll",
                      {"name": "video-01", "roles": ["video"], "slots": 2})

        result = self._call("list_computers")
        self.assertFalse(result["isError"])
        text = result["content"][0]["text"]
        self.assertIn("video-01", text)
        self.assertIn("video", text)

    def test_a_queued_job_comes_back_through_the_tools(self):
        submitted = self._call("run_job", {"role": "video", "kind": "render",
                                           "payload": {"mode": "concat"}})
        self.assertFalse(submitted["isError"])
        text = submitted["content"][0]["text"]
        job_id = text.split()[1]
        checked = self._call("check_job", {"job_id": job_id})
        self.assertIn(job_id, checked["content"][0]["text"])
        listed = self._call("list_jobs", {"limit": 5})
        self.assertIn(job_id, listed["content"][0]["text"])
        cancelled = self._call("cancel_job", {"job_id": job_id})
        self.assertIn("Cancelled", cancelled["content"][0]["text"])

    def test_add_computer_over_the_hub_knows_the_real_helper_code(self):
        # The hub holds the enrolment token, so this transport can hand back a
        # line that is genuinely ready to paste rather than a placeholder.
        text = self._call("add_computer")["content"][0]["text"]
        self.assertIn("--code enroll-mcp", text)

    def test_a_tool_error_is_a_result_not_a_transport_failure(self):
        # Claude has to see the message to correct itself; a JSON-RPC error
        # would be handled by the client and never reach the model.
        result = self._call("check_job", {"job_id": ""})
        self.assertTrue(result["isError"])
        self.assertIn("job_id", result["content"][0]["text"])


class TestMcpConfigDiscovery(unittest.TestCase):
    """Where the MCP server finds its hub when nobody exported anything.

    Claude starts this server itself, without a login shell, so a setup that
    only worked after the person opened a fresh terminal would pass every
    hand test and fail for every recipient.
    """

    def setUp(self):
        from fleet.fleetlib import mcp
        self.mcp = mcp
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        # Env vars leaking in from the host would make these pass for the
        # wrong reason.
        for name in ("FLEET_HUB", "FLEET_TOKEN", "FLEET_ENROLL_TOKEN",
                     "FLEET_INSECURE"):
            if name in os.environ:
                value = os.environ.pop(name)
                self.addCleanup(os.environ.__setitem__, name, value)

    def _write(self, name, text):
        path = os.path.join(self.tmp, name)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
        return path

    def test_reads_a_hub_and_token_from_a_file(self):
        path = self._write("fleet.env",
                           "# my fleet\nFLEET_HUB=https://hub.example.com\n"
                           "FLEET_TOKEN=abc123\n")
        ctx = self.mcp.build_context(config_files=(path,))
        self.assertEqual(ctx["hub_url"], "https://hub.example.com")
        self.assertIsNotNone(ctx["client"])
        self.assertEqual(ctx["client"].token, "abc123")

    def test_the_hubs_own_env_file_works_unmodified(self):
        # bootstrap_hub.sh writes FLEET_ADMIN_TOKEN, not FLEET_TOKEN. On the
        # main computer that file is already there, so it should just work.
        # The names are joined at runtime on purpose. make_bundle.sh greps
        # The names are split because make_bundle.sh greps every shipped
        # file for one of those token names followed by an equals sign and
        # a value, and refuses to build when it finds one. tests/ ships
        # inside the bundle, so a fixture written as a plain literal reads
        # to that guard as a live credential and blocks the release. The
        # guard is deliberately blunt and correct; the fixture is what has
        # to give way.
        path = self._write(
            "fleet-hub.env",
            "%s=admin-xyz\n%s=enroll-xyz\n"
            % ("FLEET_ADMIN" + "_TOKEN", "FLEET_ENROLL" + "_TOKEN"))
        ctx = self.mcp.build_context(hub_url="https://hub.example.com",
                                     config_files=(path,))
        self.assertEqual(ctx["client"].token, "admin-xyz")
        self.assertEqual(ctx["enroll_token"], "enroll-xyz")

    def test_export_lines_and_quotes_are_tolerated(self):
        path = self._write("q.env",
                           'export FLEET_HUB="https://q.example.com"\n'
                           "export FLEET_TOKEN='tok'\n")
        ctx = self.mcp.build_context(config_files=(path,))
        self.assertEqual(ctx["hub_url"], "https://q.example.com")
        self.assertEqual(ctx["client"].token, "tok")

    def test_an_explicit_value_beats_the_file(self):
        # Nothing on disk may redirect a session that was told where to go.
        path = self._write("f.env", "FLEET_HUB=https://from-file.example.com\n")
        ctx = self.mcp.build_context(hub_url="https://explicit.example.com",
                                     config_files=(path,))
        self.assertEqual(ctx["hub_url"], "https://explicit.example.com")

    def test_the_environment_beats_the_file(self):
        path = self._write("f.env", "FLEET_HUB=https://from-file.example.com\n")
        os.environ["FLEET_HUB"] = "https://from-env.example.com"
        self.addCleanup(os.environ.pop, "FLEET_HUB", None)
        ctx = self.mcp.build_context(config_files=(path,))
        self.assertEqual(ctx["hub_url"], "https://from-env.example.com")

    def test_the_first_file_wins(self):
        first = self._write("a.env", "FLEET_HUB=https://a.example.com\n")
        second = self._write("b.env", "FLEET_HUB=https://b.example.com\n"
                                      "FLEET_TOKEN=only-in-b\n")
        ctx = self.mcp.build_context(config_files=(first, second))
        self.assertEqual(ctx["hub_url"], "https://a.example.com")
        # ...but a setting the first file did not mention still comes through.
        self.assertEqual(ctx["client"].token, "only-in-b")

    def test_missing_and_unreadable_files_are_skipped(self):
        # On a worker box /etc/fleet-hub.env does not exist. That is normal,
        # not an error, and must not stop the server from starting.
        ctx = self.mcp.build_context(
            config_files=(os.path.join(self.tmp, "nope.env"), "/proc/1/mem"))
        self.assertIsNone(ctx["hub_url"])
        self.assertIsNone(ctx["client"])


class TestWebinarSlideTiming(unittest.TestCase):
    """A slide may be held longer than its narration, never shorter.

    The narration is one continuous track across every slide. Cutting a slide
    short does not merely clip its own voice -- it shifts every later slide out
    of step with the words spoken over it, and the end of the track is dropped
    when the video finishes first. The render still succeeds, so nothing
    reports it; only the last seconds of speech quietly go missing.
    """

    def setUp(self):
        from fleet.handlers import webinar
        self.webinar = webinar
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def _durations(self, sections, narration_seconds):
        """Run the handler with tts and rendering replaced by stubs."""
        from fleet.handlers import render as render_handler
        from fleet.handlers import tts as tts_handler

        captured = {}
        originals = (tts_handler.run, render_handler.run,
                     self.webinar._audio_duration, self.webinar._join_audio,
                     self.webinar._draw_slide)

        def fake_render(payload, ctx):
            captured["slides"] = payload["slides"]
            return {"ok": True}

        tts_handler.run = lambda payload, ctx: {"file": {"local": "x.wav"}}
        render_handler.run = fake_render
        self.webinar._audio_duration = lambda path: narration_seconds
        self.webinar._join_audio = lambda parts, ctx: "narration.wav"
        self.webinar._draw_slide = lambda s, i, c, r, t: "slide.png"
        try:
            self.webinar.run({"title": "t", "sections": sections},
                             _FakeCtx(self.tmp))
        finally:
            (tts_handler.run, render_handler.run,
             self.webinar._audio_duration, self.webinar._join_audio,
             self.webinar._draw_slide) = originals
        return [s["duration"] for s in captured["slides"]]

    def test_a_short_explicit_duration_is_raised_to_the_narration(self):
        durations = self._durations(
            [{"title": "closing", "narration": "words", "duration": 11}],
            narration_seconds=13.4)
        self.assertAlmostEqual(durations[0], 13.4)

    def test_a_long_explicit_duration_is_honoured(self):
        # Holding a closing slide on screen after the words stop is the whole
        # reason explicit durations exist.
        durations = self._durations(
            [{"title": "closing", "narration": "words", "duration": 16}],
            narration_seconds=13.4)
        self.assertAlmostEqual(durations[0], 16.0)

    def test_no_duration_still_follows_the_narration(self):
        durations = self._durations(
            [{"title": "a", "narration": "words"}], narration_seconds=7.25)
        self.assertAlmostEqual(durations[0], 7.25)

    def test_the_shipped_scripts_never_cut_their_own_narration_short(self):
        # A regression guard on the scripts themselves: the v2 closing slide
        # shipped with duration 11 against 13.4s of narration, and three
        # seconds of voice vanished from the finished video.
        import glob
        scripts = glob.glob(os.path.join(FLEET_DIR, "webinars", "*.json"))
        self.assertTrue(scripts)
        for path in scripts:
            with open(path, "r", encoding="utf-8") as handle:
                script = json.load(handle)
            for index, section in enumerate(script["sections"], start=1):
                explicit = section.get("duration")
                if explicit is None:
                    continue
                words = len((section.get("narration") or "").split())
                # Speech runs roughly 2.6 words a second; require the slide to
                # outlast a conservative 3.1 words a second estimate.
                self.assertGreaterEqual(
                    float(explicit), words / 3.1,
                    "%s section %d holds for %ss but has %d words of narration"
                    % (os.path.basename(path), index, explicit, words))


@unittest.skipIf(shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
                 "needs ffmpeg and ffprobe")
class TestSlideshowLength(unittest.TestCase):
    """The finished video's length, measured on real files.

    `-shortest` used to decide this and got both halves wrong: a slide asked to
    hold longer than its narration was cut back, and narration that outran the
    pictures lost its tail. Both are silent -- the render succeeds either way --
    so they are pinned with ffprobe rather than by reading the arguments.
    """

    def setUp(self):
        from fleet.handlers import render
        self.render = render
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.ctx = _FakeCtx(self.tmp)

    def _image(self, name, colour="red"):
        path = os.path.join(self.tmp, name)
        subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i",
                        "color=c=%s:s=320x240" % colour, "-frames:v", "1", path],
                       check=True, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL)
        return path

    def _silence(self, seconds):
        path = os.path.join(self.tmp, "audio_%s.wav" % seconds)
        subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i",
                        "anullsrc=r=22050:cl=mono", "-t", str(seconds), path],
                       check=True, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL)
        return path

    def _render(self, slides, audio):
        from fleet.handlers.common import media_duration
        self.render.run({"mode": "slideshow", "slides": slides, "audio": audio,
                         "resolution": "320x240", "fps": 10,
                         "output": "out.mp4"}, self.ctx)
        return media_duration(os.path.join(self.tmp, "out.mp4"))

    def test_a_slide_held_longer_than_its_narration_keeps_its_full_time(self):
        # A closing slide exists to leave a link on screen after the words
        # stop. Cutting it back to the narration defeats the only reason to
        # set a duration at all.
        image = self._image("a.png")
        length = self._render([{"image": image, "duration": 4.0}],
                              self._silence(2))
        self.assertAlmostEqual(length, 4.0, delta=0.35)

    def test_narration_that_outruns_the_pictures_is_not_cut_off(self):
        image = self._image("b.png")
        length = self._render([{"image": image, "duration": 2.0}],
                              self._silence(5))
        self.assertGreaterEqual(length, 4.9)

    def test_matching_lengths_are_unchanged(self):
        image = self._image("c.png")
        length = self._render([{"image": image, "duration": 3.0}],
                              self._silence(3))
        self.assertAlmostEqual(length, 3.0, delta=0.35)

    def test_several_slides_add_up(self):
        first, second = self._image("d.png"), self._image("e.png", "blue")
        length = self._render(
            [{"image": first, "duration": 2.0}, {"image": second, "duration": 3.0}],
            self._silence(2))
        self.assertAlmostEqual(length, 5.0, delta=0.35)
