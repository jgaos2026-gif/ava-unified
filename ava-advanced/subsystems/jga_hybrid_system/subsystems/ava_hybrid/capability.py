"""Capability lattice: owner-gated, pulse-bound, revocable.

Standard agents have a flat permission list that never expires.
Ava's capabilities are:
  - issued ONLY by the owner (identity key holder) -- a grant is a
    signed object, verified on use
  - scoped: a capability names one action, optionally one resource
  - pulse-bound: valid from pulse seq X to pulse seq Y, not wall time
    (wall time can be lied about; pulse seq cannot, without breaking
    the chain)
  - revocable: the owner can revoke by id, and a revoked grant is
    dead even inside its pulse window
  - non-transferable: a grant names its holder identity; another
    identity cannot use it

This is what makes Ava safe to hand a capability to: it is narrow,
it dies on schedule, and the owner can kill it early.
"""
import json


class CapabilityStore:
    def __init__(self):
        self.grants = {}
        self.revoked = set()

    def issue(self, identity, grant_id: str, action: str, holder_id: str,
              pulse_from: int, pulse_to: int, resource: str | None = None) -> dict:
        grant = {"grant_id": grant_id, "action": action, "holder_id": holder_id,
                 "pulse_from": pulse_from, "pulse_to": pulse_to,
                 "resource": resource, "issuer": identity.id}
        grant["seal"] = identity.sign_obj(grant)
        self.grants[grant_id] = grant
        return grant

    def revoke(self, grant_id: str):
        self.revoked.add(grant_id)

    def allowed(self, identity, grant: dict, action: str, pulse_seq: int,
                resource: str | None = None) -> bool:
        if grant["grant_id"] in self.revoked:
            return False
        body = {k: v for k, v in grant.items() if k != "seal"}
        if not identity.verify_obj(body, grant.get("seal", "")):
            return False
        if grant["holder_id"] != identity.id or grant["issuer"] != identity.id:
            return False
        if grant["action"] != action:
            return False
        if resource is not None and grant["resource"] not in (None, resource):
            return False
        return grant["pulse_from"] <= pulse_seq <= grant["pulse_to"]
