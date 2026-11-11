# Jay's Graphic Arts — Fully Automated (Python 3 + Supabase + VS Code)

**What this is:** the Amendment 13 pipeline as runnable Python 3 code.
AI runs outreach, design, revisions, delivery, invoicing, follow-up.
Humans stay at **approval gates only, never in production** — the client
approves at gates, John holds exception review, consent stays human.

**Status:** Phase A (supervised) by default. The code enforces every gate
in software, so a job physically cannot skip the deposit gate, ship clean
files before final payment + approval, or exceed its revision count.
Phase B (full auto) unlocks only when the measured Task Error Rate passes
the threshold John sets — see `jga_auto/gates.py`.

## Layout

```
main.py                  # CLI: --demo runs one sample job end to end
jga_auto/
  config.py              # BUSINESS_NAME + env settings (rename = one line)
  pipeline.py            # Job state machine + gate enforcement
  drafting.py            # Drafting engines (mock today, API tomorrow)
  taste.py               # Taste corpus loader (Personality strand)
  books.py               # Invoices + SHA-256 receipts (with 11VT splits)
  allocator_11vt.py      # 11VT receipt-only reserve allocator (no bank movement)
  gates.py               # Task Error Rate + Phase A/B logic
  supabase_store.py      # Supabase backend (lazy import; needs keys)
  local_store.py         # Local JSON store (no keys needed; trial + first jobs)
data/taste_corpus.json   # Taste corpus v2 (house logo + standard + 4 directions)
data/store/              # Local jobs + invoices (created on first save)
sql/001_brick1_tables.sql# Supabase migration (brick1_* tables)
tests/test_pipeline.py   # Gate + error-rate tests (stdlib unittest)
tests/test_local_store.py# Store round-trip + corpus tests
```

## Quickstart (Windows, VS Code)

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m unittest discover -s tests -v   # gates must pass before use
python main.py --demo                     # one sample job, mock drafting
python main.py --new --customer "Shop" --package "Quick Creative Help" --brief "price-list card"
python main.py --list                     # stored jobs
python main.py --advance job-001 deposit # one legal step at a time; gates enforced
```

**No keys needed to run a job.** Jobs + invoices persist locally under
`data/store/` until Supabase is connected. The demo stores itself there
too. No command moves money: `--advance … deposit` and `--advance … pay`
only record what John confirms actually cleared.

Copy `.env.example` to `.env` and fill in keys on your machine only.
**Never paste keys into chat.** Without keys, the demo runs in mock mode
and the Supabase steps report SKIPPED instead of failing.

## Supabase

Tables live in your existing project (default: trench-city-oasis) under the
`brick1_` prefix, so they never collide with the `stitch_*` tables.
Apply `sql/001_brick1_tables.sql` in the Supabase SQL editor, then set
`SUPABASE_URL` + `SUPABASE_KEY` in `.env`. Server-side use takes the
service-role key; that key never ships to a client.

## VS Code

Open this folder in VS Code. `.vscode/` ships launch + task configs:
Run and Debug → "Demo pipeline", or Tasks → Run Task → "Run tests".

## 11VT receipt-only allocation (added 2026-10-29)

On a delivered job only, `books.build_invoice()` binds two reserve
splits into the invoice SHA-256 receipt: one for the cleared 35%
deposit, one for the cleared 65% final balance. The allocator
(`jga_auto/allocator_11vt.py`) refuses any other stage — never a
contract price before funds clear — and `build_invoice()` refuses
unless both deposit_cleared and final_paid are true.

Every split carries, in the data itself:
`banking_execution: NONE_LEDGER_RECEIPT_ONLY`,
`tax_disclaimer: INTERNAL_RESERVE_TARGETS_NOT_STATUTORY_TAX_LIABILITY`,
`v7_plug_notice: ABSORBS_PENNY_ROUNDING_DELTAS`.
V10 is Internal Capital Reserve only — no succession trust is assumed.
V7 absorbs penny-rounding deltas, so splits always balance, and V7 is
not always exactly 12%. This moves NO bank funds, opens NO sub-accounts,
and does NOT claim Bluevine moves money. It is a ledger receipt policy.

Verify: `python -c "from jga_auto.allocator_11vt import allocate_cleared_payment; r = allocate_cleared_payment(575000, 'DEPOSIT_CLEARED_35', 'JOB-TEST'); assert r['balanced'] and r['banking_execution'] == 'NONE_LEDGER_RECEIPT_ONLY'; print('11VT RECEIPT ALLOCATOR: VERIFIED PASS')"`

## The gates (enforced in code, not just documented)

1. No production before a **cleared 35% deposit**.
2. No clean files before **final payment + client approval**.
3. Revision counts enforced per package (Logo 2, Brand 3, video 2).
4. No "AI end to end" claim before the **Task Error Rate gate** passes.

## Open decisions (John's, not assumed)

- **Taste corpus:** now v2 — house logo + operating standard + the 4
  portfolio directions (Street Bold, Quiet Premium, Community Warmth,
  Digital Rhythm). Directions are capability directions, not client
  work; real pieces join only with the client's permission.
- **Quick Creative Help:** added at $75 (site price, from $75) with a
  2-round revision limit, so tomorrow's walk-in jobs can run in it.

- **Business name:** you said "Jace" on Oct 28; the code uses
  `BUSINESS_NAME = "Jay's Graphic Arts"` in `jga_auto/config.py`.
  If Jace is the new name, change that one line.
- **Drafting engine:** `DRAFTING_ENGINE=mock` today. The API engine is a
  stub until you pick which drafting API to pay for (compute cost is the
  binding constraint, per Amendment 13).
- **Error-rate threshold:** `JGA_ERROR_THRESHOLD` (default 0.05) + minimum
  20 reviewed samples before Phase B.
- **Integration bridge:** how intake/deposit events reach this pipeline
  (inbox reader, daily export, or owned form + Stripe flow).
