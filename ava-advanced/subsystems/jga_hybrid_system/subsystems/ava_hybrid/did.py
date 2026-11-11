"""Local DID-style identity document.

Honest scope, stated up front: this is a DID *format* document,
resolved locally, signed with the owner's key. It is NOT registered
on any ledger, blockchain, or public DID registry, and it is NOT
interoperable with external DID resolvers until such a registry is
chosen. What it does give, today, is:
  - a stable, portable identifier: did:ava:<identity_id>
  - a signed document binding that id to a verification fingerprint
    and to the Soul Seed, so a second machine can check "is this
    document really Ava's?" without trusting the bearer
  - spoof resistance: a document signed by a different key fails
    verification, and a document claiming a different id fails too

Reputation is NOT included: a DID alone does not create reputation.
That needs a verifier network, which does not exist for Ava yet.
"""
import json


def make_did_document(identity) -> dict:
    doc = {
        "@context": "https://www.w3.org/ns/did/v1",
        "id": f"did:ava:{identity.id}",
        "controller": f"did:ava:{identity.id}",
        "verificationMethod": [{
            "id": f"did:ava:{identity.id}#key-1",
            "type": "HmacSha256Key2026-Prototype",
            "controller": f"did:ava:{identity.id}",
            "publicKeyFingerprint": identity.id,
        }],
        "authentication": [f"did:ava:{identity.id}#key-1"],
        "service": [],  # no public endpoints: local-first, no exposure
        "soul_seed": list(identity.soul_seed),
    }
    doc["proof"] = identity.sign_obj(doc)
    return doc


def resolve_did(identity, document: dict) -> tuple[bool, str]:
    body = {k: v for k, v in document.items() if k != "proof"}
    if document.get("id") != f"did:ava:{identity.id}":
        return False, "did id does not match key holder"
    if document["verificationMethod"][0]["publicKeyFingerprint"] != identity.id:
        return False, "fingerprint mismatch"
    if not identity.verify_obj(body, document.get("proof", "")):
        return False, "proof invalid -- document tampered or wrong key"
    return True, "ok"
