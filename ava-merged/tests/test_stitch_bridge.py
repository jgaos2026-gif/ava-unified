"""Regression tests for truthful local Stitch bridge semantics.

The bridge is a loopback relay to a local hash-chained room ledger. These
tests ensure that backend liveness is never reported as a peer connection,
ledger integrity is never mislabeled as envelope verification, and an
unsigned relay append is never called certified.
"""
from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from services_stdlib import room_server, stitch_bridge


@pytest.fixture
def live_bridge(tmp_path, monkeypatch):
    room = room_server.create_server(0, str(tmp_path / "room-ledger"))
    room_thread = threading.Thread(target=room.serve_forever, daemon=True)
    room_thread.start()
    room_url = "http://127.0.0.1:%d" % room.server_address[1]
    monkeypatch.setattr(stitch_bridge, "OASIS", room_url)

    bridge = ThreadingHTTPServer(("127.0.0.1", 0), stitch_bridge.H)
    bridge_thread = threading.Thread(target=bridge.serve_forever, daemon=True)
    bridge_thread.start()
    bridge_url = "http://127.0.0.1:%d" % bridge.server_address[1]
    try:
        yield bridge_url, room_url
    finally:
        bridge.shutdown()
        bridge.server_close()
        room.shutdown()
        room.server_close()
        bridge_thread.join(timeout=2)
        room_thread.join(timeout=2)


def request_json(url: str, method: str = "GET", payload=None, headers=None):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers=headers or ({"Content-Type": "application/json"} if data is not None else {}),
        method=method,
    )
    with urllib.request.urlopen(req, timeout=3) as response:
        return response.status, json.loads(response.read().decode("utf-8"))


def test_health_reports_backend_response_not_stitch_connection(live_bridge):
    bridge_url, _ = live_bridge
    status, body = request_json(bridge_url + "/health")
    assert status == 200
    assert body["ok"] is True
    assert body["state"] == "BACKEND_RESPONDING"
    assert body["connection"] == "OFFLINE"
    assert body["certified"] is False


def test_event_reports_uncertified_unsigned_append(live_bridge):
    bridge_url, _ = live_bridge
    status, body = request_json(
        bridge_url + "/event",
        "POST",
        {"event_type": "TEST_EVENT", "payload": {"value": 7}},
    )
    assert status == 200
    assert body["ok"] is True
    assert body["state"] == "APPENDED_UNCERTIFIED"
    assert body["certified"] is False
    assert body["identity_verified"] is False
    assert body["signature_verified"] is False
    assert body["envelope"]["signature_status"] == "UNSIGNED_RELAY"
    assert len(body["evidence_hash"]) == 64


def test_verify_reports_ledger_integrity_not_envelope_verification(live_bridge):
    bridge_url, _ = live_bridge
    status, body = request_json(
        bridge_url + "/verify",
        "POST",
        {"event_type": "VERIFY_REQUEST", "payload": {}},
    )
    assert status == 200
    assert body["ok"] is True
    assert body["ledger_integrity_verified"] is True
    assert body["envelope_verified"] is False
    assert body["verified"] is False
    assert body["certified"] is False
    assert body["state"] == "LEDGER_INTEGRITY_VERIFIED"


def test_replayed_envelope_is_rejected_by_room_ledger(live_bridge):
    bridge_url, room_url = live_bridge
    _, first = request_json(
        bridge_url + "/event",
        "POST",
        {"event_type": "REPLAY_TEST", "payload": {"value": 1}},
    )
    envelope = first["envelope"]
    req = urllib.request.Request(
        room_url + "/api/room/stitchbridge/event",
        data=json.dumps(envelope).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=3) as response:
        appended = json.loads(response.read().decode("utf-8"))
    assert appended["ok"] is True

    with pytest.raises(urllib.error.HTTPError) as exc:
        request_json(
            room_url + "/api/room/stitchbridge/event",
            "POST",
            envelope,
        )
    assert exc.value.code == 422
    refused = json.loads(exc.value.read().decode("utf-8"))
    assert refused["failed_layer"] == "transaction"


def test_cross_origin_browser_post_is_refused(live_bridge):
    bridge_url, _ = live_bridge
    with pytest.raises(urllib.error.HTTPError) as exc:
        request_json(
            bridge_url + "/event",
            "POST",
            {"event_type": "CSRF", "payload": {}},
            headers={
                "Content-Type": "application/json",
                "Origin": "https://attacker.example",
            },
        )
    assert exc.value.code == 403
