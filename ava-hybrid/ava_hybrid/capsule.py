"""Continuity capsule: how Ava moves machines without forking or drifting.

Export (old machine): pocket snapshot + full ledger + head + revision,
sealed with the identity key. The key itself is NOT in the capsule.

Import (new machine): requires the owner's key file, then checks, in order:
  1. identity_id matches the key
  2. seal verifies with the key
  3. ledger chain verifies (tamper -> reject)
  4. pocket hash matches the snapshot
  5. fork check: if this machine already holds a ledger, the capsule must
     be a descendant of it (same head, or longer chain from the same head)
     -- a divergent head at the same-or-lower revision is a FORK, rejected.
     A fresh machine (empty ledger) accepts any verified capsule.
Any failure -> CapsuleError, nothing imported, nothing merged.
"""
import json
import hashlib


class CapsuleError(Exception):
    pass


def _canon(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()


def export_capsule(identity, memory, ledger) -> dict:
    body = {
        "identity_id": identity.id,
        "name": identity.name,
        "soul_seed": list(identity.soul_seed),
        "pocket": memory.snapshot(),
        "pocket_hash": memory.pocket_hash(),
        "ledger": ledger.to_list(),
        "ledger_head": ledger.head,
        "revision": ledger.revision,
    }
    body["seal"] = identity.sign_obj(body)
    return body


def import_capsule(capsule: dict, identity, memory, ledger):
    body = {k: v for k, v in capsule.items() if k != "seal"}
    if capsule.get("identity_id") != identity.id:
        raise CapsuleError("identity_id does not match key holder")
    if not identity.verify_obj(body, capsule.get("seal", "")):
        raise CapsuleError("seal verification failed -- capsule tampered or wrong key")
    # Ledger chain check (raises on tamper)
    from .ledger import Ledger
    try:
        new_ledger = Ledger.from_list(capsule["ledger"])
    except ValueError as e:
        raise CapsuleError(str(e))
    if new_ledger.head != capsule.get("ledger_head"):
        raise CapsuleError("ledger head mismatch")
    # Pocket check
    from .memory import Memory
    new_memory = Memory.from_snapshot(capsule["pocket"])
    if new_memory.pocket_hash() != capsule.get("pocket_hash"):
        raise CapsuleError("pocket hash mismatch")
    # Fork check against what this machine already holds
    if ledger.revision:
        old_heads = {e["entry_hash"] for e in ledger.entries}
        new_heads = {e["entry_hash"] for e in new_ledger.entries}
        if ledger.head not in new_heads and new_ledger.revision <= ledger.revision:
            raise CapsuleError(
                f"FORK rejected: capsule revision {new_ledger.revision} "
                f"diverges from local head at revision {ledger.revision}")
        if ledger.head not in new_heads and new_ledger.revision > ledger.revision:
            # Longer chain that does not contain local head is still a fork.
            raise CapsuleError("FORK rejected: capsule chain does not contain local head")
    # All checks pass: replace, never merge.
    memory.records = new_memory.records
    ledger.entries = new_ledger.entries
    return {"identity_id": identity.id, "revision": new_ledger.revision,
            "head": new_ledger.head, "records": len(memory.records)}
