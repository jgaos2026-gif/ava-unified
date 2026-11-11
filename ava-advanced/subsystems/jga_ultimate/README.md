# JGA Ultimate System — one entry point, kept systems combined

Built 2026-11-03 at John's "Fix it all every File we keep upgrade combine
to one ultimate at system" — from the files already verified here.
**Originals are untouched.** This folder holds copies; nothing was moved,
deleted, or trashed to make it.

## What is inside (copies)
- `subsystems/jga_os/main.py` — JGA Enterprise OS core (clients, quotes,
  jobs, 35/65 gates, hash-chained ledger, AVA rules stub). Upstream
  README says v0.1.0 Local Foundation, not production.
- `subsystems/brick1/allocator_11vt.py` — Brick 1 11VT, receipt-only.
- `subsystems/entertainment/money.py` — Entertainment Brick money,
  Option B (cut from V8), receipt-only.
- `subsystems/ava/` — AVA merged page (v3 branding + simulation mode)
  and healthcheck. No LLM wired in; no consciousness claim.
- `subsystems/stripe/` — corrected Stripe PaymentIntent script
  (test-key first, no key shipped).

## What is NOT inside, and why
- **AVA hybrid prototype** — separate generation, would mix two AVAs.
- **Windows CONTROL_ROOM files** (`server.ps1`, `ava.ps1`,
  `Runtime/status.json`, etc.) — they do not exist in this workspace
  and have never been vetted here. Their status crash is still
  unconfirmed; do not assume this package fixes that system.
- **Any live Stripe, bank, or AI connection** — none is connected.
  Stripe OAuth (Jaysgraphicarts@gmail.com) is still uncompleted.
- **Any real customer data** — the test seed used during verification
  was wiped before zipping; `data/` ships empty.

## Commands
```
python ultimate.py status     # unified status, JSON
python ultimate.py automate   # one governed automation cycle
python ultimate.py split --system brick1 --cents 35000 \
    --stage DEPOSIT_CLEARED_35 --job-id job-001
python ultimate.py split --system entertainment --cents 100000 \
    --stage gig-pay-cleared
```

## Governed automation — read this before calling it "full auto"
`automate` checks the ledger, probes AVA screening + calculator,
confirms untrusted payloads are still blocked, and writes
`data/last-cycle.json`. It **never** moves money, sends a message,
contacts anyone, releases a file, changes a price, or publishes
anything. Jobs awaiting a deposit or delivery are listed under
`needs_owner`, never advanced. That boundary is Amendment 13 and the
JGA OS authority model (owner is final authority), not a gap to patch
around. A job advances only when a human records a verified cleared
payment with a real provider reference.

## Fixes carried in
- Stripe amount bug (string * 100) fixed; automatic_payment_methods added.
- AVA merged shutdown bug fixed upstream; simulation mode has no fake scores.
- Entertainment V7: 12% is a target, V7 is the residual plug.
- JGA OS default-PIN trap: no config.json is shipped here, and the
  loader deletes any default config the upstream import creates, so
  this package never keeps a default PIN. Change the PIN before any
  real use of the upstream server.

## Verified here
- Ultimate tests: **6/6** (`python -m unittest discover -s tests`)
- Brick 1 split: $350 cleared deposit balances, receipt-only.
- Entertainment split: $1,000 cleared gig balances, receipt-only.
- Automation cycle: money_moved=false, messages_sent=0, files_released=0,
  unpaid job left untouched under needs_owner.
- This package does NOT start the AVA services, the JGA OS web server,
  or any Stripe call on its own. Start those deliberately, on the
  machine they belong on.
