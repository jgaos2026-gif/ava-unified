"""AVA persistent conversation history — WARM JSONL store with hash chain.

Stage: WARM (disk JSONL under services_stdlib/AVA_ORGANISM/WARM/).
HOT is the organism core's in-memory state + HOT/experience.jsonl;
entries move HOT -> WARM here on append (the queryable persistent
layer); WARM -> COLD only through a sealed archive (not built yet);
COLD -> WARM only through verified restore (Phoenix recovery
re-verifies the chain prefix, never self-certifies).

Six-layer BCT gate on EVERY write (identity, schema, crypto, braid,
transaction, audit). A write is stored only when CERTIFIED; otherwise
it is quarantined to history_quarantine.jsonl with the failed layer
named. No silent repair, no self-certification, hashes are not truth
(the chain proves linkage, not that the content is true).

Six divisions — DEFINITION CHOICE, AWAITING JOHN'S RULING:
No division list exists anywhere in the workspace code. The JGA
Enterprise OS zip (~/workspace/user/files/JGA_ENTERPRISE_OS_v0.2.0_48_0zlk.zip,
listed 2026-11-05, 28 files) and ~/workspace/your_files/ava-hybrid/
contain no "division" definition at all. The six divisions below are
therefore defined as the six BCT strands (Execution, Memory,
Verification, Evidence, Recovery, Governance) — the only six-fold
structure in John's canon, from the BCT paper. Do NOT invent any
other division names. If John rules otherwise, replace this list
and re-verify the chain; the list itself is a definition, not a
measured fact.

Access: every history read/write names its division, and the caller
declares the scopes it holds. A caller without that division's scope
is refused with the division named. Honest limit: scopes here are a
DECLARED claim carried in the request, not an authenticated token —
there is no auth token system in this package yet. The scope check
enforces the division boundary in code; it does not prove who the
caller is. Real authenticated scopes are a future step.
"""
import hashlib
import json
import os
import threading
import time

# --- Six divisions (definition choice, AWAITING JOHN'S RULING) ---
DIVISIONS = (
    "EXECUTION",
    "MEMORY",
    "VERIFICATION",
    "EVIDENCE",
    "RECOVERY",
    "GOVERNANCE",
)

ROLES = ("user", "ava", "system")

MAX_TEXT = 100000  # same bound as the organism core's SB688 screen

ROOT = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DIR = os.path.join(ROOT, "AVA_ORGANISM", "WARM")


def _sha(obj):
    if not isinstance(obj, (str, bytes)):
        obj = json.dumps(obj, sort_keys=True, ensure_ascii=False)
    if isinstance(obj, str):
        obj = obj.encode("utf-8")
    return hashlib.sha256(obj).hexdigest()


def _canonical(obj):
    return json.dumps(obj, sort_keys=True, ensure_ascii=False)


class HistoryStore:
    """WARM hash-chained history store. One store = one directory."""

    def __init__(self, directory=None):
        self.directory = directory or os.environ.get(
            "AVA_HISTORY_DIR", DEFAULT_DIR)
        os.makedirs(self.directory, exist_ok=True)
        self.path = os.path.join(self.directory, "history.jsonl")
        self.quarantine_path = os.path.join(
            self.directory, "history_quarantine.jsonl")
        self.lock = threading.RLock()
        # Full-chain verification on mount. If the chain is broken we
        # keep the verified prefix for reads and refuse writes.
        self.chain = self.verify_chain()

    # -- chain ------------------------------------------------------
    def _read_entries(self):
        entries = []
        if not os.path.exists(self.path):
            return entries
        with open(self.path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    entries.append(json.loads(line))
        return entries

    def verify_chain(self):
        """Full-chain verification on mount. Returns a report dict;
        never self-certifies (certified is always False)."""
        if not os.path.exists(self.path):
            return {"ok": True, "entries": 0, "state": "GENESIS",
                    "certified": False}
        previous = "GENESIS"
        count = 0
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    x = json.loads(line)
                    if x.get("previous_hash") != previous:
                        return {"ok": False, "entries": count,
                                "state": "CHAIN_BREAK",
                                "expected": previous,
                                "received": x.get("previous_hash"),
                                "certified": False}
                    claimed = x.get("entry_hash")
                    y = dict(x)
                    y.pop("entry_hash", None)
                    if _sha(_canonical(y)) != claimed:
                        return {"ok": False, "entries": count,
                                "state": "HASH_FAILURE",
                                "certified": False}
                    previous = claimed
                    count += 1
            return {"ok": True, "entries": count,
                    "state": "INTEGRITY_VERIFIED", "certified": False}
        except Exception as e:  # noqa: BLE001 - report, don't raise
            return {"ok": False, "entries": count, "state": "UNRESOLVED",
                    "error": str(e), "certified": False}

    def last_hash(self):
        if not self.chain.get("ok"):
            return self.chain.get("state", "UNRESOLVED")
        entries = self._read_entries()
        if not entries:
            return "GENESIS"
        return entries[-1].get("entry_hash", "GENESIS")

    # -- six-layer gate ---------------------------------------------
    def gate(self, entry, scopes):
        """Returns (certified: bool, failed_layer: str | None).
        Layers, in order: identity, schema, crypto, braid,
        transaction, audit. Audit is checked at write time by the
        caller (append success); here it is the pre-write shape."""
        division = entry.get("division")
        # 1. identity — division known, caller holds its scope.
        if division not in DIVISIONS:
            return False, "identity"
        if not isinstance(scopes, list) or division not in scopes:
            return False, "identity"
        if not isinstance(entry.get("thread_id"), str) or not entry["thread_id"].strip():
            return False, "identity"
        # 2. schema — required fields, types, bounds.
        if entry.get("role") not in ROLES:
            return False, "schema"
        text = entry.get("text")
        if not isinstance(text, str) or not text.strip() or len(text) > MAX_TEXT:
            return False, "schema"
        if "\x00" in text:
            return False, "schema"
        if not isinstance(entry.get("cycle_id"), str) or not entry["cycle_id"].strip():
            return False, "schema"
        # 3. crypto — chain linkage verified fresh at write time
        # (append/append_existing re-verify before calling the gate);
        # a broken chain refuses writes.
        if not self.chain.get("ok"):
            return False, "crypto"
        if entry.get("previous_hash") != self.last_hash():
            return False, "crypto"
        # 4. braid — thread/cycle linkage present (linkage, not a
        # vector similarity claim).
        if not entry.get("thread_id") or not entry.get("cycle_id"):
            return False, "braid"
        # 5. transaction — entry_id unique (idempotent replay rejected).
        entry_id = entry.get("entry_id")
        if not isinstance(entry_id, str) or not entry_id:
            return False, "transaction"
        for existing in self._read_entries():
            if existing.get("entry_id") == entry_id:
                return False, "transaction"
        # 6. audit — pre-write shape only; the durable append is
        # checked by append() itself and reported there.
        return True, None

    # -- write --------------------------------------------------------
    def append(self, thread_id, cycle_id, division, role, text,
               scopes, evidence_hash=None):
        """Append one history entry. Returns a result dict. Only a
        CERTIFIED entry is stored; anything else is quarantined with
        the failed layer named."""
        entry_id = _sha({
            "thread_id": thread_id, "cycle_id": cycle_id,
            "division": division, "role": role, "text": text,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        })
        entry = {
            "entry_id": entry_id,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "thread_id": thread_id,
            "cycle_id": cycle_id,
            "division": division,
            "role": role,
            "text": text,
            "evidence_hash": evidence_hash,
            "trust_state": "PROVISIONAL",
            "self_certified": False,
            "previous_hash": self.last_hash(),
            "stage": "WARM",
        }
        with self.lock:
            # Re-verify the chain fresh at write time: the cached
            # mount-time result must not authorize a write onto a
            # chain that was modified after mount. The gate's crypto
            # layer refuses when this fresh check fails.
            self.chain = self.verify_chain()
            certified, failed_layer = self.gate(entry, scopes)
            if not certified:
                self._quarantine(entry, failed_layer, scopes)
                return {"ok": False, "certified": False,
                        "state": "QUARANTINED", "failed_layer": failed_layer,
                        "division": division}
            # Audit layer: the durable append itself.
            try:
                entry["entry_hash"] = _sha(_canonical(entry))
                with open(self.path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(entry, ensure_ascii=False) + "\n")
                    f.flush()
                    os.fsync(f.fileno())
            except Exception as e:  # noqa: BLE001
                self._quarantine(entry, "audit", scopes)
                return {"ok": False, "certified": False,
                        "state": "QUARANTINED", "failed_layer": "audit",
                        "division": division, "error": str(e)}
            # The post-write re-verification must pass before any
            # success is reported. The entry is already in the file
            # (append-only); a failed re-check means it is reported
            # as failed, never certified, and the broken chain
            # refuses further writes until repaired.
            self.chain = self.verify_chain()
            if not self.chain.get("ok"):
                self._quarantine(entry, "audit", scopes)
                return {"ok": False, "certified": False,
                        "state": "QUARANTINED", "failed_layer": "audit",
                        "division": division, "chain": self.chain}
            return {"ok": True, "certified": True,
                    "state": "CERTIFIED", "entry_id": entry_id,
                    "entry_hash": entry["entry_hash"],
                    "division": division}

    def append_existing(self, entry, scopes):
        """Append a complete, already-formed entry VERBATIM (mirror/sync path).
        Used when an entry already exists in the shared Supabase chain (or in
        another store) and the local store must hold the SAME entry — same
        entry_id, same timestamp, same entry_hash. The gate recomputes BOTH
        hashes from the fields and refuses on mismatch, so a tampered or
        mis-hashed entry can never enter the local chain. Only a CERTIFIED
        entry is stored; anything else is quarantined with the failed layer
        named. Supabase rows arrive with `timestamp_text` instead of
        `timestamp` and extra columns (seq, created_at, source); those are
        normalized away here — the stored local entry holds exactly the
        twelve canonical keys plus entry_hash, byte-identical in content
        to the entry as originally formed."""
        canonical_keys = (
            "entry_id", "timestamp", "thread_id", "cycle_id", "division",
            "role", "text", "evidence_hash", "trust_state",
            "self_certified", "previous_hash", "stage",
        )
        # The incoming hash is verified, never trusted: keep it aside
        # before normalizing (normalization drops it — it is not one of
        # the twelve canonical keys).
        given_hash = entry.get("entry_hash")
        normalized = {}
        for k in canonical_keys:
            normalized[k] = entry.get(k)
        if normalized["timestamp"] is None and entry.get("timestamp_text") is not None:
            normalized["timestamp"] = entry["timestamp_text"]
        if normalized["trust_state"] is None:
            normalized["trust_state"] = "PROVISIONAL"
        if normalized["self_certified"] is None:
            normalized["self_certified"] = False
        if normalized["stage"] is None:
            normalized["stage"] = "WARM"
        entry = normalized
        with self.lock:
            # Crypto layer, full: recompute both hashes from the fields.
            try:
                id_preimage = {
                    "thread_id": entry["thread_id"],
                    "cycle_id": entry["cycle_id"],
                    "division": entry["division"],
                    "role": entry["role"],
                    "text": entry["text"],
                    "timestamp": entry["timestamp"],
                }
                if _sha(_canonical(id_preimage)) != entry.get("entry_id"):
                    self._quarantine(entry, "crypto", scopes)
                    return {"ok": False, "certified": False,
                            "state": "QUARANTINED", "failed_layer": "crypto",
                            "division": entry.get("division")}
                stored = {k: v for k, v in entry.items() if k != "entry_hash"}
                if _sha(_canonical(stored)) != given_hash:
                    self._quarantine(entry, "crypto", scopes)
                    return {"ok": False, "certified": False,
                            "state": "QUARANTINED", "failed_layer": "crypto",
                            "division": entry.get("division")}
            except (KeyError, TypeError):
                self._quarantine(entry, "schema", scopes)
                return {"ok": False, "certified": False,
                        "state": "QUARANTINED", "failed_layer": "schema",
                        "division": entry.get("division")}
            # Gate against the local chain (identity/schema/braid/
            # transaction; crypto linkage via previous_hash == local head).
            # Re-verify fresh first: the cached mount-time result must
            # not authorize a write onto a chain modified after mount.
            self.chain = self.verify_chain()
            certified, failed_layer = self.gate(entry, scopes)
            if not certified:
                self._quarantine(entry, failed_layer, scopes)
                return {"ok": False, "certified": False,
                        "state": "QUARANTINED", "failed_layer": failed_layer,
                        "division": entry.get("division")}
            try:
                entry["entry_hash"] = _sha(_canonical(stored))
                with open(self.path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(entry, ensure_ascii=False) + "\n")
                    f.flush()
                    os.fsync(f.fileno())
            except Exception as e:  # noqa: BLE001
                self._quarantine(entry, "audit", scopes)
                return {"ok": False, "certified": False,
                        "state": "QUARANTINED", "failed_layer": "audit",
                        "division": entry.get("division"), "error": str(e)}
            # The post-write re-verification must pass before any
            # success is reported (same rule as append()).
            self.chain = self.verify_chain()
            if not self.chain.get("ok"):
                self._quarantine(entry, "audit", scopes)
                return {"ok": False, "certified": False,
                        "state": "QUARANTINED", "failed_layer": "audit",
                        "division": entry.get("division"),
                        "chain": self.chain}
            return {"ok": True, "certified": True,
                    "state": "CERTIFIED", "entry_id": entry["entry_id"],
                    "entry_hash": entry["entry_hash"],
                    "division": entry.get("division")}

    def record_reflex_escalation(self, cycle_id, reason, fault_type,
                                  seq=-1, fault_id=""):
        """File a simulation-only reflex escalation through the six-layer
        gate (append -> gate -> store-or-quarantine). The ESCALATION
        RECORD is what the gate certifies as a well-formed record; the
        reflex outcome itself stays QUARANTINED and is never certified
        by this call — the reflex never certifies its own repair.
        Returns the append() result dict."""
        text = (
            "SIMULATION-ONLY reflex escalation (research-only): "
            "reflex isolated cycle %s (reason %s, fault %s, seq %s, "
            "fault_id %s). Trust state QUARANTINED; safe-state fallback "
            "held; full governance review required before any resume. "
            "No medical claim is made." % (
                cycle_id, reason, fault_type, seq, fault_id or "none")
        )
        return self.append(
            thread_id=cycle_id, cycle_id=cycle_id, division="GOVERNANCE",
            role="system", text=text, scopes=["GOVERNANCE"],
            evidence_hash=None)

    def _quarantine(self, entry, failed_layer, scopes):
        record = dict(entry)
        record["quarantined"] = True
        record["failed_layer"] = failed_layer
        record["scopes_declared"] = scopes
        try:
            with open(self.quarantine_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except Exception:
            pass

    # -- read ---------------------------------------------------------
    def recall(self, thread_id=None, cycle_id=None, division=None,
               scopes=None, limit=20):
        """Recall entries by thread/cycle/division, newest last,
        capped at `limit`. The requested division must be in scope;
        otherwise refused with the division named."""
        if division is not None and division not in DIVISIONS:
            return {"ok": False, "state": "REFUSED",
                    "error": "unknown division: %s" % division,
                    "division": division}
        if division is not None:
            if not isinstance(scopes, list) or division not in scopes:
                return {"ok": False, "state": "REFUSED",
                        "error": "scope for division %s not held" % division,
                        "division": division}
        try:
            limit = max(1, min(int(limit), 100))
        except Exception:
            limit = 20
        entries = self._read_entries()
        # Reads return the verified prefix only: stop at the first
        # entry past the verified count when the chain is broken.
        if not self.chain.get("ok"):
            entries = entries[: self.chain.get("entries", 0)]
        out = []
        for e in entries:
            if thread_id is not None and e.get("thread_id") != thread_id:
                continue
            if cycle_id is not None and e.get("cycle_id") != cycle_id:
                continue
            if division is not None and e.get("division") != division:
                continue
            out.append(e)
        return {"ok": True, "entries": out[-limit:],
                "total_matching": len(out),
                "chain": self.chain, "certified": False}

    def divisions(self):
        return {"divisions": list(DIVISIONS),
                "definition": "six BCT strands (Execution, Memory, "
                "Verification, Evidence, Recovery, Governance)",
                "status": "AWAITING_JOHNS_RULING",
                "certified": False}
