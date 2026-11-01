"""Vercel serverless adapter for the existing JalSuraksha HTTP handler."""

import io
import json
import os
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import server as dam_server  # noqa: E402

STATE_KEY = "jalsuraksha:production-state:v1"


def _redis_command(*parts):
    url = os.environ.get("UPSTASH_REDIS_REST_URL", "").rstrip("/")
    token = os.environ.get("UPSTASH_REDIS_REST_TOKEN", "")
    if not url or not token:
        raise RuntimeError(
            "Persistent storage is not configured. Add UPSTASH_REDIS_REST_URL "
            "and UPSTASH_REDIS_REST_TOKEN in Vercel Project Settings, then redeploy."
        )
    request = urllib.request.Request(
        url,
        data=json.dumps(list(parts), separators=(",", ":")).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=8) as response:
        result = json.loads(response.read().decode("utf-8"))
    if result.get("error"):
        raise RuntimeError(str(result["error"]))
    return result.get("result")


def _load_cloud_state():
    stored = _redis_command("GET", STATE_KEY)
    if not stored:
        return
    state = json.loads(stored)
    if not isinstance(state, dict):
        raise RuntimeError("Stored JalSuraksha state is invalid.")
    dam_server.DAM_DATA.clear()
    dam_server.DAM_DATA.update(state.get("dam", {}))
    dam_server.FARMERS = state.get("farmers", [])
    dam_server.ALERT_LOGS = state.get("alertLogs", [])
    dam_server.ADMIN_SESSIONS = state.get("adminSessions", {})
    dam_server.PUBLIC_REGISTRATION_TIMES = state.get("registrationTimes", {})


def _save_cloud_state():
    state = {
        "dam": dam_server.DAM_DATA,
        "farmers": dam_server.FARMERS,
        "alertLogs": dam_server.ALERT_LOGS,
        "adminSessions": dam_server.ADMIN_SESSIONS,
        "registrationTimes": dam_server.PUBLIC_REGISTRATION_TIMES,
    }
    serialized = json.dumps(state, separators=(",", ":"), ensure_ascii=False)
    _redis_command("SET", STATE_KEY, serialized)


class handler(dam_server.DamAPIHandler):
    """Keep the existing route logic while syncing shared state per request."""

    def _cloud_error(self, error, status=503):
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()
        self.wfile.write(json.dumps({"error": str(error)}).encode("utf-8"))

    def do_GET(self):
        try:
            _load_cloud_state()
        except Exception as error:
            self._cloud_error(error)
            return
        super().do_GET()

    def do_POST(self):
        try:
            _load_cloud_state()
        except Exception as error:
            self._cloud_error(error)
            return

        # Buffer the response until the durable write succeeds, so a failed
        # write cannot be reported to a farmer or operator as a saved change.
        live_stream = self.wfile
        self.wfile = io.BytesIO()
        try:
            super().do_POST()
            response_bytes = self.wfile.getvalue()
            _save_cloud_state()
        except Exception as error:
            self.wfile = io.BytesIO()
            self._cloud_error(error)
            response_bytes = self.wfile.getvalue()
        finally:
            self.wfile = live_stream
        self.connection.sendall(response_bytes)

    def do_OPTIONS(self):
        super().do_OPTIONS()
