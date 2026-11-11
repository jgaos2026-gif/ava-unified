# Entertainment Brick — v3 prototype (merged 2026-11-02)

**Status: PROTOTYPE, not a Play Store app, not production.** Stdlib only, Python 3.10+.
Run tests: `python3 -m unittest discover -s tests -v`   Walkthrough: `python3 demo.py`

**Merge note (2026-11-02, at John's "Merge em"):** this directory is the
uploaded v3, verified here at 85/85 tests (also under `python -O`) before
filing. It supersedes the earlier 20-test workspace prototype, whose
behaviours (ISRC/UPC validation, date-blocked scheduling, adapter
re-registration gate, Option B money) are covered by v3's own modules and
tests. The pre-merge prototype is kept as
`entertainment-brick-pre-v3-merge.zip`. Tier pricing is decided, not open:
Try free, Starter $19/mo ($190/yr), Pro $49/mo ($490/yr), Full Label
$129/mo ($1,290/yr).

**Improvements (2026-11-02, at John's "Fix all of it") — 92/92 tests:**
`tiers.py` enforces the decided Try caps (3 active bookings, 1 release
prep) and a billing ledger (subscriptions, payments, lapse falls back to
Try gating, data never deleted — no payment processor, no Stripe call);
artist auth_token approval (survives save/load, wrong token refused);
`Brick.load_production()` requires a key and refuses plain-SHA stores;
confirm/cancel run under a lock so two confirms cannot race the same
slot; timed bookings now check real time overlap with travel buffers,
with whole-day block preserved when no times are given. NOT faked:
a live distributor client and a web/Play Store app still need John's
distributor choice, a verified Stripe account, and hosting — those are
external decisions, not code I can invent here.

**Hardening (2026-11-02, at John's "add fix test harden") — 96/96 tests:**
`webhook.py` verifies HMAC signatures with a 300-second timestamp window,
refuses pending/failed events, and cannot double-credit (duplicate event
id or duplicate external_ref returns duplicate, records nothing);
tenant isolation in `Brick` (`get_booking_for` / `approve_booking` refuse
cross-artist access); token rotation (`rotate_artist_token` requires the
current token, old token stops working immediately); V7 wording fixed
(12% is the target rate, actual V7 is the residual plug — the code was
already the plug). Published-library oracle comparison and a real
distributor/Stripe client are still owed — they need an external
library/service choice, not a faked implementation.

## Modules
| file | what it does |
|---|---|
| `core.py` | Artist vault, booking loop (OFFER→DRAFT→APPROVED→CONFIRMED / REJECTED / CANCELLED), messages, expenses |
| `money.py` | 11VT split on full cleared gross; Option B collaborator cuts from V8 only; sealed + verified receipts |
| `ledger.py` | Cleared events tied to bookings; receipt chain per event (no stale-receipt replay); unique external refs |
| `music.py` | Release prep with real ISRC format + UPC/EAN check-digit validation |
| `publisher.py` | Gated hand-off of releases/announcements to Spotify & other services (see below) |
| `secretary.py` | Personality/voice choices for drafted messages and decision prompts |
| `brick.py` | One object owning everything + tamper-evident save/load |

## Rules the code enforces
- No booking confirms without the booked artist's approval (`approve(by=artist)`); every transition logs actor + UTC time.
- Artist rate floor is live-checked at approve and confirm; confirmed bookings can't be rejected (use `cancel`); one confirmed booking per artist per date.
- Money is cleared-only. Gig pay needs a CONFIRMED booking and may not exceed its rate. Receipts are verified (hash + full re-derivation of the split) before any cut. Receipt-only: no bank movement.
- Messages must reference a registered booking/release id.

## Posting to Spotify and similar services — read this
Spotify, Apple Music, YouTube Music, etc. **do not accept uploads from apps**; music reaches them through a **distributor**. So:
- `ExportAdapter` (works now, offline) writes a delivery package (manifest + SHA-256 of audio/artwork) for you to upload to any distributor.
- `DistributorAdapter(name, transport)` calls a `transport(package, asset_paths)` function **you write against your chosen distributor's real API**. This repo ships no distributor client, stores no credentials, and has **not been tested against any live service**.
- Social posts ("announcement" jobs) use the same gate and adapters.
- Gate: release must be distributor-ready → artist approves the exact package hash → `send()` is dry-run by default → live send happens once (job id = idempotency key). Editing the release or swapping a file after approval blocks the send. `SUBMITTED` means handed to the distributor, not live on Spotify.

## Secretary (personality / voice)
Choices: `professional`, `warm`, `blunt`, `hype` (`secretary.choices()`); set per artist with `brick.set_secretary(artist_id, key, name)`.
Written voice only (templates; no AI calls, no text-to-speech). It drafts; it never approves, confirms, pays or sends. Personality changes wording, never facts, and "confirmed" wording is impossible for a booking that isn't confirmed. Drafts are logged only if you call `draft.send(log, sender)`.

## Persistence trust level
`brick.save/load` writes atomically (0600). Without a key the file hash is plain SHA-256: catches corruption and naive edits, **not** a determined forger. Set `JGA_RECEIPT_KEY` (or `key=`) for HMAC-SHA256; a keyed store refuses unsealed/downgraded files. Load never trusts stored state: bookings and publish jobs replay through the real transition + actor rules, receipts are re-derived. Adapters/transports are never saved.

## Still NOT done (needs your decisions or outside services)
Play Store app · AI calls · a real distributor/social API client · ad buying · licensed-agency procurement (union/California/New York work still routes through a licensed franchised agent or attorney) · tier gating (pricing already decided, see merge note) · no pilot artist named in code · audio text-to-speech voice · real authentication of "who is the artist" (identity is object-identity here; the app layer must authenticate).
