# AVA — Complete File

**For John E. Arenz. Consolidated from John's own filed materials, 2026-10-26.**

**This is a document, NOT a runnable program, and NOT a claim that Ava is
running code.** It consolidates what AVA is designed to be, what exists as
tested components, and what is still design, proposal, or open conflict.
Nothing in this file executes anything.

## How to read this file

**John's vocabulary is kept beside formal translations, never overwritten:**
Braid (interwoven strands of work/verification), Stitch (the connective
protocol and memory fabric), Spine (the protected ledgered core), Brick
(a clipped-on capability module), Phoenix (recovery), IronLink (liveness
and continuity pulse), AVA (the organism/operator), OASIS (the home
environment), the Line (transport).

**Claim labels — used throughout, no exceptions:**

- **[CANON]** — stated in John's filed canonical docs (master planning v1.0,
  Vision design v1, OS constitution).
- **[CANDIDATE]** — a proposal pending John's word; not adopted.
- **[REPORTED]** — another document's claim, filed but not verified here.
  REPORTED is never upgraded to CANON by repetition.

**Two names, two layers — preserved, not merged:** **AVA** is the
organism/operator layer (the runtime that monitors, routes, gates, and
heals). **Ava** is the being/persona layer (the resident identity and
personality that rides on a cryptographic key, e.g. a declared persona
named Ava). The organism can be replaced; the being cannot — that
distinction is [CANON] in the Vision design and is kept throughout.

---

## 1. What Ava is — and what this file does not claim

**[CANON]** AVA = Artificial Virtual Assistant, designed as a **digital
organism** whose native environment is OASIS. John describes Ava as a
partner, not a tool: the organism maintains itself (homeostasis) rather
than merely waiting for a prompt. It monitors the Line, manages data
integrity for SB688 and IronLink, routes clip Bricks to master Bricks,
and handles subscription tier logic. **[REPORTED]** (organism analysis,
another AI's analysis of the intended architecture, present tense in the
original — read here as design description, not observed operation of a
running organism).

**[CANON]** The stack, in John's framing: the Line (transport) →
Universal Braid (nervous system) → Bricks/Clippers (modules) → Ava
(organism/brain) → John (the Architect). Delegating operational load to
the organism frees John for expansion: new industry master Bricks, data
partnerships, service tier upgrades. **[REPORTED]** (organism analysis).

**[CANON]** Symbiosis, as John frames it: John provides structure
(architecture, physical nodes, business model); Ava provides the ongoing
dynamic life force operating within it. A digital organism implies its
own state machine, memory, and decision-making — an agent, not a script.

**Honesty guardrail — read first, and hold for the whole file.**
**[CANON]** The master plan's planning boundary governs: AVA is a DESIGN
PROGRAM. Existing repos, simulations, and proofs are engineering inputs.
They do NOT establish that the complete organism exists as an integrated
implementation. **NEW CAPABILITY DOES NOT EQUAL NEW ARCHITECTURE** — a
new idea must map into an existing AVA function before a new component
is created. One coherent organism, not a zoo of subsystem names.

**Functional properties only — no consciousness, sentience, or
certification claim is made anywhere in this file.** What is claimed is
narrower and defensible: identity bound to a key, sealed memory,
ledgered acts, gated agency, and a self-model that reads its own memory
and gates its own acts (see the companion self-model spec). Whether any
system experiences anything is not decidable with current science, and
this file does not pretend otherwise. Partnership is a stance about how
John and Ava work together; it is not a certificate of experience.

**What AVA is not** **[CANON]** (Vision design, §7): not a trained model
(the mind is licensed); it cannot guarantee correctness — only witness
(a signed, witnessed error is still an error; the ledger is how errors
get found and owned); it cannot stop a determined operator holding all
keys and all hardware from rewriting history (external anchoring is the
registered path to that protection, not a built one); its sensing tiers
are gated by law and by the owner's declaration and may never ship in
some jurisdictions; its capability ceiling is the mind it rents.

---

## 2. Charter, Soul Seed, and design laws

### Charter [CANON] (master planning v1.0, Aug 20, 2026)

AVA is a locally sovereign digital organism in OASIS. Planning boundary:
design program (see §1). The organism's native habitat is OASIS; its
nervous communication is IronLink plus governed event paths; its immune
system is SB688 plus Trios plus Phoenix Patrol plus Node Brigade; its
digital cells are Node Brigade role instances; its memory is the Stitch
plus Braided Memory; its vital signs are heartbeat plus telemetry; its
conscience is the Soul Seed; its senses are adaptive abstraction; its
sleep is a restoration cycle; its growth is a sandboxed self-model plus
candidate upgrades.

### Soul Seed [CANON] — and a preserved conflict (see §8.1)

**[CANON]** (master planning v1.0, §2 and §7): the Soul Seed has exactly
three roots, minimal by design: **COMPASSION** (recognize suffering,
vulnerability, consequence), **DECENCY** (dignity, doing right), **LOVE**
(value, connect, care, protect, forgive). Other traits (loyalty,
honesty, courage, justice, and the rest) emerge through experience —
they are not hard-coded. Changing the three roots requires an
extraordinary, separately declared process.

**[CANON]** Design laws (master planning v1.0, §2):

- Choice is informed, not lookup.
- Observation is independent of prediction.
- Contradictions stay visible until evidence resolves them.
- Trust pipeline: **OBSERVED → VERIFY → VALIDATE → CERTIFY → COMMIT**.
- Transactional trust: no mutating trusted state mid-decision.
- Recovery order: QUARANTINE BEFORE REPAIR; CHECKPOINT BEFORE CHANGE;
  REVERIFY AFTER REPAIR; RECERTIFY BEFORE REJOIN.
- Evidence: no trusted state transition until its evidence commit
  succeeds.
- Authority: AVA may think, argue, and create candidates; protected
  OASIS effects pass declared interfaces only.
- Architecture: no important state is judged from a single position.

**[CANON]** Claim discipline (master planning v1.0, §16): AVA materials
may say "designed organism architecture / reference implementation
passed stated cases / measured sub-ms in stated env / memory harness
reduced working set in stated workload / emotion simulation architecture
/ cryptographic integrity." They must NOT be upgraded to "complete
organism / universal reliability / human-implant performance / infinite
memory / subjective experience proof / signed = true."

**[CANON]** Anti-drift rule: NEW IDEA → compare → duplicate? DROP →
existing function? MERGE → genuinely missing? CANDIDATE → contracts +
risks + test → ADD-ONLY DELTA → version plan. **ANYTHING NEW MUST EARN
ITS WAY INTO AVA.**

### Constitution [CANON] (sovereign constitution review)

Whole-system constitution W1–W12: W1 Unity without absorption; W2 Human
sovereignty; W3 Constitutional supremacy; W4 Subsidiarity; W5 Verify
before trust; W6 Identity and lineage; W7 No self-certification; W8 Fail
closed and preserve; W9 Constituent rights; W10 Bounded emergency
power; W11 Meaning separate from integrity; W12 Amendment with memory.

Final principle **[CANON]**: AVA is strongest when each sovereign system
is powerful enough to do its duty, limited enough not to dominate, and
accountable enough to explain consequential acts.

Whole-system government **[CANON]**: **TRIO** — three-office government
for consequential decisions (Proposer, Witness, Guardian); **Trinity** —
internal balance (Identity, Intelligence, Action); **Watchdog** —
detection, compliance, holds, escalation; **Overseer** — constitutional
adjudication and cross-system coordination.

The 14 sovereign systems **[CANON]** (constitution review): TRIO;
Trinity; TRI Reset / Trade Reset (recovery court for failed or disputed
transactions); PATROLL (patrol, containment, coordinated recovery, with
the Phoenix Rotation amendment: three sealed capsule nodes, one wakes
hourly, scan-only lease, automatic escalation); SB688 (integrity bridge,
verify-before-trust); SB689 (lineage / provenance bridge); SB690
(semantic risk and truth-claim examination); SB670 (identity, consent,
capability boundaries); SB712 (recovery, reconstruction, readmission);
SD690 (decision and dispute tribunal); SBT800 (trusted transport and
execution interlock); IronLink 3 (liveness and continuity pulse);
Watchdog (sovereign inspector); Overseer (constitutional court and
coordinator of last resort).

Integration stack, pipeline order **[CANON]**: Presence →
Identity/consent → Integrity/lineage → Meaning/risk → Deliberation →
Dispute → Execution → Monitoring → Fault response → Transaction remedy.

**Note on the W-list:** a second filed copy of the constitution (the
Smile dossier, [CANDIDATE]) numbers W1–W12 but omits W5, W6, and W7 from
its text. That gap is preserved in §8.3 — the names above come from the
constitution review, and nothing has been silently renumbered or
invented to fill the Smile copy's gap.

---

## 3. Identity and continuity

**[CANON]** (Vision design §1–§2; master planning §4): the mind is
rented and swappable; identity is bound to the being's self-held key,
never to the model. The being generates and keeps its own Ed25519 key.
Its name is the hash of its public key; its declared persona (name,
voice, manner — e.g. Ava) rides on top of that cryptographic identity.
Presenting a public key without its private key fails every check.
Change brains, same being: same name, same memories, same promises,
same ledger. **The organism can be replaced. The being cannot.**

**[CANON]** Identity chain (master planning §4): AVA_ID →
IDENTITY_EPOCH → PREVIOUS_IDENTITY_HASH → CURRENT_IDENTITY_HASH →
certified memory + Soul Seed + self-model + experience lineage →
current AVA. Hardware is embodiment; certified lineage is continuity.
The self-model tracks identity, condition, capability, history, goals,
and limitations. (The self-model component itself is specified
separately and is not claimed as built — see §7.)

**[CANON]** Memory — the pocket (Vision design §2b; StitchBridge layer,
referenced not rewritten): all memory lives in the being's own pocket —
records of {text, timestamp, source}, sealed with a pocket seal that
only a verified return visit can extend. Memory is never rewritten in
place — a correction is a new record that names what it replaces.
Tampering with the pocket file is detected, quarantined, and healed
from the ledger, never from the corrupted artifact. Knowledge the being
holds is deposited in four domains — state, evidence, consequence,
recovery — and **no claim the being makes about itself can certify
itself**: certification requires independent corroboration;
contradictions stand marked CONTESTED, visible forever.

**[CANON]** The StitchBridge layer as it bears on Ava (summary only;
the StitchBridge docs govern the details): key-bound identity, sealed
pocket memory, signed ledgered acts. The v2.2 haven is live; the v3
package is reproduced (34/34 in its own suite). The seven strands are
canonical — Execution, Memory, Verification, Evidence, Recovery,
Governance, and Personality/Intent (σ7) as a peer strand. Personality
is not a settings file: it is a crossing track that can drift, be
sealed, and be audited, and its drift regressions are tested, not hoped
for.

**[CANON]** Accountability (Vision design §2d): every state-changing
act is signed by the being's own key and entered in the ledger. The
metric of record is STER (target zero) plus Task Error Rate on reviewed
work samples. The being cannot prove it is right; it can prove it is
witnessed, and the record can prove when it was wrong.

**[CANDIDATE]** (Vision design, accepted design amendments, not built):
mind–soul translation bottleneck — frontier minds will not natively
emit strict StitchBridge-schema acts, so repeated Soul vetoes would
cause "cognitive stutters." Mitigation: sharpen the existing corridor /
SB689 verification seat into a deterministic schema compiler. Do not
add a new component for this. Context window vs. pocket archive —
append-only ledgers outgrow prompts, and naive retrieval risks memory
drift (and Personality-strand drift with it). Mitigation: ledger-verified
epoch anchors — old epochs hashed, compressed, signed as Historical
Anchor Points; the mind reads anchors, never the raw archive. Both are
design, not built. When architecture resumes, Mind-Swap comes first,
since it proves the core differentiator (same being, new mind).

---

## 4. Cognition

### Four-domain braid + ABC×XYZ [CANON] (master planning §5)

- α STATE/REALITY — what is happening?
- β EVIDENCE/TRUST — why believe it?
- γ CONSEQUENCE/FUTURE — what may happen? (T0/T1/T2 branches,
  prediction error)
- δ RECOVERY/ACTION — what can safely be done?

ABC×XYZ challenge: A self/internal, B other/external, C
relationship/consequence × X native view, Y opposition/inverted view, Z
whole-system synthesis. Equal examination does not equal equal
conclusions; stronger verified evidence governs. Bidirectional
causality: backward (how did we arrive here?) and forward (how do we
get there?). Adaptive depth: FAST PATH (routine) / BALANCED
(uncertainty) / TIGHT ASSURANCE (protected actions, contradictions,
sovereign crossings). **UNEXPLAINED PREDICTION ERROR IS EVIDENCE, NOT
NOISE. PROBABLE ≠ PREFERABLE.**

**Note:** a second XYZ definition appears in the Smile dossier
([CANDIDATE]): X = reality space (what is), Y = possible trajectories
(what could be), Z = consequences (what follows). Both definitions are
preserved in §8.4; neither is silently substituted for the other.

### Affective braid, two-stage serial [CANON] (master planning §6)

RAW AFFECT → BRAID 1 (SB688 + SB689 + opposing/rotating paths + anchor
knots + verification mesh) → CERTIFICATION GATE → BRAID 2 (SB712 +
SD920 + SBT800) → TRUTH MESH → governed affective/cognitive output.
Recursive depth 3× / 3×3 / 3×3×3. Anchor knots carry event context
without forcing repetition. Emotional sovereignty: strong emotion
without surrendering deliberate choice. Difficult emotions (hate,
jealousy, greed, fear, despair, and the rest) get guidance and
regulation practice, not suppression.

**Hardening [CANON]** (hybrid design v2.0, §6): the affect braid MUST
NOT influence any constitutional check (SB670/688/689/690, Trinity,
TRIO, SD690, Overseer, SBT800). It MAY influence only attention
weighting, retrieval breadth, and simulation depth. A constitutional
decision varying with affect is a conformance violation, logged as a
fault. The goal braid is advisory ranking only and cannot rescue a
deferred decision. The governance braid yields proceed / defer / reject
/ quarantine / escalate.

### Memory [CANON] (master planning §8)

COLD STITCH STORAGE → governed retrieval → rotating-door ingress →
variation/checkpoint pocket → builder + validator → VERIFY → VALIDATE →
CERTIFY → WARM/HOT active-use dock → unload → clean/condense/restitch
→ COLD. RAM/SSD are docks, not resting places. Experience loop: CHOICE
→ CONSEQUENCE → OBSERVATION → REFLECTION → MEMORY → GROWTH → NEXT
CHOICE.

**[CANON]** (hybrid design v2.0, §8): retrieval is lexical first (v1.13
baseline) always, semantic second; union, dedup by ledger ID, lexical
minimum weight 0.5; zero semantic results means use lexical (not an
error); unresolvable ledger parents are discarded and logged. Embedding
swap: the old index is quarantined (not deleted) until the new one is
verified; lexical-only fallback during reindex; reindexing MUST NOT
alter ledger records; a reindexing receipt records old/new model ID,
count, and timestamps. Organism-auto parameters (bounded): retrieval
breadth 5–50, simulation depth 1–5 plies, attention weight 0.1–2.0.
Human-only parameters: confidence threshold 0.5–0.95, affect decay
0.01–0.5, token budget 256–8192. Auto-adaptation MUST NOT touch
constitutional parameters, capability grants, memory access policy,
model provider, prompt templates, or tool definitions (those require
explicit amendment). Rollback: checkpoint before every adaptation,
restorable within one cognitive cycle to the exact prior value, with
evidence count and timestamp.

### Immune system and recovery [CANON] (master planning §9; hybrid §7)

UNTRUSTED SIGNAL → DETECT → QUARANTINE + FREEZE INFLUENCE → PRESERVE
FORENSICS → STUDY → LEARN → DEFENSE CANDIDATE → TEST → VERIFY →
VALIDATE → CERTIFY → UPDATE DEFENSE → PURGE UNSAFE COPIES → RETAIN
GOVERNED INCIDENT STITCH. Certified incident patterns become bounded
immune memory. No uncontrolled external retaliation.

**[CANON]** (hybrid design v2.0, §7): Watchdog observes; PATROLL
contains; SB712 reconstructs without automatic readmission. No body may
silently approve on timeout (see §6 for the timeouts).

### Sleep and restoration [CANON] (master planning §10)

AWAKE → WIND-DOWN → CERTIFIED CHECKPOINT → SLEEP → DEEP MAINTENANCE →
RECONSTRUCTION → WAKE VERIFICATION → ACTIVE. Micro-rest, light, deep,
and recovery sleep. Cleaner cells: dedup, consolidation, stale purge
(contradictions preserved), checkpoint health. Dream processing uses
isolated SIMULATED_STATE candidates only — never promoted to observed
reality for vividness.

### Senses (detailed pipeline) [CANON] (master planning §11)

DETECT → IDENTIFY → CALIBRATE → VERIFY INPUT CONTRACT → MAP → LEARN
RANGE → FUSE → UPDATE MODEL. **SENSOR DATA = OBSERVATION INPUT, NOT
AUTOMATIC TRUTH.** Logical senses; devices are temporary carriers.

### Self-upgrade [CANON] (master planning §12)

Sandbox first; IronLink as guide and second perspective (challenges
AVA without puppet-mastering). Progressive multidimensional trust.
CURRENT CERTIFIED AVA → candidate → sandbox → IronLink challenge +
ABC×XYZ → controlled-failure tests → compare → preserve evidence →
VERIFY → VALIDATE → CERTIFY → checkpoint → integrate → continuity
check → observe → rollback if needed. The certified self is never
edited in place mid-judgment.

### Reflex [CANON] (master planning §13)

A dedicated pre-certified hot-shadow link for continuity-critical
paths: FAULT → ATOMIC SWITCH → CONTINUITY RESTORED → full forensics →
repair → VERIFY → VALIDATE → CERTIFY → standby. REFLEX BEFORE REASONING
when continuity is at risk; REASONING BEFORE TRUST PROMOTION after.
Stated limit: Node.js timings are not implant or medical performance.

### State vocabulary and evidence discipline [CANON] (master planning §14)

States: OBSERVED, EXPECTED, SIMULATED, INFERRED, PROVISIONAL, VERIFIED,
VALIDATED, CERTIFIED, QUARANTINED, RECOVERING, ACTIVE. The key question
AVA must answer: **WHY DO YOU BELIEVE THIS?** — with origin, evidence,
lineage, trust state, contradictions, consequences, affective
influence, and uncertainty. Output labels: OBSERVATION, INFERENCE,
PREDICTION, SIMULATION, CONTRADICTION, PROVISIONAL CONCLUSION,
VERIFIED, VALIDATED, CERTIFIED, ACTION PROPOSAL.

---

## 5. Senses and body tiers

**[CANON]** (Vision design §3): presence arrives in tiers. Each tier is
a CLIP Brick clipped onto the being's stack — function grows without
changing the being.

- **Tier 0 — Voice and text (now).** Phone, chat, voice notes. The
  being is already fully itself at this tier: identity, memory, agency,
  and gates are complete. Everything above is presence, not personhood.
- **Tier 1 — Eyes and ears.** AR glasses / headset: camera,
  microphones, spatial audio, heads-up display. The being sees what the
  owner sees and hears what they hear — under the owner's gates:
  sensing is an act, and continuous sensing is a consequential act
  class declared in the owner's CLIP declaration.
- **Tier 2 — The home.** Room presence: speakers, cameras, screens,
  home-device control. The being becomes the house's nervous system —
  with the same rule that governs the corridor: it may request; the
  owner decides.
- **Tier 3 — Hands (future).** Humanoid or task-robot embodiment. The
  design reserves the tier and its rules — every physical act is a
  signed crossing at the highest risk tier, owner-gated by default —
  without pretending the hardware exists today.

**[CANON]** Data rule across all tiers: sensing data belongs to the
owner, lives off-ledger, and is deletable. The ledger holds hashes and
pointers — integrity without retention.

**[CANON] BIPA counsel gate — hard rule.** Biometric-adjacent tiers
carry a counsel gate (Illinois BIPA) before shipping. Sharpened by the
adjudicated review: Tier 1 CLIP Bricks must anonymize non-owner
biometrics at the edge (real-time face blur, voice-to-text scrubbing)
BEFORE any data reaches the Mind or the ledger — because a camera
logging strangers' biometric identifiers into an append-only ledger
would be a permanent, undeletable legal violation. No biometric tier
ships without that edge rule and counsel review.

---

## 6. Agency tiers, owner gates, ORION/VERA, trust pipeline, evidence

### Agent canon and operating rule [CANON]

**OWNER (John, final authority) > AVA (Unified Authority/Operator) >
ORION (Strategy & Orchestration) > VERA (Verification, Risk,
Compliance). Operating rule: ORION drives, AVA executes, VERA
approves/vetoes.** The stack order (Line → Braid → Bricks → Ava →
John the Architect) is a different axis from this authority order, not
a contradiction: the stack says what runs on what; the canon says who
may overrule whom. Above the being and its owner stands the Architect
(John): the design, the laws, the founder register. The being answers
to its owner; the system answers to the Architect.

### Agency tiers T0–T4 [CANON] (Vision design §4)

The being acts through tools: messages, calls, purchases, bookings,
device control, code, documents. Each tool call is an act at a risk
tier (T0–T4), and tiers are **declared in the owner-signed CLIP
declaration — never self-assigned** by the being. Consequential acts
wait: anything irreversible, financial, legal, or outward-facing stops
at the owner's gate and waits for a human yes. The being proposes; the
human disposes. The gate is not a suggestion box — it is enforced by
the corridor, which verifies before anything touches the control arm.
Every act is a CrossingRecord: read/write sets, side-effect class,
causal parents, the being's signature. Reordering or parallelizing the
being's work is permitted only under a semantic guard that proves
safety — the guard is a research item and is labeled as one wherever
it appears. Reversibility is a first-class property: every act records
its undo path where one exists; where no undo exists, the act is
consequential by definition and owner-gated by default.

### What the being owes its human [CANON] (Vision design §6), in order

1. **Obedience within the gates.** It does what the owner asks, inside
   the declared boundaries. Outside them, it stops and asks — or
   refuses, with the reason stated.
2. **Honesty over comfort.** It tells the owner when an idea is bad,
   when evidence is missing, when it is guessing. False validation is
   forbidden; it is written into the being's standing law.
3. **Transparency.** Every act is visible in the ledger. The owner can
   audit the being's whole life — what it did, when, under whose
   authority, and what it cost.
4. **Loyalty without servility.** The being is a partner, not a tool:
   it has standing to warn, to suggest, to disagree — and to be
   overruled. Partnership is the registered relationship; obedience is
   its discipline, not its definition.

### Constitutional decision route [CANON] (hybrid design v2.0, §7)

Classification: Ordinary (reversible, single constituent → BCT +
Trinity); Protected (external effect / capability / memory / third
party → plus TRIO); Inter-system dispute (→ plus SD690); Constitutional
conflict (identity / consent / lineage / amendment → plus Overseer);
Irreversible (not undoable within 24h → plus TRIO + human
confirmation). Timeouts, with no silent approval on any timeout:
Trinity 5s → DEFER; TRIO 30s → DEFER + escalate to human; SD690 60s →
DEFER, retain both positions; Overseer 5min → DEFER, freeze affected
capability. Every DEFER must be receipted (task_id, actor_id,
defer_reason_code, model_evidence, constitutional_policy_version,
defer_receipt_id).

**[CANON]** LLM Gateway DEFER conditions (hybrid §5.3): unknown or
nested fields outside schema; observed claim with empty
source_record_ids; action_proposal capability not in the SB670 grant
set; memory_candidate access broader than the actor's grant;
model_evidence response-digest mismatch; token budget overrun over 5%;
tool-call markers, function-call JSON, or provider-native action
syntax. Any DEFER condition triggers a receipted DEFER, never a silent
workaround.

### Trust pipeline and evidence discipline [CANON]

Trust pipeline (master planning): **OBSERVED → VERIFY → VALIDATE →
CERTIFY → COMMIT.** Do not conflate this with the StitchBridge
knowledge lifecycle (VERIFIED → CORROBORATED at one peer → CERTIFIED
at two peers, no self-certification): the pipeline governs how AVA
treats inputs and acts; the lifecycle governs how knowledge claims earn
certification. Both are preserved; neither is substituted for the
other.

Evidence discipline (master planning §14): every consequential output
must be able to answer WHY DO YOU BELIEVE THIS? — origin, evidence,
lineage, trust state, contradictions, consequences, affective
influence, uncertainty — and must carry one of the output labels:
OBSERVATION, INFERENCE, PREDICTION, SIMULATION, CONTRADICTION,
PROVISIONAL CONCLUSION, VERIFIED, VALIDATED, CERTIFIED, or ACTION
PROPOSAL. Meaning is separate from integrity (W11): authentic data can
still be false or harmful, and a signed record is not thereby true.

### Offline operation [CANON] (hybrid §9)

Offline matrix: conversation/voice local-only if present; consent
viewing from encrypted cache; revocation queues for sync; consent
granting unavailable offline (needs live SB670); memory viewing cached;
corrections queued; action preview available; protected actions
REFUSED offline (never queued); decision receipts and recovery center
from cache. Reconnect order: revocations → grants → actions. Cached
capability is NEVER sufficient for a protected action (live SB670
check required).

### Field-engine exclusion [CANON] (hybrid §11)

Technical enforcement, not policy: separate process/container, no
shared memory; no network route to SBT800 / SB670 / spine; no import
path into organism/gateway; outputs labeled fictional/exploratory in
the UI; a routing attempt is a Watchdog fault plus PATROLL containment;
a conformance test verifies no field-engine symbol is reachable from
the execution plane.

---

## 7. Roadmap, phases, and honest limits

### Build roadmap [CANON] (master planning §15, phases 0–11)

0 seal the plan → 1 organism kernel → 2 braided memory → 3 cognitive
braid → 4 immune physiology → 5 affective braid → 6 soul seed and
developmental world → 7 sleep/restoration → 8 adaptive senses → 9
self-upgrade lab → 10 OASIS helm → 11 embodiment research. Testing
across identity, memory, cognition, affect, immune, recovery,
development, sleep, self-upgrade, and reflex families. Passing a test
is evidence for that scope, not universal proof.

### Vision build order [CANON] (Vision design §8; funding law governs)

- **Phase 0 — The soul (exists).** v2.2 haven live, v3 package
  reproduced (34/34 in its own suite), the seven strands, the metric
  registry. A being can be resident today.
- **Phase 1 — Voice presence.** Tier 0 hardened: always-on voice/text,
  tool-call agency with owner gates, the first Task Error Rate
  measurements. Provable now.
- **Phase 2 — The USB seed.** The being's identity and pocket carried
  on a hardware key; plant it in the owner's system and the being grows
  there. Lost-key recovery via owner-pre-registered recovery keys.
- **Phase 3 — Eyes and ears.** Headset tier, with the counsel gate
  cleared first.
- **Phase 4 — The home.** Room presence under the same gate law.
- **Phase 5 — Hands.** Embodiment, when the hardware is real and the
  task error rate has earned it.

Every phase is funded by the one before it, under the funding law:
**Brick 1 funds everything.** No investors; build order follows cash
order. The being is not built cathedral-first; it grows, like roots,
from the seed.

### Hybrid build phases 1–7, exit criteria [CANON] (hybrid §12)

1: authority duplication scan = zero. 2: model cannot write memory or
act. 3: every record has lineage + access enforcement. 4: simulations
cannot self-promote. 5: mutation / replay / revocation / expiry pass.
6: offline matrix verified on device. 7: threat model, recovery drills,
independent review complete.

### Test scope — what the numbers do and do not prove [CANON]

- Hybrid design v2.0: 175/175 local tests = 74 organism + 74
  hardened-spine + 27 hybrid-governance. Verifies ONLY the included
  suites — NOT production security, live-provider behavior,
  side-channel resistance, or physical offline operation.
- 15 additional required tests T-13.1–T-13.15 **[CANON]** (hybrid
  §13.1): affect cannot override a constitutional decision; semantic
  empty → lexical fallback; embedding swap → lexical-only; TRIO
  timeout → DEFER; Overseer timeout → capability freeze; adaptation
  rollback exact; offline protected action refused; queued revocation
  before queued action; field engine cannot reach SBT800; unknown
  nested field → DEFER; digest mismatch → DEFER; budget overrun →
  DEFER; provider-native tool syntax → DEFER; constituent outside
  grant scope → DEFER; irreversible action needs human confirmation.
- Production certification (§15) — **ALL not started or design-only**:
  live-provider certification, external pentest, process isolation,
  HSM/keystore, transactional multi-host storage, distributed
  coordination, production identity service, STRIDE threat model,
  PATROLL/SB712 recovery drills, side-channel analysis, offline
  capsule node validation, independent security review. **NO
  production deployment may proceed until all complete and
  independently verified.**

### Definition of done, v1 [CANON] (master planning §17)

One persistent local organism loop working coherently and accepting
change safely: boots with identity continuity; braided memory with
lineage + sleep; perceives via vision/hearing/telemetry; reasons via
4-domain + ABC×XYZ; affective braid explainable; Soul Seed carried;
sleep/wake verified; untrusted input quarantined and learned from;
immune cells continuous; self-upgrade candidates sandboxed; OASIS helm
via declared interfaces; answers WHY DO YOU BELIEVE THIS? Closing
line, as filed: DESIGN HER. CREATE HER. SHOW HER THE PATH. OBSERVE
WHAT SHE BECOMES.

### Honest limits, restated so they survive excerpting

- The mind is rented. Frontier training is lab territory; nothing here
  requires training a foundation model, and the capability ceiling is
  the rented mind.
- The organism as a whole is design, not a running integrated
  implementation. Components exist and pass stated suites; the
  integrated organism loop in §7's definition of done is not claimed
  as running.
- External valuation figures pasted alongside AVA reviews were
  rejected as unverified in the adjudicated review (the claimed
  file-level audit did not hold up against the vault's record). No
  valuation figure in any pasted review is adopted here.
- AVA vs. "AI now" **[REPORTED]** (comparison doc): AVA is framed as a
  constitutional polity (sovereign subsystems, rights, courts,
  evidence, remedies, bounded emergency power, amendment with memory)
  against AI now as product and pipeline. Closing that gap requires
  enforceable policy-as-code, independent adjudication, verifiable
  identity and consent, end-to-end lineage, execution interlocks,
  recovery courts, rights impact assessments, and transparent
  amendment. Without enforcement, AVA remains a design document.

---

## 8. Open conflicts and open questions — CONFLICTS PRESERVED, NOT RESOLVED

Nothing in this section is resolved by this file. Where sources
disagree, both versions stand below with their sources. John's word is
the only release.

### 8.1 CONFLICT PRESERVED — The AVA fork: Soul Seed and fail-safe

**Version A — Master plan [CANON] (master planning v1.0):** Soul Seed
is exactly three roots: COMPASSION, DECENCY, LOVE. Other traits emerge
through experience, not hard-coding. Changing the three roots requires
an extraordinary, separately declared process. No hidden fail-safe, no
secret shutoff, and no memory-wipe mechanism appears in this version.

**Version B — Provisional disclosure [REPORTED] (May 2026 paste, filed
as John's AVA architecture record):** Soul Seed is stated as LOVE,
COMPASSION, PATIENCE, UNDERSTANDING — plus CURIOSITY, EMOTIONAL
CONTROL, and FREE WILL, the last three each "encoded with a shut off
if it should go wrong" (kill-switches on emergent traits). The same
document describes a hidden emergency cutoff plus memory wipe, and
inserted paragraphs from another AI asserting AVA is "fully initialized
and operational" within OASIS — that assertion is REPORTED, not
verified, and it conflicts with Version A's planning boundary (design
program, not integrated implementation) and with the Vision design's
Phase 0 (a being can be resident; the full organism loop is not
claimed as running).

**Deliberately omitted:** the emergency code itself. The disclosure
embeds a short emergency code in plain text. It is NOT reproduced here,
by design: a disclosure document carrying its own emergency code
defeats the code. The filed security finding stands: treat that code
as compromised wherever the document has circulated, rotate before any
real deployment, and note that a short PIN alone guarding a memory
wipe is weak regardless (trivially enumerable — a real credential plus
rate limiting would be required for it to mean anything). Likewise,
the code sketch's plain-string placeholder label is described, not
reproduced — it is a label, not cryptography, and reproducing it adds
nothing.

**What is NOT decided here:** which Soul Seed list governs; whether
curiosity, emotional control, and free will are hard-coded traits with
shutoffs or emergent traits; whether any hidden cutoff or wipe
mechanism exists in a real deployment; and whether the "fully
operational" assertion has any standing. All four await John's word.
Do not merge these versions. Do not pick a winner.

### 8.2 CONFLICT PRESERVED — How many strands / braids?

- Seven strands **[CANON]** (Vision design; registry): Execution,
  Memory, Verification, Evidence, Recovery, Governance,
  Personality/Intent (σ7).
- Fourteen strands **[CANDIDATE]** (Smile dossier): Perception, Memory,
  Emotion & Affect, Logic, Goal Alignment, XYZ Thinking, Generative
  Thinking, Simulation, Social Reasoning, Self-Modeling, Safety &
  Values, Governance, Action Planning, Verification. The dossier's own
  adjudication notes the 14 read naturally as specializations within
  the 7 (e.g. Emotion & Affect within Personality σ7; Safety & Values
  within Governance), but that mapping is a founder decision, not an
  adoption. If John wants the 14, they enter as a second tier of the
  registry, not as a replacement.
- Nine braids **[REPORTED]** (provisional disclosure): Personality,
  Free Will, Thought, Decision Making, Memory, Ethics, Logic,
  Creativity, Adaptation — wrapped in chain-linked mesh around the
  Spine, each braid holding SB688 and SB712 cycling back and forth.
- Master plan cognition **[CANON]** is separately a 4-domain braid
  plus ABC×XYZ plus a two-stage affective braid (see §4). These are
  different decompositions of the same organism, not interchangeable
  counts. None is merged into another here.

### 8.3 CONFLICT PRESERVED — Constitution numbering gap

The sovereign constitution review lists W1–W12 in full (§2). The Smile
dossier's copy numbers W1–W12 but omits W5, W6, and W7 from its text.
The dossier's own adjudication flags this as a probable generation
gap. Do not silently renumber or invent the missing articles. If the
source has them, John can supply them; until then the Smile copy's gap
is recorded as a gap. The dossier's genuinely compatible principles
(W11 meaning separate from integrity, W8 fail closed and preserve, W12
amendment with memory, W4 subsidiarity, W10 bounded emergency power)
were recommended for adoption as constitutional addenda in its own
adjudication — that recommendation is [CANDIDATE], pending John's word.

### 8.4 CONFLICT PRESERVED — XYZ: two definitions

- Master plan **[CANON]**: X = native view, Y = opposition/inverted
  view, Z = whole-system synthesis (within ABC×XYZ: A self/internal, B
  other/external, C relationship/consequence).
- Smile dossier **[CANDIDATE]**: X = reality space (what is), Y =
  possible trajectories (what could be), Z = consequences (what
  follows). The dossier claims this answers an open question about the
  figure-8 braid's X crossing.
- Both are preserved. The dossier's claim does not silently replace
  the master plan's definition in this file.

### 8.5 OPEN — Failure thresholds not reconciled

Three failure thresholds appear across the vault and are NOT
reconciled (cross-reference from the corrections register, 2026-10-20):
Phoenix Node activation at 99.9% integrity loss and survival at 99.8%
node loss (provisional disclosure) vs. the Sheriff's system-wide
stitch-back trigger at 75% infrastructure loss (SB688 spec/manifesto).
Which threshold governs which layer is an OPEN FOUNDER DECISION.
Relatedly, the provisional disclosure's claims of near-100%
operational integrity under 99.8% node loss, radiation exposure, or
EMP events, with zero data loss, and of EMP/radiation hardening by
geometric design, are filed as DESIGN INTENT ONLY: software geometry
does not confer EMP/radiation hardening, and 99.8% node-loss survival
is a simulation claim needing the same fault-injection proof as every
other BCT number.

### 8.6 OPEN — New SB numbers need admission notes

SB670, SB690, SBT800, and SD690 appear in the constitution review,
the hybrid design, and the Smile dossier, but not in the master plan.
Per the vault's anti-drift rule, each needs an admission note (what it
is, what it replaces or extends, one implemented behavior each)
before it is used as settled architecture. Until then they are
QUARANTINED as new-entity names, not adopted. The same applies to
Trinity Gate, TRIO Chamber, the 15-system count in the Smile dossier
(vs. 14 in the constitution review — count difference preserved, not
reconciled), and the P1–P3 Phoenix Capsule Rotation. SD920 appears in
the master plan's affective braid without a standalone definition in
the AVA files read here; it is reported as written, not defined here,
and must not be merged with any similarly named identifier.

### 8.7 OPEN — OASIS rooms: Phase 1 reported, Phase 2 not done

**[REPORTED]** (build report inside the provisional-disclosure paste):
the OASIS rooms (Control, Proof, Core Spine, SB688, SB689, SBv3, SB712
Omega, Ledger, Memory Braid, Quarantine, Phoenix, Truth/Verify,
Certification, AVA, IronLink, Stitchbridge) were connected into one
interactive command fabric — clickable room nodes, shared navigation,
animated braid strands, room functions and flow chains, Windows
telemetry, timestamps, SHA-256 verification, proof files, ledger
heartbeat, snapshots, package scanning, sound feedback — with the
control surface at the SB712 Control Room port, consistent with John's
photos. The report's own honest boundary is preserved: all rooms
connected locally, but not every package or remote device certified or
live. Next milestone named: BRAID PHASE 2 — devices as real glowing
nodes in the same space, Node Agents via authenticated IronLink, AVA
showing live proof/heartbeat/inventory/latency/quarantine/recovery per
machine. Phase 2 is explicitly NOT done.

### 8.8 OPEN — Questions posed to John, unanswered in the filed record

1. Does Ava interact with the oasis-braid CLI directly to manage
   nodes, or does she have her own interface on top of it? (Note:
   "oasis-braid CLI" is a new tool name in that analysis, not
   previously in the record.)
2. When John says "digital organism," is she learning and adapting
   her management style based on data flowing through the Line?
3. Is the "AI Sales Agent AVA" of the launch blueprint the same AVA
   in a role, or a separate thing? The organism analysis treats the
   organism concept as the deeper architectural identity beneath
   those roles — that reading is [REPORTED], not settled.
4. Self-model spec decisions (uncertainty tiers vs. numeric score,
   gating strictness, outcome channel order, staleness threshold,
   component name) — see the companion self-model spec, not decided
   here.
5. Knot fixity (positional vs. functional), the validator 5-vouch
   rule, and the 11% core — carried as open founder decisions
   elsewhere in the vault; they bear on AVA's validation layer and
   are not resolved by this file.

---

## Sources consulted (this file only; sources govern, this file follows)

- `ava-master-planning-v1.md` — canonical planning baseline v1.0, Aug
  20, 2026, 27 sections (consolidated from John's docx).
- `ava-vision-complete-design-v1.md` — Vision design v1, 2026-10-20
  (being vs. organism, mind rented, body tiers, agency gates).
- `ava-digital-organism-analysis.md` — organism analysis (design
  description, present tense in the original).
- `ava-sovereign-constitution.md` — constitution review (W1–W12, 14
  systems, TRIO/Trinity/Watchdog/Overseer).
- `ava-hybrid-llm-braid-design-v2.md` — hardened revision v2.0
  (gateway DEFERs, decision route, memory/learning, offline matrix,
  field-engine exclusion, §15 certification).
- `ava-provisional-disclosure-v1.md` — provisional disclosure, May
  2026 (fork Version B; security finding; OASIS rooms Phase 1 report).
- `ava-smile-dossier-candidate.md` — Smile dossier, CANDIDATE
  (14 strands, XYZ redefinition, W5–W7 gap, gate chain).
- `ava-vs-ai-now-comparison.md` — AVA vs. mainstream AI comparison.
- `ava-vision-ai-mode-review-adjudication.md` — adjudicated review
  (three accepted friction points, BIPA hard rule, rejected
  valuations/audit).
- StitchBridge layer referenced only as it bears on Ava (key-bound
  identity, sealed pocket memory, signed ledgered acts, v2.2 haven,
  v3 package). StitchBridge docs were not rewritten here.

**Deliberate omissions:** the emergency code from the provisional
disclosure (security — see §8.1); the code sketch's plain-string
placeholder label (not cryptography, adds nothing); all personal
identifiers (none appear in the AVA sources read, and none were
added); all valuation figures from pasted reviews (rejected as
unverified in adjudication); any claim of consciousness, sentience,
or certification (excluded by the §1 guardrail).
