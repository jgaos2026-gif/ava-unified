"""ZK-lite signed receipts: prove a rule check ran, without revealing
the private input.

This is NOT a zero-knowledge proof system. A real ZKP proves a
computation followed a circuit, with a proving system and heavy
compute. What this does, honestly, is selective disclosure:
  - the receipt contains ONLY: rule ids checked, verdict, and a
    SHA-256 hash of the private payload -- never the payload itself,
    never a prompt, never pocket contents
  - the receipt is sealed with the identity key
  - a verifier with the key can check: seal valid, rules checked,
    payload hash matches a claimed payload -- without the receipt
    ever having disclosed that payload

That gives the trust benefit John actually needs (prove the check
ran, prove which rules, hide the private context) at stdlib cost.
Claiming full ZK for this would be false, so the module is named
zk-lite, not zk.
"""
import hashlib
import json


def _hash(obj) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def issue_receipt(identity, rule_ids: list, allowed: bool, private_payload) -> dict:
    body = {
        "issuer": identity.id,
        "rules_checked": sorted(rule_ids),
        "verdict": "ALLOWED" if allowed else "DENIED",
        "payload_hash": _hash(private_payload),
        # Deliberately absent: payload, prompt, pocket, sources.
    }
    body["seal"] = identity.sign_obj(body)
    return body


def verify_receipt(identity, receipt: dict, claimed_payload=None) -> tuple[bool, str]:
    body = {k: v for k, v in receipt.items() if k != "seal"}
    if receipt.get("issuer") != identity.id:
        return False, "issuer mismatch"
    if not identity.verify_obj(body, receipt.get("seal", "")):
        return False, "seal invalid -- receipt tampered or wrong key"
    if claimed_payload is not None and _hash(claimed_payload) != receipt["payload_hash"]:
        return False, "payload hash mismatch"
    if "payload" in receipt or "prompt" in receipt:
        return False, "receipt leaks private payload"
    return True, "ok"
