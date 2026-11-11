# AVA Sovereign — Connection to Talent Agent Plus and Jay's Graphic Arts

**Owner's hard rules (2026-11-09 ~02:16 CST): NO KEYS, LOCAL ONLY, COMPLETELY SOVEREIGN.**
This brief states what the connection IS under those rules — what she carries locally,
what she can read keyless, what a live two-way link would need and why it is OUT, and
how each connection behaves offline vs online. Nothing here requires a key.

**The two apps (both live on Render, free plan, Python 3, Oregon):**
- **Talent Agent Plus** — https://talent-agent-plus.onrender.com — the separate public
  Play Store app (artist system: Find, Book, Collect, Communicate; tiers; Discover;
  Design · JGA; AVA tab; Social tab; BCT tab; Money tab). Repo:
  https://github.com/jgaos2026-gif/talent-agent-plus (main @ b071c79 — includes the
  Supabase store wiring). Workspace package: `~/workspace/your_files/talent-agent-plus-render/`.
- **Jay's Graphic Arts** — https://jays-graphic-arts.onrender.com — Brick 1 storefront
  (6 packages, 12 services, Vistaprint pricing, orders, AVA tab). Repo:
  https://github.com/jgaos2026-gif/jays-graphic-arts-store (main @ 52bea46 — includes
  the Supabase store wiring). Workspace package: `~/workspace/your_files/jays-graphic-arts-render/`.
- Free-tier note: both instances sleep after ~15 min idle; a cold request can take
  50+ seconds to wake. That delay is the host, not an error — say so when it happens.
- The hosted artifact apps (ts-spaces `talent-agent-plus` / `jay-s-graphic-arts`) are
  the same products with a different runtime; the Render repos are the canonical
  public endpoints below. The artifact apps have NO public REST API — their public
  view is UI-only (showcases, gig board, tiers/prices, catalog).

---

## 1. What she carries locally (no connection needed — loaded from the knowledge pack)

AVA Sovereign holds both apps' rules, numbers, and behaviors in her local braid, so
she can answer and work from them with zero connection:

**Both apps**
- 11VT split + Option B collaborator rule (cuts out of V8 only, named payee, may not
  exceed current V8); demo anchor $1,000 cleared + $40 cut → V8 $160.
- Tiers: Try FREE / Starter $19 or $190 / Pro $49 or $490 / Full Label $129 or $1,290;
  each tier includes those below; gates ON at every tier; data integrity/security free
  at every tier.
- Trial rule: 7 days, one time per email, ever (claim recorded permanently; delete +
  re-register refused; claim survives export/restore).
- Legal gate: tool for artist self-representation, NOT a licensed talent agency; union
  & CA/NY bookings via licensed franchised agent/attorney; SAG-AFTRA cap 10%; DSP
  payout lag 2–3 months; Coogan Law for minors; AI calls disclosed + recording
  consent; no cold-call blasts; Spotify/Apple need a distributor (SUBMITTED ≠ live).
- Privacy: per-person isolation server-side; signed-out views show only opt-in
  showcases, the open gig board, tiers/prices, and the public catalog; Stripe account
  details + discount codes are blanked for non-owners; roster never leaks.
- AVA behaviors: chat from live records, mic + spoken replies, user-creatable avatar,
  adaptive personality (style notes), braided memory through the six-layer gate,
  operator pass + Approvals, Prove-it panel, semantic screen, evidence replay,
  Thought/Decision Records. She never claims to have booked/sent/called/paid.
- Owner's-room rules: freedom + private media ONLY in owner's mode; secrecy from
  everyone but John (existence, contents, counts, metadata — never shown, mentioned,
  or confirmed to any non-owner).
- Money honesty: Stripe is test mode until John finishes Dashboard verification; no
  real money moves; `banking_execution: NONE_LEDGER_RECEIPT_ONLY`; receipts only.
- Unified public email: **jgaos2026@gmail.com**. Location: Peoria, Illinois.
  Business phone: (779) 396-6934.

**Talent Agent Plus only**
- Opportunity kinds (gig, audition, casting, venue, producer, collaborator, theatre,
  dance, film, voice_acting, commercial); expense categories (travel, taxes,
  advertising, pay, wardrobe, cds, online); booking states (DRAFT, OFFERED, APPROVED
  artist-only, CONFIRMED, COMPLETED, CANCELLED, REJECTED).
- Discover: showcase opt-in only (default private; unpublish removes at once); public
  listings show only showcase name, skills, location, bio, tier, samples; samples
  labeled "provided by the artist," never verified as client work, never invented.
  Connect = pending request with seeker contact they choose to share for that artist
  only — not a booking, contract, or sent message.
- Design · JGA: CD cover art, posters, business cards, event tickets, flyers, social
  graphics, any JGA package; upload or prompt; briefs stored verbatim (no blocking
  blood/guns/etc.); discounts Starter 30% / Pro 40% / Full Label 50% (codes ARTIST30 /
  ARTIST40 / ARTIST50); order flow request → in design → proof → approved → delivered.
- Vistaprint formula: (cost × 1.20 + delivery at cost) × 1.05; $50 + $8 → $71.40.
- Twilio BYOT: each artist creates their OWN Twilio account + number; the app pays
  for no calls; stores number + optional Account SID last-4 only, never password/Auth
  Token; the app dials nothing.
- Tier social allowances (UNVERIFIED — Rumi's ladder, John unconfirmed): Try 1 post /
  1 video / drafting-only; Starter 5 / 3 / 1 campaign; Pro 15 / 10 / 3; Full Label
  unlimited. Ad spend always the artist's to Meta.
- Profitability suite: trial day-5/day-7 reminders, failed-payment recovery (pauses,
  never deletes), referrals (free month), retention flags, owner money dashboard.
- Hourly AVA automation cron (96 successful hourly runs over 92 distinct hours,
  Nov 5 → Nov 9, zero refusals — scheduler-mark proof complete).

**Jay's Graphic Arts only**
- Packages (published site): Quick Creative Help from $75, Logo Launch from $350,
  Business Brand from $750, Brand & Social Launch from $1,250, social design from
  $299/mo, Design Subscription $499/mo. Terms: 35% to start, balance before final
  clean files, proof approved before anything is final. Clean files only after final
  payment + proof approval; before that, visible MOCK-DRAFT mark.
- Order states: REQUESTED → IN_DESIGN → PROOF_SENT → client approves → PROOF_APPROVED
  → DELIVERED. Vistaprint formula as above (same formula, both apps).
- JGA owner-side bookkeeping (Brief C): tax-check gate (DELIVERED blocked until the
  owner marks the check done — owner's check, not tax advice); legal-docs checklist
  (IL registration, EIN letter, S-corp proof, D-U-N-S, Good Standing, bank proof) all
  starting NEEDS_UPLOAD, SHA-256 on upload; monthly close report (sales tax collected
  reported as NOT separately recorded); receipt log; generic CSV bank import — bank
  is **Chime**, NOT Bluevine. Loaded facts CONFIRMED BY JOHN (2026-11-05, "Comfirm"):
  EIN exists; D-U-N-S exists; Good Standing through 2027; S-corp treatment — confirmed
  by John himself, NOT independently verified (no document seen).
- Brick 1 shop calls (Twilio, PARKED): 12 verified shops, 5/day nearest first,
  disclosed-AI scripts, call log, one follow-up after 3 days. Day 1: Curtis Salons
  (309) 231-8785, Winter's Barber Shop (309) 672-2573 (Tue/Thu/Fri/Sat only), Hale
  Beauty Salon (309) 673-8138, Que For You (309) 981-5105, Kak Barber Shop
  (309) 673-9600. Day 2: West Town Tap, J+B Studio, Kelly's Barber Shop, Jimador,
  High Def Barber Shop. Day 3: Jr's Kitchen, Dang Boba (food pitch). Full pack:
  `~/workspace/goals/jay-s-graphic-arts-brick-1/files/overnight-sell/ava-shop-calls.md`.
  Callback number: (779) 396-6934. **None contacted yet. Calls are spoken messages
  with a recorded reply, not live two-way conversation.**

---

## 2. What she can read keyless (public endpoints — verified in the Render server code)

These are plain unauthenticated GETs on the live Render apps. No token, no key, no
sign-in. They return ONLY public data — that is enforced server-side, not by trust.

**Talent Agent Plus — `https://talent-agent-plus.onrender.com`**
| Endpoint | Returns (public) | Notes |
|---|---|---|
| `GET /api/health` | `{ok, product, version, banking_execution: NONE_LEDGER_RECEIPT_ONLY, store, supabase_configured}` | Liveness + store mode. Last verified live 2026-11-09 ~00:44: `"store": "supabase"`, `"supabase_configured": true` |
| `GET /api/tiers` | Tier list with prices/features | Discount codes are scrubbed from public tier feature strings (a leak was found and fixed 2026-11-05) |
| `GET /api/discover/artists?skill=&location=` | Opt-in showcases only | Empty unless an artist published a showcase; roster never leaks |
| `GET /api/discover/samples` | Public samples from opt-in showcases | Labeled "provided by the artist" |
| `GET /` + `/frontend/*` | The public web view (app description, showcases, gig board, tiers, tour, manual) | Keyless page read |

**Jay's Graphic Arts — `https://jays-graphic-arts.onrender.com`**
| Endpoint | Returns (public) | Notes |
|---|---|---|
| `GET /api/health` | `{ok, product, version, banking_execution, stripe_mode: "test", store, supabase_configured}` | Last verified live 2026-11-09 ~00:44: `"store": "supabase"` |
| `GET /api/public` | Full public catalog: 6 packages, 12 services, print products, process, terms | No sign-in |
| `GET /api/stripe/links` | Test-mode Stripe payment links (full / 35% deposit / 65% balance per package) | Test mode only; no real money moves |
| `GET /` + `/frontend/*` | The public storefront | Keyless page read |

**Keyless-read rules for AVA Sovereign:**
- Read only these endpoints (plus the public pages). Copy URLs verbatim from tool
  output; never construct or guess URLs.
- Label everything read this way with **when it was fetched** (the Render free tier
  sleeps; a cold read can be 50+ seconds old before it even starts). Never present a
  cached read as live.
- Public reads return public data only. If a read returns empty (no showcases, no
  orders), that is the true state — never invent a record to fill the gap.
- A failed or incomplete text fetch does NOT establish a login barrier, a failure in
  the live app, or the absence of an option. Report only what the fetch actually showed.

**What is NOT keyless (do not attempt without the owner's live session):**
- TAP: `/api/store/verify` (owner only), `/api/artists/:id/calendar|agenda|summary`,
  `/api/shop/:id`, `/api/campaigns`, `/api/productions`, `/api/tasks`, `/api/calls`,
  `/api/opportunities`, `/api/connect-requests`, `/api/payments`, `/api/branding`
  (all take a session token and refuse without a valid one), and every POST
  (setup-owner, logins, bookings, shop orders, campaigns, trials).
- JGA: `/api/store/verify` (owner only), `/api/orders`, `/api/orders/:id` (token-gated),
  and every POST (setup-owner, logins, clients, orders, proof approval, payments).
- The hosted artifact apps expose no public REST API at all; their public view is
  UI-only. Do not probe them for endpoints that do not exist.

---

## 3. What a live two-way data link would need — and why it is OUT

A live link (AVA Sovereign reading private records from, or writing to, the two apps
or the shared chain) would need one of the following. **All are OUT under the owner's
no-keys rule.** This section documents the path so John can reverse it in his own
words if he ever wants to — it is not a request to build it.

| What the link needs | Why it is OUT |
|---|---|
| The Supabase **service-role key** for project jga-apps (the only key that can call `ava.append_memory` / `ava.verify_memory_chain` and the `tap_*` / `brick1_*` RPC wrappers — they are revoked from anon/authenticated) | It is a master credential. The sovereign app holds no keys by John's order. The migration + client code already exist and are proven (`001_ava_unified.sql`, `supabase_mirror.py`, 67/67 suite; seed + live write→recall PROVEN 2026-11-05), but the key must never be pasted into this app without his explicit reversal. |
| An **owner session token** from either app (24h TTL, `secrets.token_hex(32)`) | Tokens belong to John's live sign-in; they expire; using one would let the app act as John. Owner actions (store verify, TOTP, legal-doc uploads, CSV import, monthly close, the owner's room itself) have never been driven except under his real sign-in. |
| An **artist/client session token** | Same problem, smaller scope — and per-person isolation means a token only ever sees its own records. |
| A **Gemini API key** for a live model brain | Out by the same no-keys rule. The sovereign app's brain is built-in only. |
| A **Twilio SID + Auth Token** for dialing | Out; env vars on the dialing machine only; trial expires ~Dec 5, 2026; account sign-in blocked on John's own checkbox click. |
| **Stripe live mode** for real charges | Out; test mode until John finishes Dashboard verification AND picks which of the two accounts to finish (Dashboard "Jays graphic arts" acct_1UYM5V2K0jIcRFLl vs sandbox acct_1UY8LtRyup299Dc0). Deferred to Tue Nov 10, 2026 by his word. |

**Consequences of OUT (state them plainly, never work around them):**
- Her memory lives in this app alone. She does NOT share memory live with the TAP/JGA
  app AVAs or with ava-merged. The shared chain is live on Supabase and holds 5
  entries from the 2026-11-05 seed — she cannot read or write it from here.
- She cannot see private records (bookings, orders, messages, money, AVA threads) in
  either app. She knows the rules and the public catalog; she does not know who
  booked what.
- She cannot write to either app. Anything she drafts for the apps (outreach, a
  booking, a payment record, a design order) goes to the owner's Approvals here, and
  John enters it in the app himself — or reverses the no-keys rule and tells her how.
- She cannot dial, charge, or deploy. Call prep, payment-link lookup (public test
  links), and Studio drafts are the limits.

---

## 4. Offline / online behavior per connection

**Online (internet available):**
- TAP: keyless reads of `/api/health`, `/api/tiers`, `/api/discover/artists`,
  `/api/discover/samples` + public pages. Fresh data, labeled with fetch time.
  Keyless web search for anything else (public pages only, sources named).
- JGA: keyless reads of `/api/health`, `/api/public`, `/api/stripe/links` + public
  pages. Fresh data, labeled with fetch time.
- Research queue: worked in order; findings stored as memory links with provenance
  (source address + when read); unanswered items stay queued and are reported as
  unanswered, never guessed.
- The app shows online state clearly; every fetched fact carries its fetch time.

**Offline (no internet):**
- Both connections go quiet. No error, no retry storm, no fake data.
- She works from her **local braid**: both apps' rules, tiers, prices, catalogs,
  shop-call pack, and the last fetched public data — every cached fact labeled
  with its fetch time and marked **stale — verify when back online** before acting
  on it.
- Research questions go to the queue. Ideas, Studio drafts, notes, records, and
  memory writes all keep working locally. The operator pass runs on local data only
  and says so.
- When back online she works the queue first, then refreshes the public reads, and
  tells the owner what changed (if anything) — plainly, without re-pitching.

**Never, in either mode:** present cached data as live; present a public read as a
private record; claim she booked/sent/called/paid anything; write to either app;
use a key, token, or session that is not hers to use; or treat a failed fetch as
proof that something does not exist.

---

## 5. If John ever reverses the no-keys rule (his words only)

The path is already built and proven; it only needs his explicit yes, in his own
words, naming what to connect:
1. Shared memory: apply nothing new — migration `001_ava_unified.sql` is already live
   on jga-apps; the client is `supabase_mirror.py` (hash equality proven byte-for-byte);
   the app would need the service-role key supplied by John through a secure entry,
   never pasted in chat. Then prove a live cross-app write→recall through the app.
2. App records: owner session token (his live sign-in) for `/api/store/verify` and the
   token-gated reads; or the Render repo port of the shared-memory client (repos have
   the env; hosted artifacts have the client but no env — that port is scoped, not
   started).
3. Live model: a Gemini key through the same secure path; model name is John's lock
   (gemini-3.5-flash was a test choice only).
4. Dialing: John clicks the Twilio checkbox himself → agent buys the 309 number,
   creates the 2 TwiML Bins → John approves the $20 upgrade → test call to his own
   number → Day 1 calls.
5. Stripe: John picks the account, finishes Dashboard onboarding (his hands only —
   legal name, DOB, SSN/ITIN or EIN as the account type dictates, Chime payout bank),
   then approves live mode.

Until then, this brief stands as written: **local rules, keyless public reads, no
writes, no keys, no cloud memory. Sovereign means she answers from what she holds,
and says plainly what she does not hold.**
