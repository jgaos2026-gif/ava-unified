# Minimal Reflex Simulator — SIMULATION ONLY / RESEARCH ONLY

Reference implementation of the minimal reflex simulator (milestone 4,
section 7 of the research spec in `SPEC.md`). The spec is the sole
authority for what was built. This is a software-only research
simulation: it simulates synthetic neural-intent frames / sensor packets,
injects controlled software faults, and compares a minimal reflex path
with a full governance path under identical fault campaigns.

## What it is

- **Synthetic frames** — timestamped synthetic frames with an exact
  sequence number, a SHA-256 integrity digest, a source identity, and
  expected bounds.
- **Fault injection** — all eight fault types, each as a named, seeded,
  reproducible injector: bit corruption, stale replay, packet
  reordering, duplicate frames, dropped frames, impossible values,
  delayed responses, conflicting control messages.
- **REFLEX path** — detect → isolate → safe-state fallback → signal.
  It NEVER certifies its own repair. A reflex-only outcome is
  `QUARANTINED` (after a fault) or `PENDING_VERIFICATION` (clean
  pass-through), never `CERTIFIED`.
- **FULL governance path** — evidence → verify → validate → certify,
  before controlled resume or continued quarantine. Quarantine before
  repair. Fail closed: any unverified state stays quarantined; the last
  certified command/state is preserved.
- **Append-only evidence ledger** — every transition and recovery event
  recorded, hash-chained with SHA-256 (each entry links the previous
  entry hash). No silent trust escapes: every promotion decision names
  its evidence.
- **Metrics** — median / p95 / p99 / worst-case software response
  latency; deadline misses at 0.1 / 0.25 / 0.5 / 1 ms (benchmark
  thresholds, NOT clinical requirements); false-positive isolation
  rate; false-negative / silent fault escape rate; rollback
  correctness; evidence completeness; split-brain / conflicting
  safe-state events; CPU, memory, and power cost (wall time + peak RSS
  via the `resource` module; power as an estimate label, never a
  measured claim); deterministic replay of identical fault campaigns
  (same seed → byte-identical canonical metrics output).
- **Compare mode** — `compare_paths()` runs the FULL path vs the REFLEX
  path under the identical campaign (milestone 5's shape, included as a
  comparison function and labeled as such).

## How to run

```bash
cd ~/workspace/your_files/ava-reflex-sim
python3 -m unittest test_reflex_sim -v
python3 demo.py
```

Run the demo twice and compare the output — it must be byte-identical:

```bash
python3 demo.py > /tmp/reflex-demo-1.txt
python3 demo.py > /tmp/reflex-demo-2.txt
cmp /tmp/reflex-demo-1.txt /tmp/reflex-demo-2.txt && echo "identical"
```

Python standard library only. Digests and ledger chaining use
`hashlib.sha256` — never builtin `hash()`. No hardcoded secrets; no
keys/credentials anywhere.

## Success criterion (in the spec's own words)

> A "fast" reflex is not enough. The research win is: lower latency
> without silent unsafe-state escape, without bypassing evidence, and
> without allowing the reflex to certify its own repair.

## Honest limits

- **SIMULATION ONLY / research-only everywhere.** Nothing here is a
  medical device, a treatment, or evidence about a real neural
  interface.
- **NO medical claims** — no seizure prevention, no tissue healing, no
  clinical safety, no implant compatibility.
- **Benchmark thresholds are not clinical requirements.** The 0.1 /
  0.25 / 0.5 / 1 ms deadline thresholds are research benchmarks only.
- **Latency numbers are software-only on this machine**, not
  hardware/neural timing. Canonical latency values are deterministic
  simulated software latencies from the seeded campaign model; real
  wall time and peak RSS are measured separately per run and are
  excluded from the byte-identical canonical output.
- **Power cost is estimated, not measured.** It is an estimate label
  only; no power measurement was made.
- **Single-fault campaigns detect every injected fault; the fixed-seed
  mixed campaign does not.** Injectors interact when combined (a fault
  can overwrite or mask another fault's frame), so the mixed demo
  honestly reports 1 false negative / 1 silent escape out of 24
  injected faults at seed 42 — that escape is recorded in the ledger
  and counted, not hidden.
- The full path shares the reflex's detection check; it adds evidence,
  verification, and certification after isolation — it does not invent
  a second, independent detection pass.
