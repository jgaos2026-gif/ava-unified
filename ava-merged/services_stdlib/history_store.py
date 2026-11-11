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
is refused with the division named. Scopes are authenticated by signed
scope tokens (services_stdlib/scope_tokens.py): a call that presents a
valid token is reported as `authenticated`; a call with caller-declared
scopes only keeps working but is reported as `declared-untrusted` in
its result. A presented token that does not verify is an identity-layer
refusal, never a silent downgrade. Honest limit: a token authenticates
the KEY HOLDER, not a human — which key belongs to which caller is the
operator's provisioning step (env/keyfile, see scope_tokens.py), not
done here. Until the operator provisions keys, every call is
declared-untrusted and the division boundary is enforced in code only.
"""
import hashlib
import json
import os
import threading
import time

# Signed scope tokens (Finding 12). Optional import, same convention
# as local_organism_core: if the module cannot load, the store still
# runs and every presented token is refused while declared scopes keep
# working as declared-untrusted.
try:
    from services_stdlib import scope_tokens as _scope_tokens
except Exception:  # noqa: BLE001 - plain-import layout fallback
    try:
        import scope_tokens as _scope_tokens
    except Exception:  # noqa: BLE001 - tokens unavailable, fail closed
        _scope_tokens = None

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

    def __init__(self, directory=None, scope_authority=None):
        self.directory = directory or os.environ.get(
            "AVA_HISTORY_DIR", DEFAULT_DIR)
        os.makedirs(self.directory, exist_ok=True)
        self.path = os.path.join(self.directory, "history.jsonl")
        self.quarantine_path = os.path.join(
            self.directory, "history_quarantine.jsonl")
        self.lock = threading.RLock()
        # Scope-token authority for this store. None means "build from
        # the environment on each call" (scope_tokens default); pass an
        # explicit ScopeTokenAuthority to pin keys (tests, embedding).
        self.scope_authority = scope_authority
        # Full-chain verification on mount. If the chain is broken we
        # keep the verified prefix for reads and refuse writes.
        self.chain = self.verify_chain()

    # -- scopes -------------------------------------------------------
    def _resolve_scopes(self, scopes, scope_token):
        """Resolve the effective scopes for one call.
        Returns (effective_scopes, scope_trust, refusal):
          * valid token -> (token scopes, "authenticated", None)
          * invalid token -> (None, "invalid-token", refusal dict)
          * no token -> (declared scopes, "declared-untrusted", None)
        When the scope_tokens module failed to load, any presented
        token is refused (fail closed); declared scopes still work."""
        if scope_token is None:
            return scopes, "declared-untrusted", None
        if _scope_tokens is None:
            return None, "invalid-token", {
                "ok": False, "state": "REFUSED",
                "error": "scope tokens unavailable: scope_tokens module "
                         "not loaded",
                "scope_trust": "invalid-token"}
        return _scope_tokens.resolve_scopes(
            scopes, scope_token, authority=self.scope_authority,
            allowed_scopes=DIVISIONS)

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
               scopes, evidence_hash=None, scope_token=None):
        """Append one history entry. Returns a result dict. Only a
        CERTIFIED entry is stored; anything else is quarantined with
        the failed layer named. `scope_token` (optional) is a signed
        scope token; a valid token reports scope_trust "authenticated",
        declared scopes only report "declared-untrusted", and a
        presented-but-invalid token is an identity-layer refusal.
        The result always carries "scope_trust"."""
        effective_scopes, scope_trust, refusal = self._resolve_scopes(
            scopes, scope_token)
        # ONE clock read for both the entry_id preimage and the entry
        # timestamp (Finding 18): two reads could straddle a second
        # boundary, and then the entry_id would not recompute from the
        # stored timestamp.
        timestamp = time.strftime("%Y-%m-%dT%H:%M:%S")
        entry_id = _sha({
            "thread_id": thread_id, "cycle_id": cycle_id,
            "division": division, "role": role, "text": text,
            "timestamp": timestamp,
        })
        entry = {
            "entry_id": entry_id,
            "timestamp": timestamp,
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
            if refusal is not None:
                self._quarantine(entry, "identity", scopes, scope_trust)
                return {"ok": False, "certified": False,
                        "state": "QUARANTINED", "failed_layer": "identity",
                        "division": division, "scope_trust": scope_trust,
                        "error": refusal["error"]}
            # Re-verify the chain fresh at write time: the cached
            # mount-time result must not authorize a write onto a
            # chain that was modified after mount. The gate's crypto
            # layer refuses when this fresh check fails.
            self.chain = self.verify_chain()
            certified, failed_layer = self.gate(entry, effective_scopes)
            if not certified:
                self._quarantine(entry, failed_layer, scopes, scope_trust)
                return {"ok": False, "certified": False,
                        "state": "QUARANTINED", "failed_layer": failed_layer,
                        "division": division, "scope_trust": scope_trust}
            # Audit layer: the durable append itself.
            try:
                entry["entry_hash"] = _sha(_canonical(entry))
                with open(self.path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(entry, ensure_ascii=False) + "\n")
                    f.flush()
                    os.fsync(f.fileno())
            except Exception as e:  # noqa: BLE001
                self._quarantine(entry, "audit", scopes, scope_trust)
                return {"ok": False, "certified": False,
                        "state": "QUARANTINED", "failed_layer": "audit",
                        "division": division, "scope_trust": scope_trust,
                        "error": str(e)}
            # The post-write re-verification must pass before any
            # success is reported. The entry is already in the file
            # (append-only); a failed re-check means it is reported
            # as failed, never certified, and the broken chain
            # refuses further writes until repaired.
            self.chain = self.verify_chain()
            if not self.chain.get("ok"):
                self._quarantine(entry, "audit", scopes, scope_trust)
                return {"ok": False, "certified": False,
                        "state": "QUARANTINED", "failed_layer": "audit",
                        "division": division, "scope_trust": scope_trust,
                        "chain": self.chain}
            return {"ok": True, "certified": True,
                    "state": "CERTIFIED", "entry_id": entry_id,
                    "entry_hash": entry["entry_hash"],
                    "division": division, "scope_trust": scope_trust}

    def append_existing(self, entry, scopes, scope_token=None):
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
        to the entry as originally formed. `scope_token` is a signed
        scope token; see append(). The result always carries
        "scope_trust"."""
        effective_scopes, scope_trust, refusal = self._resolve_scopes(
            scopes, scope_token)
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
            if refusal is not None:
                self._quarantine(entry, "identity", scopes, scope_trust)
                return {"ok": False, "certified": False,
                        "state": "QUARANTINED", "failed_layer": "identity",
                        "division": entry.get("division"),
                        "scope_trust": scope_trust,
                        "error": refusal["error"]}
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
                    self._quarantine(entry, "crypto", scopes, scope_trust)
                    return {"ok": False, "certified": False,
                            "state": "QUARANTINED", "failed_layer": "crypto",
                            "division": entry.get("division"),
                            "scope_trust": scope_trust}
                stored = {k: v for k, v in entry.items() if k != "entry_hash"}
                if _sha(_canonical(stored)) != given_hash:
                    self._quarantine(entry, "crypto", scopes, scope_trust)
                    return {"ok": False, "certified": False,
                            "state": "QUARANTINED", "failed_layer": "crypto",
                            "division": entry.get("division"),
                            "scope_trust": scope_trust}
            except (KeyError, TypeError):
                self._quarantine(entry, "schema", scopes, scope_trust)
                return {"ok": False, "certified": False,
                        "state": "QUARANTINED", "failed_layer": "schema",
                        "division": entry.get("division"),
                        "scope_trust": scope_trust}
            # Gate against the local chain (identity/schema/braid/
            # transaction; crypto linkage via previous_hash == local head).
            # Re-verify fresh first: the cached mount-time result must
            # not authorize a write onto a chain modified after mount.
            self.chain = self.verify_chain()
            certified, failed_layer = self.gate(entry, effective_scopes)
            if not certified:
                self._quarantine(entry, failed_layer, scopes, scope_trust)
                return {"ok": False, "certified": False,
                        "state": "QUARANTINED", "failed_layer": failed_layer,
                        "division": entry.get("division"),
                        "scope_trust": scope_trust}
            try:
                entry["entry_hash"] = _sha(_canonical(stored))
                with open(self.path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(entry, ensure_ascii=False) + "\n")
                    f.flush()
                    os.fsync(f.fileno())
            except Exception as e:  # noqa: BLE001
                self._quarantine(entry, "audit", scopes, scope_trust)
                return {"ok": False, "certified": False,
                        "state": "QUARANTINED", "failed_layer": "audit",
                        "division": entry.get("division"),
                        "scope_trust": scope_trust, "error": str(e)}
            # The post-write re-verification must pass before any
            # success is reported (same rule as append()).
            self.chain = self.verify_chain()
            if not self.chain.get("ok"):
                self._quarantine(entry, "audit", scopes, scope_trust)
                return {"ok": False, "certified": False,
                        "state": "QUARANTINED", "failed_layer": "audit",
                        "division": entry.get("division"),
                        "scope_trust": scope_trust,
                        "chain": self.chain}
            return {"ok": True, "certified": True,
                    "state": "CERTIFIED", "entry_id": entry["entry_id"],
                    "entry_hash": entry["entry_hash"],
                    "division": entry.get("division"),
                    "scope_trust": scope_trust}

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

    def _quarantine(self, entry, failed_layer, scopes,
                    scope_trust="declared-untrusted"):
        record = dict(entry)
        record["quarantined"] = True
        record["failed_layer"] = failed_layer
        record["scopes_declared"] = scopes
        # The trust of the scopes behind the refused call. The token
        # itself is NEVER recorded here: a valid token is a bearer
        # credential and must not land in a file.
        record["scope_trust"] = scope_trust
        try:
            with open(self.quarantine_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except Exception:
            pass

    # -- read ---------------------------------------------------------
    def recall(self, thread_id=None, cycle_id=None, division=None,
               scopes=None, limit=20, scope_token=None):
        """Recall entries by thread/cycle/division, newest last,
        capped at `limit`. The requested division must be in scope;
        otherwise refused with the division named. The chain is
        re-verified FRESH from disk before serving (Finding 13): the
        cached mount-time result must not authorize serving rows that
        were tampered with after mount. Only the verified prefix is
        served; the chain report in the result names the break.
        `scope_token` is a signed scope token; see append(). The
        result always carries "scope_trust"."""
        effective_scopes, scope_trust, refusal = self._resolve_scopes(
            scopes, scope_token)
        if refusal is not None:
            return dict(refusal, division=division)
        if division is not None and division not in DIVISIONS:
            return {"ok": False, "state": "REFUSED",
                    "error": "unknown division: %s" % division,
                    "division": division, "scope_trust": scope_trust}
        if division is not None:
            if not isinstance(effective_scopes, list) \
                    or division not in effective_scopes:
                return {"ok": False, "state": "REFUSED",
                        "error": "scope for division %s not held" % division,
                        "division": division, "scope_trust": scope_trust}
        try:
            limit = max(1, min(int(limit), 100))
        except Exception:
            limit = 20
        with self.lock:
            # Fresh re-verification from disk at recall time (Finding
            # 13). A row tampered after mount must not be served on
            # the strength of the mount-time check.
            self.chain = self.verify_chain()
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
                "chain": self.chain, "certified": False,
                "scope_trust": scope_trust}

    def divisions(self):
        return {"divisions": list(DIVISIONS),
                "definition": "six BCT strands (Execution, Memory, "
                "Verification, Evidence, Recovery, Governance)",
                "status": "AWAITING_JOHNS_RULING",
                "certified": False}
