//! # BCT Phoenix Braid Kernel
//!
//! A bounded, dependency-free algebraic kernel for the BCT research architecture.
//!
//! ## What this module does
//! - Represents signed Artin braid words on `B_n`.
//! - Computes the exact faithful Artin action on the free group `F_n`.
//! - Tests braid-word equivalence within configured resource limits.
//! - Computes exact syntactic braid inverses.
//! - Verifies Phoenix recovery algebraically.
//! - Tracks semantic strand identities while crossings permute positions.
//! - Enforces a zero-trust gate for cognition -> memory promotion.
//!
//! ## What this module deliberately does NOT claim
//! - It is not a full Garside normal-form implementation.
//! - It does not equate logical contradictions with mathematical knots.
//! - It does not execute destructive rollback by replaying inverse business operations.
//! - It does not provide cryptographic signatures or durable storage.
//!
//! Phoenix uses the algebraic inverse as a proof/verification object. Actual system
//! recovery should restore a certified checkpoint and then re-verify before promotion.

use std::fmt;

pub type BctResult<T> = Result<T, BctError>;

/// Semantic strand cap for this kernel: the BCT domains are strands 1-66
/// (cognition 1-22, memory 23-36, evidence 37-48, authority 49-58,
/// recovery 59-66). A larger `n` is not a claim about B_n in general; it is
/// out of scope here, and accepting it would allow unbounded allocation in
/// identity actions. All constructors enforce this bound.
pub const MAX_STRANDS: usize = 66;

/// Strand-count check shared by every constructor: at least 2, at most
/// MAX_STRANDS. This bounds identity-action allocation (num_strands images).
fn check_strand_count(num_strands: usize) -> BctResult<()> {
    if num_strands < 2 || num_strands > MAX_STRANDS {
        return Err(BctError::InvalidStrandCount { strands: num_strands });
    }
    Ok(())
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum BctError {
    InvalidStrandCount { strands: usize },
    GeneratorOutOfBounds { index: usize, strands: usize },
    StrandCountMismatch { left: usize, right: usize },
    TraceTooLong { found: usize, max: usize },
    FreeWordTooLong { found: usize, max: usize },
    TotalActionTooLarge { found: usize, max: usize },
    VerifiedPrefixOutOfBounds { verified: usize, total: usize },
    CheckpointCorrupt(String),
    RecoveryMismatch,
    ClaimedStrandMismatch {
        position: usize,
        expected_strand_id: usize,
        claimed_strand_id: usize,
    },
    GateRejected(String),
}

impl fmt::Display for BctError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::InvalidStrandCount { strands } => {
                write!(f, "braid requires at least 2 strands; got {}", strands)
            }
            Self::GeneratorOutOfBounds { index, strands } => write!(
                f,
                "sigma_{} is invalid for B_{}; valid generator indices are 1..{}",
                index,
                strands,
                strands.saturating_sub(1)
            ),
            Self::StrandCountMismatch { left, right } => {
                write!(f, "strand-count mismatch: {} != {}", left, right)
            }
            Self::TraceTooLong { found, max } => {
                write!(f, "trace contains {} generators; configured maximum is {}", found, max)
            }
            Self::FreeWordTooLong { found, max } => {
                write!(f, "free-group image grew to {} symbols; configured maximum is {}", found, max)
            }
            Self::TotalActionTooLarge { found, max } => {
                write!(f, "total Artin action contains {} symbols; configured maximum is {}", found, max)
            }
            Self::VerifiedPrefixOutOfBounds { verified, total } => write!(
                f,
                "verified prefix length {} exceeds total trace length {}",
                verified, total
            ),
            Self::CheckpointCorrupt(msg) => {
                write!(f, "checkpoint corrupt or tampered: {}", msg)
            }
            Self::RecoveryMismatch => {
                write!(f, "candidate inverse did not restore the verified braid action")
            }
            Self::ClaimedStrandMismatch {
                position,
                expected_strand_id,
                claimed_strand_id,
            } => write!(
                f,
                "claimed strand mismatch at position {}: expected strand {}, got {}",
                position, expected_strand_id, claimed_strand_id
            ),
            Self::GateRejected(msg) => write!(f, "gate rejected event: {}", msg),
        }
    }
}

impl std::error::Error for BctError {}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Limits {
    pub max_trace_generators: usize,
    pub max_free_word_len: usize,
    pub max_total_action_symbols: usize,
}

impl Default for Limits {
    fn default() -> Self {
        Self {
            max_trace_generators: 4096,
            max_free_word_len: 250_000,
            max_total_action_symbols: 1_500_000,
        }
    }
}

/// Mathematical generator sigma_i^(+/-1).
///
/// `index` is **1-based**, matching standard braid notation:
/// sigma_1 crosses positions 1 and 2.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub struct Generator {
    pub index: usize,
    pub is_positive: bool,
}

impl Generator {
    pub const fn positive(index: usize) -> Self {
        Self {
            index,
            is_positive: true,
        }
    }

    pub const fn negative(index: usize) -> Self {
        Self {
            index,
            is_positive: false,
        }
    }

    pub const fn inverse(self) -> Self {
        Self {
            index: self.index,
            is_positive: !self.is_positive,
        }
    }

    pub fn validate(self, num_strands: usize) -> BctResult<()> {
        check_strand_count(num_strands)?;
        if self.index == 0 || self.index >= num_strands {
            return Err(BctError::GeneratorOutOfBounds {
                index: self.index,
                strands: num_strands,
            });
        }
        Ok(())
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct BraidWord {
    pub num_strands: usize,
    pub generators: Vec<Generator>,
}

impl BraidWord {
    pub fn identity(num_strands: usize) -> BctResult<Self> {
        check_strand_count(num_strands)?;
        Ok(Self {
            num_strands,
            generators: Vec::new(),
        })
    }

    pub fn new(num_strands: usize, generators: Vec<Generator>) -> BctResult<Self> {
        check_strand_count(num_strands)?;
        for &g in &generators {
            g.validate(num_strands)?;
        }
        Ok(Self {
            num_strands,
            generators,
        })
    }

    pub fn inverse(&self) -> Self {
        let generators = self
            .generators
            .iter()
            .rev()
            .copied()
            .map(Generator::inverse)
            .collect();

        Self {
            num_strands: self.num_strands,
            generators,
        }
    }

    pub fn concat(&self, other: &Self) -> BctResult<Self> {
        if self.num_strands != other.num_strands {
            return Err(BctError::StrandCountMismatch {
                left: self.num_strands,
                right: other.num_strands,
            });
        }

        let mut generators =
            Vec::with_capacity(self.generators.len() + other.generators.len());
        generators.extend_from_slice(&self.generators);
        generators.extend_from_slice(&other.generators);

        Ok(Self {
            num_strands: self.num_strands,
            generators,
        })
    }

    /// Cancels only immediately adjacent g g^-1 pairs.
    ///
    /// This is intentionally not advertised as a full braid normal form.
    pub fn free_reduce(&self) -> Self {
        let mut stack: Vec<Generator> = Vec::with_capacity(self.generators.len());

        for &g in &self.generators {
            if let Some(last) = stack.last().copied() {
                if last.index == g.index && last.is_positive != g.is_positive {
                    stack.pop();
                    continue;
                }
            }
            stack.push(g);
        }

        Self {
            num_strands: self.num_strands,
            generators: stack,
        }
    }
}

/// Reduced word in the free group F_n.
/// Positive k means x_k, negative k means x_k^-1.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct FreeWord {
    letters: Vec<i32>,
}

impl FreeWord {
    fn empty() -> Self {
        Self { letters: Vec::new() }
    }

    fn basis(index_1_based: usize) -> Self {
        Self {
            letters: vec![index_1_based as i32],
        }
    }

    fn inverse(&self) -> Self {
        Self {
            letters: self.letters.iter().rev().map(|x| -*x).collect(),
        }
    }

    fn append_reduced(&mut self, other: &Self, limits: &Limits) -> BctResult<()> {
        for &letter in &other.letters {
            if self.letters.last().copied() == Some(-letter) {
                self.letters.pop();
            } else {
                self.letters.push(letter);
            }

            if self.letters.len() > limits.max_free_word_len {
                return Err(BctError::FreeWordTooLong {
                    found: self.letters.len(),
                    max: limits.max_free_word_len,
                });
            }
        }
        Ok(())
    }

    pub fn letters(&self) -> &[i32] {
        &self.letters
    }
}

/// Faithful Artin representation B_n -> Aut(F_n).
///
/// We use:
/// sigma_i:
///   x_i     -> x_i x_{i+1} x_i^-1
///   x_{i+1} -> x_i
///
/// sigma_i^-1:
///   x_i     -> x_{i+1}
///   x_{i+1} -> x_{i+1}^-1 x_i x_{i+1}
///
/// Equality of these automorphisms is exact braid-group equality, subject only
/// to the configured resource bounds.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct BraidAction {
    pub num_strands: usize,
    images: Vec<FreeWord>,
}

impl BraidAction {
    pub fn identity(num_strands: usize) -> BctResult<Self> {
        check_strand_count(num_strands)?;

        Ok(Self {
            num_strands,
            images: (1..=num_strands).map(FreeWord::basis).collect(),
        })
    }

    pub fn from_word(word: &BraidWord, limits: &Limits) -> BctResult<Self> {
        if word.generators.len() > limits.max_trace_generators {
            return Err(BctError::TraceTooLong {
                found: word.generators.len(),
                max: limits.max_trace_generators,
            });
        }

        let mut action = Self::identity(word.num_strands)?;
        for &g in &word.generators {
            action.apply_right_generator(g, limits)?;
        }
        Ok(action)
    }

    fn apply_right_generator(
        &mut self,
        generator: Generator,
        limits: &Limits,
    ) -> BctResult<()> {
        generator.validate(self.num_strands)?;

        let i = generator.index - 1;
        let left = self.images[i].clone();
        let right = self.images[i + 1].clone();

        if generator.is_positive {
            // f o sigma_i:
            // x_i     -> f(x_i x_{i+1} x_i^-1)
            // x_{i+1} -> f(x_i)
            let mut new_left = FreeWord::empty();
            new_left.append_reduced(&left, limits)?;
            new_left.append_reduced(&right, limits)?;
            new_left.append_reduced(&left.inverse(), limits)?;

            self.images[i] = new_left;
            self.images[i + 1] = left;
        } else {
            // f o sigma_i^-1:
            // x_i     -> f(x_{i+1})
            // x_{i+1} -> f(x_{i+1}^-1 x_i x_{i+1})
            let mut new_right = FreeWord::empty();
            new_right.append_reduced(&right.inverse(), limits)?;
            new_right.append_reduced(&left, limits)?;
            new_right.append_reduced(&right, limits)?;

            self.images[i] = right;
            self.images[i + 1] = new_right;
        }

        let mut total: usize = 0;
        for w in &self.images {
            total = total.checked_add(w.letters.len()).ok_or(BctError::TotalActionTooLarge {
                found: usize::MAX,
                max: limits.max_total_action_symbols,
            })?;
        }
        if total > limits.max_total_action_symbols {
            return Err(BctError::TotalActionTooLarge {
                found: total,
                max: limits.max_total_action_symbols,
            });
        }

        Ok(())
    }

    pub fn images(&self) -> &[FreeWord] {
        &self.images
    }
}

pub fn braid_equivalent(
    left: &BraidWord,
    right: &BraidWord,
    limits: &Limits,
) -> BctResult<bool> {
    if left.num_strands != right.num_strands {
        return Err(BctError::StrandCountMismatch {
            left: left.num_strands,
            right: right.num_strands,
        });
    }

    Ok(
        BraidAction::from_word(left, limits)?
            == BraidAction::from_word(right, limits)?,
    )
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum RecoveryStrategy {
    /// Restore the last certified checkpoint, then pass the restored state through
    /// ordinary verification before promotion.
    RestoreCheckpointThenReverify,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PhoenixRecoveryPlan {
    pub verified_history: BraidWord,
    pub candidate_suffix: BraidWord,
    pub algebraic_inverse: BraidWord,
    pub proof_trace: BraidWord,
    pub strategy: RecoveryStrategy,
}

/// Build and algebraically verify a Phoenix recovery plan.
///
/// Important:
/// `algebraic_inverse` is a proof object. It is NOT permission to replay arbitrary
/// business/system operations backwards. Real recovery restores a certified
/// checkpoint and re-verifies it.
pub fn plan_phoenix_recovery(
    total_trace: &BraidWord,
    verified_prefix_len: usize,
    limits: &Limits,
) -> BctResult<PhoenixRecoveryPlan> {
    if verified_prefix_len > total_trace.generators.len() {
        return Err(BctError::VerifiedPrefixOutOfBounds {
            verified: verified_prefix_len,
            total: total_trace.generators.len(),
        });
    }

    let verified_history = BraidWord::new(
        total_trace.num_strands,
        total_trace.generators[..verified_prefix_len].to_vec(),
    )?;

    let candidate_suffix = BraidWord::new(
        total_trace.num_strands,
        total_trace.generators[verified_prefix_len..].to_vec(),
    )?;

    let algebraic_inverse = candidate_suffix.inverse();
    let proof_trace = total_trace.concat(&algebraic_inverse)?;

    if !braid_equivalent(&proof_trace, &verified_history, limits)? {
        return Err(BctError::RecoveryMismatch);
    }

    Ok(PhoenixRecoveryPlan {
        verified_history,
        candidate_suffix,
        algebraic_inverse,
        proof_trace,
        strategy: RecoveryStrategy::RestoreCheckpointThenReverify,
    })
}

/// Hardened Phoenix plan: candidate, evidence, and committed history are
/// three different things, and must not be collapsed into one suffix.
///
/// - `verified_history` is committed history, already certified.
/// - `candidate` is the unverified braid being tested for cancellation.
/// - `evidence` is a contradiction / fault record. It is NOT inverted, NOT
///   replayed, and NOT treated as a braid to cancel. It is quarantined:
///   returned separately, never included in `proof_trace`, and never
///   granted authority by this function.
///
/// The old `plan_phoenix_recovery` is kept for compatibility, but it treats
/// everything after `verified_prefix_len` as the candidate. Prefer this
/// function whenever a trace may contain separate evidence material.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PhoenixRecoveryPlanV2 {
    pub verified_history: BraidWord,
    pub candidate: BraidWord,
    pub evidence: BraidWord,
    pub algebraic_inverse: BraidWord,
    pub proof_trace: BraidWord,
    pub evidence_quarantined: bool,
    pub strategy: RecoveryStrategy,
}

pub fn plan_phoenix_recovery_with_evidence(
    total_trace: &BraidWord,
    verified_len: usize,
    candidate_len: usize,
    limits: &Limits,
) -> BctResult<PhoenixRecoveryPlanV2> {
    let total = total_trace.generators.len();
    if verified_len + candidate_len > total {
        return Err(BctError::VerifiedPrefixOutOfBounds {
            verified: verified_len + candidate_len,
            total,
        });
    }

    let verified_history = BraidWord::new(
        total_trace.num_strands,
        total_trace.generators[..verified_len].to_vec(),
    )?;
    let candidate = BraidWord::new(
        total_trace.num_strands,
        total_trace.generators[verified_len..verified_len + candidate_len].to_vec(),
    )?;
    let evidence = BraidWord::new(
        total_trace.num_strands,
        total_trace.generators[verified_len + candidate_len..].to_vec(),
    )?;

    let algebraic_inverse = candidate.inverse();
    // Proof only covers verified + candidate + inverse(candidate).
    // Evidence is deliberately excluded from the proof trace.
    let verified_plus_candidate = verified_history.concat(&candidate)?;
    let proof_trace = verified_plus_candidate.concat(&algebraic_inverse)?;

    if !braid_equivalent(&proof_trace, &verified_history, limits)? {
        return Err(BctError::RecoveryMismatch);
    }

    Ok(PhoenixRecoveryPlanV2 {
        verified_history,
        candidate,
        evidence,
        algebraic_inverse,
        proof_trace,
        evidence_quarantined: true,
        strategy: RecoveryStrategy::RestoreCheckpointThenReverify,
    })
}

/// Independent check used by property tests: w * w^-1 must be the identity
/// automorphism, for any word, including negative-only words.
pub fn verify_word_inverse_identity(word: &BraidWord, limits: &Limits) -> BctResult<bool> {
    let product = word.concat(&word.inverse())?;
    let id = BraidWord::identity(word.num_strands)?;
    braid_equivalent(&product, &id, limits)
}

// ---------------------------------------------------------------------------
// Semantic strand domains and zero-trust crossing policy
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Domain {
    Cognition,
    Memory,
    Evidence,
    Authority,
    Recovery,
}

pub fn domain_of_strand(strand_id: usize) -> Option<Domain> {
    match strand_id {
        1..=22 => Some(Domain::Cognition),
        23..=36 => Some(Domain::Memory),
        37..=48 => Some(Domain::Evidence),
        49..=58 => Some(Domain::Authority),
        59..=66 => Some(Domain::Recovery),
        _ => None,
    }
}

pub fn is_affect_strand(strand_id: usize) -> bool {
    matches!(strand_id, 13..=16)
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Certification {
    Green,
    Amber,
    Red,
    Black,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct GateProof {
    pub certification: Certification,
    pub evidence_certified: bool,
    pub authority_certified: bool,
    pub capability_authorized: bool,
    /// Identifier only. The cryptographic binding belongs in the command/evidence layer.
    pub proof_id: Option<String>,
}

impl GateProof {
    pub fn untrusted() -> Self {
        Self {
            certification: Certification::Amber,
            evidence_certified: false,
            authority_certified: false,
            capability_authorized: false,
            proof_id: None,
        }
    }
}

/// A gate proof that has passed structural verification. It can only be
/// built through `verify_gate_proof`, never by setting fields directly.
///
/// HONEST LIMIT: this is a structural verifier, not a cryptographic one.
/// It refuses proofs that are incomplete on their face (not GREEN, a flag
/// false, no proof id, no evidence hash, no authority). It does NOT verify
/// signatures, authority, or evidence content — that verification belongs
/// in the higher Gatekeeper layer (e.g. Ed25519 signatures over the
/// evidence), which must run before calling this function with trusted
/// inputs. A caller that fabricates all fields still passes this check;
/// that is why this type is "verified" only in the structural sense.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct VerifiedGateProof {
    pub proof_id: String,
    pub authority_id: String,
}

pub fn verify_gate_proof(
    proof: &GateProof,
    evidence_hash: &[u8],
    authority_id: &str,
) -> BctResult<VerifiedGateProof> {
    if proof.certification != Certification::Green {
        return Err(BctError::GateRejected("certification is not GREEN".into()));
    }
    if !proof.evidence_certified || !proof.authority_certified || !proof.capability_authorized {
        return Err(BctError::GateRejected(
            "a gate flag is false".into(),
        ));
    }
    let proof_id = match &proof.proof_id {
        Some(id) if !id.trim().is_empty() => id.clone(),
        _ => return Err(BctError::GateRejected("proof has no id".into())),
    };
    if evidence_hash.is_empty() {
        return Err(BctError::GateRejected("evidence hash is empty".into()));
    }
    if authority_id.trim().is_empty() {
        return Err(BctError::GateRejected("authority id is empty".into()));
    }
    Ok(VerifiedGateProof {
        proof_id,
        authority_id: authority_id.to_string(),
    })
}

/// Durable, tamper-evident checkpoint for a verified braid word.
///
/// Format (no external crates, no serde): `BCT-CKPT/1|n=<strands>|gens=<signed
/// indices, comma-separated, empty for identity>|total=<action symbols>|chk=<FNV-1a
/// hash of everything before "|chk=">`. `restore` recomputes the Artin action
/// and refuses the checkpoint if the checksum, the strand count, any
/// generator, or the stored action total disagrees. This is a checkpoint
/// format, not a cryptographic signature: a forger who recomputes the
/// checksum can forge it, which is why production checkpoints must also be
/// sealed by the higher layer (HMAC/signature over the checkpoint text).
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Checkpoint {
    pub word: BraidWord,
    pub total_action_symbols: usize,
}

fn fnv1a(text: &str) -> u64 {
    let mut h: u64 = 0xcbf29ce484222325;
    for b in text.as_bytes() {
        h ^= *b as u64;
        h = h.wrapping_mul(0x100000001b3);
    }
    h
}

impl Checkpoint {
    pub fn from_action(word: &BraidWord, action: &BraidAction) -> BctResult<Self> {
        let mut total: usize = 0;
        for w in &action.images {
            total = total.checked_add(w.letters.len()).ok_or(BctError::TotalActionTooLarge {
                found: usize::MAX,
                max: usize::MAX,
            })?;
        }
        Ok(Self {
            word: word.clone(),
            total_action_symbols: total,
        })
    }

    pub fn to_text(&self) -> String {
        let gens: Vec<String> = self
            .word
            .generators
            .iter()
            .map(|g| {
                if g.is_positive {
                    g.index.to_string()
                } else {
                    format!("-{}", g.index)
                }
            })
            .collect();
        let body = format!(
            "BCT-CKPT/1|n={}|gens={}|total={}",
            self.word.num_strands,
            gens.join(","),
            self.total_action_symbols
        );
        format!("{}|chk={:016x}", body, fnv1a(&body))
    }

    pub fn from_text(text: &str, limits: &Limits) -> BctResult<Self> {
        let (body, chk) = text.rsplit_once("|chk=").ok_or_else(|| {
            BctError::CheckpointCorrupt("missing checksum".into())
        })?;
        if format!("{:016x}", fnv1a(body)) != chk {
            return Err(BctError::CheckpointCorrupt("checksum mismatch".into()));
        }
        let mut num_strands: Option<usize> = None;
        let mut gens: Vec<Generator> = Vec::new();
        let mut total: Option<usize> = None;
        for part in body.split('|') {
            if let Some(v) = part.strip_prefix("n=") {
                num_strands = Some(v.parse().map_err(|_| {
                    BctError::CheckpointCorrupt("bad strand count".into())
                })?);
            } else if let Some(v) = part.strip_prefix("gens=") {
                if !v.is_empty() {
                    for token in v.split(',') {
                        let (neg, digits) = if let Some(d) = token.strip_prefix('-') {
                            (true, d)
                        } else {
                            (false, token)
                        };
                        let index: usize = digits.parse().map_err(|_| {
                            BctError::CheckpointCorrupt("bad generator".into())
                        })?;
                        gens.push(Generator {
                            index,
                            is_positive: !neg,
                        });
                    }
                }
            } else if let Some(v) = part.strip_prefix("total=") {
                total = Some(v.parse().map_err(|_| {
                    BctError::CheckpointCorrupt("bad action total".into())
                })?);
            }
        }
        let num_strands = num_strands
            .ok_or_else(|| BctError::CheckpointCorrupt("missing strand count".into()))?;
        check_strand_count(num_strands)?;
        let word = BraidWord::new(num_strands, gens)?;
        let total = total.ok_or_else(|| BctError::CheckpointCorrupt("missing action total".into()))?;
        let action = BraidAction::from_word(&word, limits)?;
        let restored = Checkpoint::from_action(&word, &action)?;
        if restored.total_action_symbols != total {
            return Err(BctError::CheckpointCorrupt(
                "stored action total does not match recomputed action".into(),
            ));
        }
        Ok(restored)
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum CrossingPurpose {
    IntraDomain,
    CandidateCommitToMemory,
    CrossDomainTransfer,
    RecoveryTransfer,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ActorClass {
    Normal,
    Affect,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct TraceEvent {
    pub generator: Generator,
    /// Optional identity claims are checked against the live strand permutation.
    pub claimed_left_strand_id: Option<usize>,
    pub claimed_right_strand_id: Option<usize>,
    pub purpose: CrossingPurpose,
    pub actor: ActorClass,
    pub proof: GateProof,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct QuarantineDirective {
    pub reason: String,
    pub left_strand_id: usize,
    pub right_strand_id: usize,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum GateDecision {
    Allowed,
    Quarantine(QuarantineDirective),
}

/// Tracks semantic strand IDs separately from braid positions.
///
/// This fixes a subtle but important issue: after crossings, sigma_22 no longer
/// necessarily means "cognition strand crosses memory strand". The verifier must
/// inspect the current permutation of labeled strands.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct LabeledTopology {
    pub num_strands: usize,
    order: Vec<usize>,
}

impl LabeledTopology {
    pub fn new(num_strands: usize) -> BctResult<Self> {
        check_strand_count(num_strands)?;

        Ok(Self {
            num_strands,
            order: (1..=num_strands).collect(),
        })
    }

    pub fn strand_order(&self) -> &[usize] {
        &self.order
    }

    pub fn evaluate_event(&mut self, event: &TraceEvent) -> BctResult<GateDecision> {
        event.generator.validate(self.num_strands)?;

        let pos = event.generator.index - 1;
        let left_id = self.order[pos];
        let right_id = self.order[pos + 1];

        if let Some(claimed) = event.claimed_left_strand_id {
            if claimed != left_id {
                return Err(BctError::ClaimedStrandMismatch {
                    position: pos + 1,
                    expected_strand_id: left_id,
                    claimed_strand_id: claimed,
                });
            }
        }

        if let Some(claimed) = event.claimed_right_strand_id {
            if claimed != right_id {
                return Err(BctError::ClaimedStrandMismatch {
                    position: pos + 2,
                    expected_strand_id: right_id,
                    claimed_strand_id: claimed,
                });
            }
        }

        let left_domain = domain_of_strand(left_id);
        let right_domain = domain_of_strand(right_id);

        // Affect is a modulation-only subdomain. It may braid locally among
        // affect strands, but may not cross into evidence/authority or commit memory.
        if event.actor == ActorClass::Affect {
            let affect_local =
                is_affect_strand(left_id)
                    && is_affect_strand(right_id)
                    && event.purpose == CrossingPurpose::IntraDomain;

            if !affect_local {
                return Ok(GateDecision::Quarantine(QuarantineDirective {
                    reason:
                        "affect actor may only perform local crossings among strands 13..16"
                            .to_string(),
                    left_strand_id: left_id,
                    right_strand_id: right_id,
                }));
            }
        }

        let same_domain = left_domain.is_some() && left_domain == right_domain;

        match event.purpose {
            CrossingPurpose::IntraDomain => {
                if !same_domain {
                    return Ok(GateDecision::Quarantine(QuarantineDirective {
                        reason: "event declared intra-domain but crosses a domain boundary"
                            .to_string(),
                        left_strand_id: left_id,
                        right_strand_id: right_id,
                    }));
                }
            }

            CrossingPurpose::CandidateCommitToMemory => {
                let c_m_pair = matches!(
                    (left_domain, right_domain),
                    (Some(Domain::Cognition), Some(Domain::Memory))
                        | (Some(Domain::Memory), Some(Domain::Cognition))
                );

                let proof_ok = event.proof.certification == Certification::Green
                    && event.proof.evidence_certified
                    && event.proof.authority_certified
                    && event.proof.capability_authorized;

                if !c_m_pair || !proof_ok {
                    return Ok(GateDecision::Quarantine(QuarantineDirective {
                        reason: "cognition-memory promotion requires GREEN evidence, authority, and capability proof"
                            .to_string(),
                        left_strand_id: left_id,
                        right_strand_id: right_id,
                    }));
                }
            }

            CrossingPurpose::CrossDomainTransfer => {
                if same_domain || !event.proof.capability_authorized {
                    return Ok(GateDecision::Quarantine(QuarantineDirective {
                        reason:
                            "cross-domain transfer requires a real domain boundary and authorized capability"
                                .to_string(),
                        left_strand_id: left_id,
                        right_strand_id: right_id,
                    }));
                }
            }

            CrossingPurpose::RecoveryTransfer => {
                let touches_recovery =
                    left_domain == Some(Domain::Recovery)
                        || right_domain == Some(Domain::Recovery);

                if !touches_recovery || !event.proof.capability_authorized {
                    return Ok(GateDecision::Quarantine(QuarantineDirective {
                        reason:
                            "recovery transfer must touch the recovery domain and carry authorized capability"
                                .to_string(),
                        left_strand_id: left_id,
                        right_strand_id: right_id,
                    }));
                }
            }
        }

        // Only an allowed crossing mutates the live topology.
        self.order.swap(pos, pos + 1);
        Ok(GateDecision::Allowed)
    }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    fn limits() -> Limits {
        Limits {
            max_trace_generators: 10_000,
            max_free_word_len: 100_000,
            max_total_action_symbols: 500_000,
        }
    }

    #[test]
    fn inverse_requires_reverse_order_and_flip_signs() -> BctResult<()> {
        let w = BraidWord::new(
            4,
            vec![
                Generator::positive(1),
                Generator::negative(2),
                Generator::positive(3),
            ],
        )?;

        assert_eq!(
            w.inverse().generators,
            vec![
                Generator::negative(3),
                Generator::positive(2),
                Generator::negative(1),
            ]
        );
        Ok(())
    }

    #[test]
    fn generator_inverse_cancels_exactly() -> BctResult<()> {
        let w = BraidWord::new(
            66,
            vec![Generator::positive(41), Generator::negative(41)],
        )?;
        let id = BraidWord::identity(66)?;
        assert!(braid_equivalent(&w, &id, &limits())?);
        Ok(())
    }

    #[test]
    fn artin_relation_is_exact() -> BctResult<()> {
        let left = BraidWord::new(
            66,
            vec![
                Generator::positive(20),
                Generator::positive(21),
                Generator::positive(20),
            ],
        )?;

        let right = BraidWord::new(
            66,
            vec![
                Generator::positive(21),
                Generator::positive(20),
                Generator::positive(21),
            ],
        )?;

        assert!(braid_equivalent(&left, &right, &limits())?);
        Ok(())
    }

    #[test]
    fn distant_generators_commute() -> BctResult<()> {
        let left = BraidWord::new(
            66,
            vec![Generator::positive(2), Generator::negative(50)],
        )?;
        let right = BraidWord::new(
            66,
            vec![Generator::negative(50), Generator::positive(2)],
        )?;

        assert!(braid_equivalent(&left, &right, &limits())?);
        Ok(())
    }

    #[test]
    fn adjacent_generators_do_not_generally_commute() -> BctResult<()> {
        let left = BraidWord::new(
            4,
            vec![Generator::positive(1), Generator::positive(2)],
        )?;
        let right = BraidWord::new(
            4,
            vec![Generator::positive(2), Generator::positive(1)],
        )?;

        assert!(!braid_equivalent(&left, &right, &limits())?);
        Ok(())
    }

    #[test]
    fn arbitrary_word_times_inverse_is_identity() -> BctResult<()> {
        let word = BraidWord::new(
            66,
            vec![
                Generator::positive(1),
                Generator::negative(2),
                Generator::positive(41),
                Generator::positive(20),
                Generator::negative(20),
                Generator::positive(58),
                Generator::negative(7),
            ],
        )?;

        let product = word.concat(&word.inverse())?;
        let id = BraidWord::identity(66)?;

        assert!(braid_equivalent(&product, &id, &limits())?);
        Ok(())
    }

    #[test]
    fn phoenix_plan_restores_verified_braid_action() -> BctResult<()> {
        let total = BraidWord::new(
            66,
            vec![
                // Verified prefix
                Generator::positive(23),
                Generator::positive(24),
                // Unverified candidate suffix
                Generator::positive(1),
                Generator::positive(2),
                Generator::positive(41),
            ],
        )?;

        let plan = plan_phoenix_recovery(&total, 2, &limits())?;

        assert_eq!(
            plan.strategy,
            RecoveryStrategy::RestoreCheckpointThenReverify
        );
        assert_eq!(plan.verified_history.generators.len(), 2);
        assert_eq!(plan.candidate_suffix.generators.len(), 3);
        assert!(braid_equivalent(
            &plan.proof_trace,
            &plan.verified_history,
            &limits()
        )?);

        Ok(())
    }

    #[test]
    fn cognition_memory_commit_fails_closed_without_proof() -> BctResult<()> {
        let mut topology = LabeledTopology::new(66)?;

        // Initially sigma_22 crosses semantic strand 22 (Cognition)
        // with semantic strand 23 (Memory).
        let event = TraceEvent {
            generator: Generator::positive(22),
            claimed_left_strand_id: Some(22),
            claimed_right_strand_id: Some(23),
            purpose: CrossingPurpose::CandidateCommitToMemory,
            actor: ActorClass::Normal,
            proof: GateProof::untrusted(),
        };

        let before = topology.strand_order().to_vec();
        let decision = topology.evaluate_event(&event)?;

        assert!(matches!(decision, GateDecision::Quarantine(_)));
        // Rejected crossings must not mutate the semantic topology.
        assert_eq!(before, topology.strand_order());

        Ok(())
    }

    #[test]
    fn cognition_memory_commit_succeeds_with_green_proof() -> BctResult<()> {
        let mut topology = LabeledTopology::new(66)?;

        let event = TraceEvent {
            generator: Generator::positive(22),
            claimed_left_strand_id: Some(22),
            claimed_right_strand_id: Some(23),
            purpose: CrossingPurpose::CandidateCommitToMemory,
            actor: ActorClass::Normal,
            proof: GateProof {
                certification: Certification::Green,
                evidence_certified: true,
                authority_certified: true,
                capability_authorized: true,
                proof_id: Some("proof-demo-001".to_string()),
            },
        };

        assert_eq!(topology.evaluate_event(&event)?, GateDecision::Allowed);
        assert_eq!(topology.strand_order()[21], 23);
        assert_eq!(topology.strand_order()[22], 22);

        Ok(())
    }

    #[test]
    fn affect_cannot_escape_local_subdomain() -> BctResult<()> {
        let mut topology = LabeledTopology::new(66)?;

        // sigma_16 initially crosses affect strand 16 with cognition strand 17.
        let event = TraceEvent {
            generator: Generator::positive(16),
            claimed_left_strand_id: Some(16),
            claimed_right_strand_id: Some(17),
            purpose: CrossingPurpose::CrossDomainTransfer,
            actor: ActorClass::Affect,
            proof: GateProof {
                certification: Certification::Green,
                evidence_certified: true,
                authority_certified: true,
                capability_authorized: true,
                proof_id: Some("should-still-fail".to_string()),
            },
        };

        assert!(matches!(
            topology.evaluate_event(&event)?,
            GateDecision::Quarantine(_)
        ));

        Ok(())
    }

    #[test]
    fn labeled_topology_tracks_strand_identity_after_crossings() -> BctResult<()> {
        let mut topology = LabeledTopology::new(66)?;

        let event1 = TraceEvent {
            generator: Generator::positive(21),
            claimed_left_strand_id: Some(21),
            claimed_right_strand_id: Some(22),
            purpose: CrossingPurpose::IntraDomain,
            actor: ActorClass::Normal,
            proof: GateProof::untrusted(),
        };
        assert_eq!(topology.evaluate_event(&event1)?, GateDecision::Allowed);

        // Position 22 now contains strand 21, not strand 22.
        assert_eq!(topology.strand_order()[21], 21);

        Ok(())
    }

    // ---- Hardened property tests (deterministic, no external crates) ----
    // A small LCG is enough for a deterministic test RNG; it is not used
    // for any security purpose in this crate.
    struct TestRng(u64);
    impl TestRng {
        fn next_u64(&mut self) -> u64 {
            self.0 = self
                .0
                .wrapping_mul(6364136223846793005)
                .wrapping_add(1442695040888963407);
            self.0 >> 33
        }
        fn below(&mut self, n: usize) -> usize {
            (self.next_u64() as usize) % n
        }
    }

    fn random_word(rng: &mut TestRng, strands: usize, len: usize, negative_only: bool) -> BctResult<BraidWord> {
        let mut gens = Vec::with_capacity(len);
        for _ in 0..len {
            let index = 1 + rng.below(strands - 1);
            let positive = if negative_only { false } else { rng.below(2) == 0 };
            gens.push(Generator { index, is_positive: positive });
        }
        BraidWord::new(strands, gens)
    }

    #[test]
    fn randomized_inverse_identity_500() -> BctResult<()> {
        let mut rng = TestRng(0x9E3779B97F4A7C15);
        for _ in 0..500 {
            let strands = 4 + rng.below(5); // 4..8
            let len = 1 + rng.below(16);
            let word = random_word(&mut rng, strands, len, false)?;
            assert!(
                verify_word_inverse_identity(&word, &limits())?,
                "w * w^-1 != identity for {:?}", word.generators
            );
        }
        Ok(())
    }

    #[test]
    fn randomized_negative_words_inverse_identity() -> BctResult<()> {
        let mut rng = TestRng(0xC2B2AE3D27D4EB4F);
        for _ in 0..200 {
            let strands = 4 + rng.below(5);
            let len = 1 + rng.below(16);
            let word = random_word(&mut rng, strands, len, true)?;
            assert!(verify_word_inverse_identity(&word, &limits())?);
            // Negative-only words must also satisfy the same cancellation:
            // their inverse is the reversed, sign-flipped (positive) word.
            let inv = word.inverse();
            assert!(inv.generators.iter().all(|g| g.is_positive));
        }
        Ok(())
    }

    #[test]
    fn randomized_artin_rewrites_hold() -> BctResult<()> {
        let mut rng = TestRng(0x165667B19E3779F9);
        for _ in 0..200 {
            // Braid relation at a random adjacent pair.
            let i = 1 + rng.below(10);
            let left = BraidWord::new(
                12,
                vec![
                    Generator::positive(i),
                    Generator::positive(i + 1),
                    Generator::positive(i),
                ],
            )?;
            let right = BraidWord::new(
                12,
                vec![
                    Generator::positive(i + 1),
                    Generator::positive(i),
                    Generator::positive(i + 1),
                ],
            )?;
            assert!(braid_equivalent(&left, &right, &limits())?);
            // Distant commutation at random far-apart indices.
            let a = 1 + rng.below(5);
            let b = a + 2 + rng.below(5);
            let l2 = BraidWord::new(12, vec![Generator::positive(a), Generator::negative(b)])?;
            let r2 = BraidWord::new(12, vec![Generator::negative(b), Generator::positive(a)])?;
            assert!(braid_equivalent(&l2, &r2, &limits())?);
        }
        Ok(())
    }

    #[test]
    fn negative_generator_normalization_matches_formula() -> BctResult<()> {
        // For every generator index on 66 strands, sigma_i^-1 alone must
        // produce exactly the Artin inverse images, and sigma_i * sigma_i^-1
        // (and the reverse order) must be the identity.
        for i in 1..66usize {
            let w = BraidWord::new(66, vec![Generator::negative(i)])?;
            let action = BraidAction::from_word(&w, &limits())?;
            // images[i-1] = x_{i+1}; images[i] = x_{i+1}^-1 x_i x_{i+1}
            assert_eq!(action.images()[i - 1].letters(), &[(i + 1) as i32]);
            assert_eq!(
                action.images()[i].letters(),
                &[-(i as i32) - 1, i as i32, (i + 1) as i32]
            );
            let prod = BraidWord::new(
                66,
                vec![Generator::positive(i), Generator::negative(i)],
            )?;
            assert!(verify_word_inverse_identity(
                &BraidWord::new(66, vec![Generator::positive(i)])?,
                &limits()
            )?);
            assert!(braid_equivalent(&prod, &BraidWord::identity(66)?, &limits())?);
        }
        Ok(())
    }

    #[test]
    fn boundary_66_strand_cases() -> BctResult<()> {
        // First generator, last generator, and the domain boundaries
        // 22/23 (cognition/memory) and 58/59 (authority/recovery).
        for i in [1usize, 22, 23, 58, 59, 65] {
            let w = BraidWord::new(
                66,
                vec![
                    Generator::positive(i),
                    Generator::negative(i),
                    Generator::positive(i),
                ],
            )?;
            // w is sigma_i (after adjacent cancellation in the action),
            // so w * w^-1 must still be identity.
            assert!(verify_word_inverse_identity(&w, &limits())?);
        }
        // Braid relation at the top boundary: sigma_64 sigma_65 sigma_64.
        let left = BraidWord::new(
            66,
            vec![
                Generator::positive(64),
                Generator::positive(65),
                Generator::positive(64),
            ],
        )?;
        let right = BraidWord::new(
            66,
            vec![
                Generator::positive(65),
                Generator::positive(64),
                Generator::positive(65),
            ],
        )?;
        assert!(braid_equivalent(&left, &right, &limits())?);
        Ok(())
    }

    #[test]
    fn phoenix_distinguishes_candidate_from_evidence() -> BctResult<()> {
        // total = verified(2) + candidate(3) + evidence(1).
        // Evidence must be returned quarantined and must NOT be inverted
        // or included in the proof trace.
        let total = BraidWord::new(
            66,
            vec![
                Generator::positive(23),
                Generator::positive(24),
                Generator::positive(1),
                Generator::positive(2),
                Generator::positive(41),
                Generator::positive(7), // evidence material, not candidate
            ],
        )?;
        let plan = plan_phoenix_recovery_with_evidence(&total, 2, 3, &limits())?;
        assert_eq!(plan.verified_history.generators.len(), 2);
        assert_eq!(plan.candidate.generators.len(), 3);
        assert_eq!(plan.evidence.generators, vec![Generator::positive(7)]);
        assert!(plan.evidence_quarantined);
        // Proof trace = verified + candidate + inverse(candidate) = 2+3+3.
        assert_eq!(plan.proof_trace.generators.len(), 8);
        assert!(braid_equivalent(
            &plan.proof_trace,
            &plan.verified_history,
            &limits()
        )?);
        assert_eq!(
            plan.strategy,
            RecoveryStrategy::RestoreCheckpointThenReverify
        );
        Ok(())
    }

    #[test]
    fn resource_limits_are_enforced() -> BctResult<()> {
        let tight = Limits {
            max_trace_generators: 2,
            max_free_word_len: 100_000,
            max_total_action_symbols: 500_000,
        };
        let w = BraidWord::new(
            4,
            vec![
                Generator::positive(1),
                Generator::positive(2),
                Generator::positive(1),
            ],
        )?;
        assert!(matches!(
            BraidAction::from_word(&w, &tight),
            Err(BctError::TraceTooLong { .. })
        ));
        Ok(())
    }
}

#[cfg(test)]
mod hardening_v03_tests {
    use super::*;

    fn green_proof() -> GateProof {
        GateProof {
            certification: Certification::Green,
            evidence_certified: true,
            authority_certified: true,
            capability_authorized: true,
            proof_id: Some("proof-1".into()),
        }
    }

    #[test]
    fn strand_count_upper_bound_enforced() {
        assert!(BraidWord::identity(67).is_err());
        assert!(BraidWord::identity(66).is_ok());
        assert!(BraidAction::identity(1000).is_err());
        assert!(LabeledTopology::new(1).is_err());
    }

    #[test]
    fn verified_gate_proof_refuses_incomplete_proofs() {
        assert!(verify_gate_proof(&green_proof(), b"hash", "auth-1").is_ok());
        let mut p = green_proof();
        p.proof_id = None;
        assert!(verify_gate_proof(&p, b"hash", "auth-1").is_err());
        assert!(verify_gate_proof(&green_proof(), b"", "auth-1").is_err());
        assert!(verify_gate_proof(&green_proof(), b"hash", "").is_err());
        assert!(verify_gate_proof(&GateProof::untrusted(), b"hash", "auth-1").is_err());
        // Booleans true but certification not GREEN is still refused.
        let mut p2 = green_proof();
        p2.certification = Certification::Amber;
        assert!(verify_gate_proof(&p2, b"hash", "auth-1").is_err());
    }

    #[test]
    fn checkpoint_roundtrip_and_tamper_refused() -> BctResult<()> {
        let limits = Limits::default();
        let w = BraidWord::new(
            4,
            vec![Generator::positive(1), Generator::positive(2), Generator::positive(1)],
        )?;
        let action = BraidAction::from_word(&w, &limits)?;
        let ckpt = Checkpoint::from_action(&w, &action)?;
        let text = ckpt.to_text();
        let restored = Checkpoint::from_text(&text, &limits)?;
        assert_eq!(restored, ckpt);
        // Tamper with a generator digit: checksum must refuse it.
        let tampered = text.replace("gens=1,2,1", "gens=1,2,2");
        assert!(Checkpoint::from_text(&tampered, &limits).is_err());
        // Tamper with the checksum itself.
        let bad_chk = format!("{}0", &text[..text.len() - 1]);
        assert!(Checkpoint::from_text(&bad_chk, &limits).is_err());
        Ok(())
    }
}
