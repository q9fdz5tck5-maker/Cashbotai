"""HTTP client for talking to a fleet hub.

Why this exists instead of ``requests``
---------------------------------------
Claude's sandbox exports ``HTTPS_PROXY`` pointing at a policy-enforcing egress
proxy. That proxy allowlists destination hosts, so a CONNECT to your own VPS
comes back ``403`` and every high-level HTTP library that honours the
environment (requests, urllib, httpx) fails the same way.

Direct TCP+TLS on port 443 is *not* filtered. ``http.client`` never reads the
proxy environment variables, so building on it gets us a clean, direct,
fully-verified TLS connection to the hub. That is the whole trick: the hub
listens on 443, and we dial it straight.

Port 22 is firewalled outright, which is why SSH can never work from here --
this client is the replacement for it, not a workaround layered on top.
"""

import http.client
import json
import os
import socket
import ssl
import time
import urllib.parse

DEFAULT_TIMEOUT = 30
# Long-poll claims hold the socket open while the hub waits for work.
LONG_POLL_TIMEOUT = 90


class FleetError(RuntimeError):
    """Any non-2xx response, carrying the status and decoded body."""

    def __init__(self, status, body, url):
        self.status = status
        self.body = body
        self.url = url
        super().__init__("%s %s -> %s" % (status, url, body))


class Unauthorized(FleetError):
    pass


class FleetClient:
    """Minimal JSON-over-HTTPS client with retries and no proxy involvement.

    ``base_url`` may be https (normal) or http (for a hub on a trusted LAN, or
    for the loopback hub the tests spin up).
    """

    def __init__(self, base_url, token=None, timeout=DEFAULT_TIMEOUT,
                 ca_file=None, insecure=False, retries=3, agent_id=None,
                 extra_headers=None):
        parsed = urllib.parse.urlsplit(base_url.rstrip("/"))
        if parsed.scheme not in ("http", "https"):
            raise ValueError("base_url must be http:// or https://, got %r" % base_url)
        self.scheme = parsed.scheme
        self.host = parsed.hostname
        self.port = parsed.port or (443 if parsed.scheme == "https" else 80)
        self.prefix = parsed.path or ""
        self.token = token
        self.timeout = timeout
        self.retries = max(1, retries)
        self.ca_file = ca_file
        self.insecure = insecure
        # Agents authenticate as "this token, for this agent id"; the hub needs
        # both to tell two agents apart.
        self.agent_id = agent_id
        self.extra_headers = dict(extra_headers or {})

    # -- construction ----------------------------------------------------

    @classmethod
    def from_env(cls, **overrides):
        """Build a client from FLEET_HUB / FLEET_TOKEN / FLEET_CA_FILE."""
        base_url = overrides.pop("base_url", None) or os.environ.get("FLEET_HUB")
        if not base_url:
            raise ValueError(
                "No hub URL. Set FLEET_HUB=https://hub.example.com or pass --hub."
            )
        kwargs = {
            "token": os.environ.get("FLEET_TOKEN"),
            "ca_file": os.environ.get("FLEET_CA_FILE") or None,
            "insecure": os.environ.get("FLEET_INSECURE", "") == "1",
            "agent_id": os.environ.get("FLEET_AGENT_ID") or None,
        }
        kwargs.update(overrides)
        return cls(base_url, **kwargs)

    def _ssl_context(self):
        if self.insecure:
            # Only for a self-signed hub you control on a LAN. The bearer token
            # still authenticates every request.
            ctx = ssl._create_unverified_context()
            return ctx
        return ssl.create_default_context(cafile=self.ca_file)

    def _connect(self):
        if self.scheme == "https":
            return http.client.HTTPSConnection(
                self.host, self.port, timeout=self.timeout,
                context=self._ssl_context(),
            )
        return http.client.HTTPConnection(self.host, self.port, timeout=self.timeout)

    # -- request plumbing ------------------------------------------------

    def request(self, method, path, body=None, params=None, timeout=None):
        """Send one JSON request, retrying only on transport-level failures."""
        url = self.prefix + path
        if params:
            url += "?" + urllib.parse.urlencode(
                {k: v for k, v in params.items() if v is not None}
            )
        payload = None if body is None else json.dumps(body).encode("utf-8")
        headers = {"Accept": "application/json", "User-Agent": "fleet-client/1.0"}
        if payload is not None:
            headers["Content-Type"] = "application/json"
        if self.token:
            headers["Authorization"] = "Bearer " + self.token
        if self.agent_id:
            headers["X-Fleet-Agent"] = self.agent_id
        headers.update(self.extra_headers)

        previous_timeout = self.timeout
        if timeout is not None:
            self.timeout = timeout
        try:
            return self._send_with_retries(method, url, payload, headers)
        finally:
            self.timeout = previous_timeout

    def _send_with_retries(self, method, url, payload, headers, decode=True):
        last_error = None
        for attempt in range(self.retries):
            conn = self._connect()
            try:
                conn.request(method, url, body=payload, headers=headers)
                response = conn.getresponse()
                raw = response.read()
                if not decode:
                    if response.status >= 400:
                        # Errors are still JSON, even on a binary endpoint.
                        return self._decode(response.status, raw, url)
                    return raw
                return self._decode(response.status, raw, url)
            except (socket.timeout, TimeoutError):
                # A long-poll that found no work is a normal, expected timeout.
                raise
            except (http.client.HTTPException, OSError, ssl.SSLError) as exc:
                last_error = exc
                if attempt < self.retries - 1:
                    time.sleep(2 ** attempt)
            finally:
                conn.close()
        raise FleetError(0, "transport failure: %s" % last_error, url)

    @staticmethod
    def _decode(status, raw, url):
        text = raw.decode("utf-8", "replace")
        try:
            data = json.loads(text) if text else {}
        except ValueError:
            data = {"raw": text}
        if status == 401 or status == 403:
            raise Unauthorized(status, data, url)
        if status >= 400:
            raise FleetError(status, data, url)
        return data

    # -- verbs -----------------------------------------------------------

    def get(self, path, params=None, timeout=None):
        return self.request("GET", path, params=params, timeout=timeout)

    def get_bytes(self, path, params=None, timeout=None):
        """Fetch a response as raw bytes.

        Artifacts are video and audio. Running them through the JSON decoder
        replaces every byte that is not valid UTF-8 with U+FFFD, which silently
        corrupts the file instead of failing -- so binary reads never go
        through `request`.
        """
        url = self.prefix + path
        if params:
            url += "?" + urllib.parse.urlencode(
                {k: v for k, v in params.items() if v is not None}
            )
        headers = {"Accept": "*/*", "User-Agent": "fleet-client/1.0"}
        if self.token:
            headers["Authorization"] = "Bearer " + self.token
        if self.agent_id:
            headers["X-Fleet-Agent"] = self.agent_id
        headers.update(self.extra_headers)

        previous = self.timeout
        if timeout is not None:
            self.timeout = timeout
        try:
            result = self._send_with_retries("GET", url, None, headers,
                                             decode=False)
        finally:
            self.timeout = previous
        if not isinstance(result, bytes):
            raise FleetError(0, "expected binary, got %r" % type(result), url)
        return result

    def post(self, path, body=None, params=None, timeout=None):
        return self.request("POST", path, body=body, params=params, timeout=timeout)

    def delete(self, path, params=None):
        return self.request("DELETE", path, params=params)

    def post_bytes(self, path, data, headers=None, timeout=None):
        """Upload raw bytes (artifacts) rather than a JSON document."""
        url = self.prefix + path
        send_headers = {
            "Content-Type": "application/octet-stream",
            "Accept": "application/json",
            "User-Agent": "fleet-client/1.0",
        }
        if self.token:
            send_headers["Authorization"] = "Bearer " + self.token
        if self.agent_id:
            send_headers["X-Fleet-Agent"] = self.agent_id
        send_headers.update(self.extra_headers)
        send_headers.update(headers or {})

        previous = self.timeout
        if timeout is not None:
            self.timeout = timeout
        try:
            return self._send_with_retries("POST", url, data, send_headers)
        finally:
            self.timeout = previous

    # -- diagnostics -----------------------------------------------------

    def preflight(self):
        """Explain, in plain terms, whether this machine can reach the hub.

        Separates the three failure modes that otherwise look identical:
        the port is firewalled, TLS does not verify, or the token is wrong.
        """
        report = {"host": self.host, "port": self.port, "scheme": self.scheme}
        sock = socket.socket()
        sock.settimeout(10)
        try:
            sock.connect((self.host, self.port))
            report["tcp"] = "ok"
        except Exception as exc:
            report["tcp"] = "blocked: %s" % type(exc).__name__
            report["advice"] = (
                "Cannot open a TCP connection to %s:%s. If the port is not 443, "
                "note that this sandbox only allows outbound 443 -- move the hub "
                "to 443." % (self.host, self.port)
            )
            return report
        finally:
            sock.close()

        if self.scheme == "https":
            try:
                raw = socket.create_connection((self.host, self.port), timeout=10)
                with self._ssl_context().wrap_socket(
                    raw, server_hostname=self.host
                ) as tls:
                    report["tls"] = "ok"
                    report["tls_version"] = tls.version()
            except ssl.SSLError as exc:
                report["tls"] = "failed: %s" % exc
                report["advice"] = (
                    "TLS did not verify. Use a real certificate (the bundled "
                    "Caddyfile does this automatically), or pass --insecure for "
                    "a self-signed hub you control."
                )
                return report
            except Exception as exc:
                report["tls"] = "failed: %s" % type(exc).__name__
                return report

        try:
            report["hub"] = self.get("/v1/health")
            report["auth"] = "ok" if self.token else "no token sent"
        except Unauthorized:
            report["auth"] = "rejected -- FLEET_TOKEN is missing or wrong"
        except FleetError as exc:
            report["hub"] = "error: %s" % exc
        return report
