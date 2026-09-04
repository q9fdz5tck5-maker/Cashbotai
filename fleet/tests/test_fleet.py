"""Tests for the fleet control plane.

Run from the repository root:

    python3 -m unittest discover -s fleet/tests -v
"""

import os
import shutil
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
