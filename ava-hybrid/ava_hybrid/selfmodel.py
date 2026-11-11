"""Read-only self-model: Ava can report its own state, never certify itself.

This is transparency, not consciousness. It answers, from its own
ledger and memory, in numbers a human can check:
  - ledger revision, head, verify status
  - memory counts by state (OBSERVED / VERIFY / VALIDATE / CERTIFY /
    COMMIT / SYNTHESIS) and contradiction links
  - gateway deferral count and reasons (caller supplies the log)
  - pulse seq and pulse verify status
  - emotion influence audit: decisions recorded with their emotion
    must show the same outcome for the same evidence -- if an audit
    ever shows emotion changed a trust decision, that is a fault,
    reported, not hidden

The self-model has NO write path. It cannot edit memory, ledger,
identity, or a decision. A read-only reporter cannot lie to itself
into a new state, because it cannot change state at all.
"""
from dataclasses import dataclass


@dataclass
class SelfState:
    identity_id: str
    ledger_revision: int
    ledger_head: str | None
    ledger_ok: bool
    memory_by_state: dict
    contradiction_links: int
    pulse_seq: int
    pulse_ok: bool
    deferrals: dict
    emotion_audit_ok: bool


def read_self_state(identity, ledger, memory, pulse, deferral_log: list,
                    decision_audit: list) -> SelfState:
    by_state = {}
    links = 0
    for r in memory.records.values():
        by_state[r.state] = by_state.get(r.state, 0) + 1
        links += len(r.contradicts)
    ledger_ok, _ = ledger.verify()
    pulse_ok, _ = pulse.verify()
    deferrals = {}
    for reason in deferral_log:
        deferrals[reason] = deferrals.get(reason, 0) + 1
    # Emotion audit: same evidence must never give different outcomes
    # under different emotions. Entry = (evidence_key, emotion_label, outcome).
    seen = {}
    audit_ok = True
    for evidence_key, _emotion_label, outcome in decision_audit:
        if evidence_key in seen and seen[evidence_key] != outcome:
            audit_ok = False
        seen[evidence_key] = outcome
    return SelfState(
        identity_id=identity.id, ledger_revision=ledger.revision,
        ledger_head=ledger.head, ledger_ok=ledger_ok,
        memory_by_state=by_state, contradiction_links=links // 2,
        pulse_seq=pulse.seq, pulse_ok=pulse_ok,
        deferrals=deferrals, emotion_audit_ok=audit_ok)
