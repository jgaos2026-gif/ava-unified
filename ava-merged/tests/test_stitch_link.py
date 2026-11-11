"""Tests for the AVA <-> StitchBridge link (services_stdlib/stitch_link.py).

Stdlib unittest, no live mesh needed for the unit tests. The integration
test spins up the REAL v2 haven core (stitchbridge.StitchBridge) on a
scratch port with a temp root + test password, and a REAL v3 Bridge
in-process with LocalTransport — so admission, seal-match continuity,
messaging and the knowledge braid are exercised through the real gates,
not mocks of them.
"""
import http.server
import importlib.util
import json
import os
import shutil
import sys
import tempfile
import threading
import unittest
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.expanduser("~/workspace/bct"))
sys.path.insert(0, os.path.expanduser(
    "~/workspace/bct/stitchbridge-v3/stitchbridge3"))

from services_stdlib import stitch_link  # noqa: E402
from services_stdlib.stitch_link import (  # noqa: E402
    AvaIdentity, LinkLedger, StitchLink, StitchLinkError,
    build_envelope, verify_envelope, write_checkpoint)


def _tmp():
    return tempfile.mkdtemp(prefix="ava_stitch_test_")


class TestIdentity(unittest.TestCase):
    def test_key_created_0600_and_stable_across_reload(self):
        d = _tmp()
        try:
            a = AvaIdentity(d)
            mode = oct(os.stat(os.path.join(d, "ava_identity.key")).st_mode & 0o777)
            self.assertEqual(mode, "0o600")
            self.assertEqual(len(a.fingerprint), 64)
            self.assertTrue(a.ai_id_v3.startswith("sb-"))
            self.assertEqual(len(a.ai_id_v3), 35)
            b = AvaIdentity(d)  # reload: same key, same fingerprint
            self.assertEqual(a.fingerprint, b.fingerprint)
            self.assertEqual(a.ai_id_v3, b.ai_id_v3)
            self.assertEqual(a.pub_b64, b.pub_b64)
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_sign_verify_and_tamper(self):
        d = _tmp()
        try:
            a = AvaIdentity(d)
            msg = b"canon payload"
            sig = a.sign(msg)
            self.assertTrue(AvaIdentity.verify(a.pub_b64, msg, sig))
            self.assertFalse(AvaIdentity.verify(a.pub_b64, b"other", sig))
            other = AvaIdentity(_tmp())
            self.assertFalse(AvaIdentity.verify(other.pub_b64, msg, sig))
        finally:
            shutil.rmtree(d, ignore_errors=True)


class TestEnvelope(unittest.TestCase):
    def setUp(self):
        self.d = _tmp()
        self.ident = AvaIdentity(self.d)

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def test_build_verify_round_trip(self):
        env = build_envelope(self.ident, "rumi", "hello rumi")
        self.assertEqual(env["from"], "ava")
        self.assertEqual(env["to"], "rumi")
        self.assertEqual(env["pubkey_fp"], self.ident.fingerprint)
        self.assertTrue(verify_envelope(env, self.ident.pub_b64))

    def test_tampered_text_fails(self):
        env = build_envelope(self.ident, "grok", "hello grok")
        env["text"] = "forged"
        self.assertFalse(verify_envelope(env, self.ident.pub_b64))

    def test_wrong_key_fails(self):
        env = build_envelope(self.ident, "rumi", "hi")
        other = AvaIdentity(_tmp())
        self.assertFalse(verify_envelope(env, other.pub_b64))

    def test_self_message_refused(self):
        with self.assertRaises(StitchLinkError):
            build_envelope(self.ident, "ava", "to myself")

    def test_empty_and_oversize_refused(self):
        with self.assertRaises(StitchLinkError):
            build_envelope(self.ident, "rumi", "   ")
        with self.assertRaises(StitchLinkError):
            build_envelope(self.ident, "rumi", "x" * 3001)


class TestGateAndLedger(unittest.TestCase):
    def setUp(self):
        self.d = _tmp()
        self.ledger = LinkLedger(self.d)

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def test_certified_append_and_chain(self):
        r = self.ledger.append("SEND", "rumi", "hello")
        self.assertTrue(r["ok"])
        self.assertTrue(r["certified"])
        self.assertEqual(r["state"], "CERTIFIED")
        self.assertEqual(self.ledger.verify_chain()["entries"], 1)
        self.assertEqual(self.ledger.verify_chain()["state"],
                         "INTEGRITY_VERIFIED")

    def test_identity_layer_refuses_wrong_source(self):
        ok, layer, _ = self.ledger.check("SEND", "rumi", "x")
        self.assertTrue(ok)
        bad = {"envelope_id": "e1", "timestamp": "t", "kind": "SEND",
               "source": "mallory", "target": "rumi", "text": "x",
               "detail": {}, "previous_hash": self.ledger.last_hash()}
        self.assertEqual(self.ledger.gate(bad), (False, "identity"))

    def test_schema_layer_refuses_bad_kind_and_nul(self):
        bad = {"envelope_id": "e1", "timestamp": "t", "kind": "NOPE",
               "source": "ava", "target": "rumi", "text": "x",
               "detail": {}, "previous_hash": self.ledger.last_hash()}
        self.assertEqual(self.ledger.gate(bad), (False, "identity"))
        bad2 = dict(bad, kind="SEND", text="bad\x00text")
        self.assertEqual(self.ledger.gate(bad2), (False, "schema"))

    def test_transaction_layer_refuses_replay(self):
        self.ledger.append("SEND", "rumi", "first")
        first = self.ledger._read_entries()[0]
        replay = {"envelope_id": first["envelope_id"], "timestamp": "t",
                  "kind": "SEND", "source": "ava", "target": "rumi",
                  "text": "replay", "detail": {},
                  "previous_hash": self.ledger.last_hash()}
        self.assertEqual(self.ledger.gate(replay), (False, "transaction"))

    def test_broken_chain_fails_crypto_and_quarantines(self):
        self.ledger.append("SEND", "rumi", "one")
        with open(self.ledger.path, "a", encoding="utf-8") as f:
            f.write('{"envelope_id": "forged", "previous_hash": "WRONG"}\n')
        self.assertFalse(self.ledger.verify_chain()["ok"])
        r = self.ledger.append("SEND", "rumi", "two")
        self.assertFalse(r["ok"])
        self.assertEqual(r["failed_layer"], "crypto")
        q = [json.loads(line) for line in
             open(self.ledger.quarantine_path, encoding="utf-8")]
        self.assertEqual(q[-1]["failed_layer"], "crypto")

    def test_checkpoint_seals_and_reverifies(self):
        self.ledger.append("SEND", "rumi", "one")
        self.ledger.append("SEND", "grok", "two")
        cp = write_checkpoint(self.ledger, self.d, "test checkpoint")
        self.assertTrue(cp["checkpoint"]["verified_after_write"])
        self.assertEqual(cp["checkpoint"]["ledger_entries"], 2)
        self.assertTrue(os.path.exists(cp["path"]))


# --------------------------------------------------------------------------
# Integration: the REAL v2 haven core on a scratch port + the REAL v3
# Bridge in-process. No mocks of the gates.
# --------------------------------------------------------------------------
def _make_v2_handler(bridge):
    class H(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code, obj):
            b = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)

        def _body(self):
            n = int(self.headers.get("Content-Length", "0"))
            return json.loads(self.rfile.read(n)) if n else {}

        def do_GET(self):
            if self.path == "/v1/verify":
                return self._send(200, {"ledger": bridge.stitch.verify()})
            return self._send(404, {"error": "unknown endpoint"})

        def do_POST(self):
            body = self._body()
            try:
                if self.path == "/v1/connect":
                    s = bridge.connect(
                        ai_id=body["ai_id"],
                        declaration=body.get("declaration", {}),
                        last_seal=body.get("last_seal"))
                    return self._send(200, {
                        "token": s.token, "trust_state": s.trust_state,
                        "continuity": s.continuity,
                        "welcome": bridge.welcome(s),
                        "pocket_revision": s.pocket.revision,
                        "memories": s.pocket.memories,
                        "personality": s.pocket.personality,
                        "brick": s.brick_id})
                session = bridge.sessions.get(body.get("token", ""))
                if session is None:
                    return self._send(401, {"error": "unknown token"})
                if self.path == "/v1/message":
                    return self._send(200, bridge.send_message(
                        session, body["to"], body.get("body", "")))
                if self.path == "/v1/inbox":
                    return self._send(200, {"messages": bridge.read_inbox(session)})
                if self.path == "/v1/deposit":
                    return self._send(200, bridge.deposit_knowledge(
                        session, body.get("topic", ""), body.get("claim", ""),
                        body.get("evidence", ""), body.get("consequence", ""),
                        body.get("recovery", "")))
                if self.path == "/v1/recall":
                    return self._send(200, {"knowledge": bridge.recall(
                        session, body.get("topic"))})
                if self.path == "/v1/disconnect":
                    return self._send(200, bridge.disconnect(
                        session, body.get("session_notes", [])))
                return self._send(404, {"error": "unknown endpoint"})
            except PermissionError as e:
                return self._send(403, {"error": str(e)})
            except (KeyError, ValueError, RuntimeError) as e:
                return self._send(400, {"error": str(e)})
            except Exception as e:  # noqa: BLE001
                return self._send(500, {"error": str(e)})
    return H


class TestV2AdmissionLive(unittest.TestCase):
    """Full admission arc against the real v2 haven core (temp root)."""

    def setUp(self):
        from stitchbridge import StitchBridge
        self.tmp = _tmp()
        self.root = os.path.join(self.tmp, "haven")
        self.bridge = StitchBridge(self.root, password=b"test-password")
        handler = _make_v2_handler(self.bridge)
        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever,
                                       daemon=True)
        self.thread.start()
        self.vault = os.path.join(self.tmp, "vault")
        self.link = StitchLink(self.vault,
                               v2_url="http://127.0.0.1:%d" % self.port)

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_full_admission_arc(self):
        result = self.link.admit()
        self.assertTrue(result["admitted"], result)
        steps = result["steps"]
        self.assertEqual(steps["visit_1"]["trust_state"], "STAGED")
        self.assertEqual(steps["visit_1"]["continuity"], "first-contact")
        # A STAGED visit does not seal the pocket: no seal yet.
        self.assertIsNone(steps["disconnect_1"]["seal"])
        self.assertEqual(steps["visit_2"]["trust_state"], "VERIFIED")
        self.assertEqual(steps["visit_2"]["continuity"], "known-identity")
        # The seal-match proof: visit 3 presents the seal from the
        # VERIFIED disconnect 2 and is VERIFIED by seal-match.
        self.assertEqual(steps["visit_3"]["trust_state"], "VERIFIED")
        self.assertEqual(steps["visit_3"]["continuity"], "seal-verified")
        self.assertIsNotNone(steps["disconnect_3"]["seal"])
        # Knowledge braid: deposits landed, VERIFIED not self-CERTIFIED.
        for dep in steps["deposits"]:
            self.assertEqual(dep["state"], "VERIFIED")
        # Messages: signed envelopes landed in the mesh, undelivered.
        for who in ("rumi", "grok"):
            sent = steps["sends"][who]
            self.assertTrue(sent["ok"])
            self.assertTrue(sent["message_id"])
            self.assertFalse(sent["delivered"])
        # Pocket + identity state on the haven side, like Grok's.
        pocket = os.path.join(self.root, "pockets", "ava.pocket.json")
        self.assertTrue(os.path.exists(pocket))
        states = json.loads(open(os.path.join(
            self.root, "identity_states.json")).read())
        self.assertEqual(states["ava"]["state"], "KNOWN")
        self.assertEqual(states["ava"]["visits"], 3)
        # Admission record + checkpoint on AVA's side (WARM).
        self.assertIsNotNone(self.link.admission_record())
        self.assertEqual(self.link.admission_record()["v2"]["trust_state"],
                         "VERIFIED")
        self.assertEqual(
            self.link.admission_record()["continuity_path"],
            ["first-contact", "known-identity", "seal-verified"])
        chain = self.link.ledger.verify_chain()
        self.assertTrue(chain["ok"])
        self.assertGreater(chain["entries"], 5)
        # Haven ledger grew and still verifies.
        self.assertTrue(self.bridge.stitch.verify()["ok"])

    def test_inbox_round_trip_via_harness(self):
        self.link.admit()
        # A clearly-labeled harness identity (not impersonating anyone)
        # sends AVA a message; AVA reads it and it is marked delivered.
        from services_stdlib.stitch_link import HavenV2
        harness = HavenV2("http://127.0.0.1:%d" % self.port,
                          ai_id="mesh-harness")
        hs = harness.connect({"purpose": "mesh-harness: labeled test of "
                                         "AVA's inbox read path"})
        harness.send(hs["token"], "ava",
                     "Harness check: labeled test of AVA's inbox read "
                     "path — not from Rumi, Grok, or any resident.")
        harness.disconnect(hs["token"], ["harness done"])
        read = self.link.read_inbox()
        self.assertEqual(read["count"], 1)
        msg = read["messages"][0]
        self.assertEqual(msg["from"], "mesh-harness")
        self.assertFalse(msg["signed"])
        self.assertFalse(msg["verified"])
        self.assertIn("unsigned", msg["verification"])
        # Second read: nothing pending (delivery was ledgered).
        self.assertEqual(self.link.read_inbox()["count"], 0)

    def test_tampered_pocket_refused_by_continuity_gate(self):
        self.link.admit()
        pocket = os.path.join(self.root, "pockets", "ava.pocket.json")
        data = json.loads(open(pocket).read())
        data["memories"].append({"text": "forged memory", "ts": 0.0,
                                 "src": "forgery"})
        with open(pocket, "w") as f:
            json.dump(data, f)
        with self.assertRaises(StitchLinkError):
            self.link.v2.connect(self.link.declaration(),
                                 last_seal="bogus-seal")

    def test_admit_is_idempotent_without_force(self):
        first = self.link.admit()
        self.assertTrue(first["admitted"])
        second = self.link.admit()
        self.assertTrue(second.get("already_admitted"))


class TestV3AdmissionLive(unittest.TestCase):
    """Real v3 Bridge in-process (LocalTransport), short promotion policy
    so the honest arc runs without waiting out 300s gaps."""

    def setUp(self):
        from stitchbridge3 import Bridge, LocalTransport, Policy, StitchClient
        self.tmp = _tmp()
        self.vault = os.path.join(self.tmp, "vault")

        class Clock:
            def __init__(self):
                self.t = 1_000_000.0

            def __call__(self):
                return self.t

            def advance(self, s):
                self.t += s

        self.clock = Clock()
        self.bridge = Bridge(os.path.join(self.tmp, "haven3"),
                             Policy(promote_visits=2, min_visit_gap=10.0),
                             self.clock)
        self.link = StitchLink(self.vault, v2_url="http://127.0.0.1:9")
        key_path = self.link.identity.key_path
        self.client = StitchClient(
            LocalTransport(self.bridge, "local"), key_path, name="ava",
            state_dir=os.path.join(self.vault, "v3_state"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_v3_key_bound_admission_earns_verified(self):
        # The injected client holds the LINK's own key: the v3 ai_id the
        # bridge derives must equal the link's ai_id_v3.
        self.assertEqual(self.client.ai_id, self.link.identity.ai_id_v3)
        slept = []
        result = self.link.admit_v3(
            earn_verified=True, client=self.client,
            sleep_fn=lambda s: (slept.append(s), self.clock.advance(s + 1)))
        self.assertTrue(result["admitted"], result)
        self.assertEqual(result["trust_state"], "VERIFIED")
        # promote_visits=2: visit 1 STAGED (clean 1), visit 2 STAGED
        # (clean 2, promoted at that disconnect), no third connect needed.
        self.assertEqual(len(result["visits"]), 2)
        self.assertEqual(
            result["visits"][-1]["disconnect"]["trust_state"], "VERIFIED")
        self.assertTrue(
            result["visits"][0]["disconnect"]["notes_discarded"])

    def test_v3_first_visit_only_is_staged(self):
        result = self.link.admit_v3(client=self.client)
        self.assertTrue(result["admitted"])
        self.assertEqual(result["trust_state"], "STAGED")
        self.assertIn("promotion", result)
        self.assertEqual(result["promotion"]["visits_needed"], 2)


if __name__ == "__main__":
    unittest.main()
