"""Scratch prototype: the pulse loop (Step 2 of pulse-spec-v1.md).

A SEPARATE process. It never writes to a main ledger and never holds a
bridge key. Per beat it:
  1. reads the scratch haven's ledger file READ-ONLY,
  2. queries the scratch server (GET only) for /v1/head, /v1/info and
     /v1/verify,
  3. independently recomputes the ledger head from the file (chain,
     content hashes, bridge signatures verified against the public key
     the ledger itself claims in its genesis entry -- the ledger is
     self-describing; any divergence between that key and the server's
     key surfaces through the head comparison and the server audit),
  4. spot-checks ONE pocket seal (round-robin over the haven's pocket
     cache files, recomputing the pocket hash from the cache's own
     fields),
  5. appends ONE pulse-log entry (healthy or failure) and never stamps
     a healthy pulse over a broken state.

Fail-closed rules (spec Step 2 + one documented extension):
- verify failure (server audit not ok) -> failure record, reason
  "verify_failed".
- independent recompute failure -> "recompute_failed".
- sequence backward (reported or recomputed ledger seq below the
  highest previously observed) -> "seq_backward".
- recomputed head != reported head -> "head_drift".
- pocket cache internally inconsistent (recomputed pocket hash !=
  stored pocket hash) -> "pocket_mismatch". This extends the spec's
  fail-closed list by one case, in the fail-closed direction: stamping
  healthy over a mismatched pocket would be a false clean beat.
- Normal head advance on legitimate appends is NOT drift and NOT a
  failure: the beat is healthy as long as audit ok, recompute ok,
  recomputed head == reported head, and no sequence goes backward.
- While broken, the loop keeps observing (one failure record per
  beat) but never stamps a healthy beat, so recovery is observable
  and no clean beat ever covers a broken state. It does not halt on
  the first transient failure: a watchdog that dies on first contact
  with trouble is itself a single point of failure.
- On startup the loop verifies the existing pulse log chain and
  refuses to append over a broken chain or a torn tail (exit 2).
  It also reconciles: the last recorded head must still exist as a
  record hash in the ledger file, else the ledger was replaced or
  rewound under it and the loop refuses to stamp (exit 2).

Ordering note: the loop reads the ledger file BEFORE querying the
server. A concurrent append landing between the file read and the
server query could false-positive a drift. That failure direction is
fail-closed (a spurious failure record, never a false healthy beat),
and the tests run with no concurrent writers. A production loop
would want a server-side atomic snapshot endpoint; that is out of
scope for this prototype and is NOT built here.

SCRATCH ONLY. --base/--root/--log/--key must point at scratch paths.
This file contains no live root, live port, live key path, or bridge
key reference by construction (the no-second-writer test greps for it).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pulse_log import (GENESIS, BrokenLog, TornTail, append_entry, b64d,
                       canon, load_resume_state, load_pulse_private,
                       pulse_public_b64, sha)

GENESIS_HASH = GENESIS


def http_get(base: str, path: str, timeout: float = 5.0):
    req = urllib.request.Request(base.rstrip("/") + path, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def pocket_hash_mirror(ai_id, personality, memories, revision) -> str:
    """Mirrors the v3 pocket-hash definition (bridge.py/util.py) exactly:
    sha(canon({"v": 3, "ai_id", "personality", "memories", "revision"})).
    Validated by the test: a real sealed/registered pocket must match."""
    return sha(canon({"v": 3, "ai_id": ai_id, "personality": personality,
                      "memories": memories, "revision": revision}))


def read_record_hashes(ledger_path: str) -> list:
    hashes = []
    try:
        with open(ledger_path, "rb") as f:
            data = f.read()
    except OSError:
        return hashes
    for raw in data.split(b"\n"):
        if not raw.strip():
            continue
        try:
            rec = json.loads(raw)
            if isinstance(rec.get("hash"), str):
                hashes.append(rec["hash"])
        except ValueError:
            continue
    return hashes


def recompute_ledger(ledger_path: str) -> dict:
    """Independent head recompute from the ledger file, read-only.
    Checks seq order, prev chain, content hashes, and bridge signatures
    against the public key the ledger itself claims in its genesis
    entry payload (BRIDGE_GENESIS carries "pub"). A ledger whose
    genesis key differs from the serving server's key is caught by the
    head comparison (recomputed head != reported head) and by the
    server's own audit, which verifies against the server's key.
    Returns {ok, seq, head, error}."""
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    try:
        with open(ledger_path, "rb") as f:
            data = f.read()
    except OSError as ex:
        return {"ok": False, "seq": None, "head": None, "error": f"unreadable ledger: {ex}"}
    if data and not data.endswith(b"\n"):
        return {"ok": False, "seq": None, "head": None, "error": "ledger_torn_tail"}
    lines = data.split(b"\n")[:-1] if data else []
    if not lines:
        return {"ok": True, "seq": 0, "head": GENESIS_HASH, "error": None}
    try:
        genesis = json.loads(lines[0])
        genesis_pub = genesis["entry"]["payload"]["pub"]
        pub = Ed25519PublicKey.from_public_bytes(b64d(genesis_pub))
    except (ValueError, KeyError, TypeError) as ex:
        return {"ok": False, "seq": None, "head": None,
                "error": f"genesis pubkey unreadable: {ex}"}
    prev = GENESIS_HASH
    for i, raw in enumerate(lines):
        try:
            rec = json.loads(raw)
            e = rec["entry"]
            if e["seq"] != i:
                return {"ok": False, "seq": None, "head": None,
                        "error": f"entry {i}: bad seq {e['seq']}"}
            if e["prev"] != prev:
                return {"ok": False, "seq": None, "head": None,
                        "error": f"entry {i}: chain broken"}
            if sha(canon(e)) != rec["hash"]:
                return {"ok": False, "seq": None, "head": None,
                        "error": f"entry {i}: content hash mismatch"}
            pub.verify(b64d(rec["sig"]), rec["hash"].encode())
            prev = rec["hash"]
        except (ValueError, KeyError, TypeError) as ex:
            return {"ok": False, "seq": None, "head": None,
                    "error": f"entry {i}: malformed ({ex})"}
        except InvalidSignature:
            return {"ok": False, "seq": None, "head": None,
                    "error": f"entry {i}: bridge signature invalid"}
    return {"ok": True, "seq": len(lines), "head": prev, "error": None}


def spotcheck_pocket(root: str, index: int) -> dict:
    """Check ONE pocket cache file (round-robin by index). Returns
    {ai_id, pocket_hash, recomputed, match} or a no-pocket note."""
    pdir = os.path.join(root, "pockets")
    try:
        names = sorted(n for n in os.listdir(pdir) if n.endswith(".json"))
    except OSError:
        names = []
    if not names:
        return {"ai_id": None, "match": None, "note": "no pockets yet"}
    path = os.path.join(pdir, names[index % len(names)])
    try:
        with open(path) as f:
            cache = json.load(f)
        recomputed = pocket_hash_mirror(cache["ai_id"], cache["personality"],
                                         cache["memories"], cache["revision"])
        return {"ai_id": cache["ai_id"], "pocket_hash": cache["pocket_hash"],
                "recomputed": recomputed, "match": recomputed == cache["pocket_hash"]}
    except (OSError, ValueError, KeyError, TypeError) as ex:
        return {"ai_id": None, "match": False, "note": f"unreadable pocket cache: {ex}"}


def ts_display_now() -> str:
    # DISPLAY-ONLY timestamp. Never ordering evidence (see pulse_log.py).
    return datetime.now(timezone.utc).isoformat()


def main() -> int:
    ap = argparse.ArgumentParser(description="Scratch pulse loop (Step 2).")
    ap.add_argument("--base", required=True, help="scratch server base URL")
    ap.add_argument("--root", required=True, help="scratch haven root (read-only use)")
    ap.add_argument("--log", required=True, help="pulse log path (this loop's only write target)")
    ap.add_argument("--key", required=True, help="scratch pulse private key file")
    ap.add_argument("--interval", type=float, default=2.0)
    ap.add_argument("--beats", type=int, default=0, help="0 = run forever")
    a = ap.parse_args()

    priv = load_pulse_private(a.key)
    pub = pulse_public_b64(priv)
    try:
        state = load_resume_state(a.log, pub)
    except (BrokenLog, TornTail) as ex:
        print(f"pulse_loop: refusing to start: {ex}", file=sys.stderr)
        return 2

    ledger_path = os.path.join(a.root, "ledger.jsonl")
    # Startup reconciliation: the last recorded head must still exist
    # in the ledger file, else the ledger was replaced/rewound under us.
    if state["last_entry"] is not None and state["last_good_head"] != GENESIS_HASH:
        hashes = read_record_hashes(ledger_path)
        if state["last_good_head"] not in hashes:
            print("pulse_loop: refusing to start: last recorded head "
                  f"{state['last_good_head'][:16]}... not found in ledger file",
                  file=sys.stderr)
            return 2

    seq = state["last_seq"]
    prev_hash = state["last_hash"]
    last_good_head = state["last_good_head"]
    baseline_seq = None
    beat = 0
    try:
        while True:
            beat += 1
            reason = None
            reported = None
            recomputed = None
            try:
                info = http_get(a.base, "/v1/info")
                reported = info["head"]
                audit = http_get(a.base, "/v1/verify")
            except (urllib.error.URLError, urllib.error.HTTPError, ValueError,
                    KeyError, TimeoutError) as ex:
                reason = f"server_unreachable: {ex}"
                audit = None
                info = None
            if reason is None and not audit.get("ok"):
                reason = f"verify_failed: {audit.get('error', 'audit not ok')}"
            if reason is None:
                recomputed = recompute_ledger(ledger_path)
                if not recomputed["ok"]:
                    reason = f"recompute_failed: {recomputed['error']}"
            if reason is None:
                if baseline_seq is None:
                    baseline_seq = recomputed["seq"]
                if (reported["seq"] < baseline_seq or recomputed["seq"] < baseline_seq):
                    reason = (f"seq_backward: reported={reported['seq']} "
                              f"recomputed={recomputed['seq']} baseline={baseline_seq}")
            if reason is None and recomputed["head"] != reported["hash"]:
                reason = (f"head_drift: recomputed={recomputed['head'][:16]}... "
                          f"reported={reported['hash'][:16]}...")
            healthy = reason is None
            if healthy:
                check = spotcheck_pocket(a.root, beat - 1)
                if check.get("match") is False:
                    healthy = False
                    reason = f"pocket_mismatch: {check}"
                spot = check
                head = reported["hash"]
                baseline_seq = max(baseline_seq, recomputed["seq"], reported["seq"])
            else:
                spot = {"ai_id": None, "match": None, "note": f"skipped: {reason}"}
                head = last_good_head
            fields = {"seq": seq + 1, "ts_display": ts_display_now(),
                      "verify_ok": healthy, "head_hash": head,
                      "pocket_spotcheck": spot}
            entry = append_entry(a.log, fields, prev_hash, priv)
            seq = entry["seq"]
            prev_hash = entry["entry_hash"]
            if healthy:
                last_good_head = head
            print(json.dumps({"beat": beat, "seq": seq, "healthy": healthy,
                              "reason": reason, "head": head[:16] + "..."}),
                  flush=True)
            if a.beats and beat >= a.beats:
                break
            time.sleep(a.interval)
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
