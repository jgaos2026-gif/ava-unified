"""Scratch prototype: watcher of the watchdog (Step 3, option (a)).

An independent observer that reads pulse-log growth. It is a separate
process from the pulse loop and from the server. It verifies the pulse
log chain, then judges freshness.

Statuses (this watcher is one observer; the STATUS file it writes is
the regress terminus for this prototype -- a human or external check
reads the STATUS file, because a watcher with no watcher is the same
hole one level up):
- HEALTHY: chain verifies and the last entry is younger than
  tolerance x interval.
- DEGRADED: chain verifies, beats are arriving, but the last entry is
  a failure record (verify_ok=false): the loop is alive and reporting
  a broken state.
- STALE: chain verifies but no new entry within tolerance x interval:
  the loop is dead, wedged, or its beats are not reaching the log.
  Absence is the signal -- a process cannot reliably report its own
  death, which is why this check lives outside the loop.
- BROKEN: the pulse log chain itself fails verification, or its tail
  is torn. Fail-closed: a damaged log is never reported healthy.

Wall-clock note: the age check uses wall time as the watcher's own
liveness timeout ("should a beat have arrived by now"). That is a
timeout, not ordering evidence. Ordering, gap, and tamper evidence
always come from seq plus hashes, never from timestamps.

Exit codes: 0 HEALTHY, 1 DEGRADED, 2 BROKEN, 3 STALE.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pulse_log import verify_log


def main() -> int:
    ap = argparse.ArgumentParser(description="Scratch pulse watcher (Step 3a).")
    ap.add_argument("--log", required=True)
    ap.add_argument("--pub", required=True, help="scratch pulse public key file (b64)")
    ap.add_argument("--interval", type=float, default=2.0)
    ap.add_argument("--tolerance", type=float, default=2.0,
                    help="missed-beat tolerance, in beats")
    ap.add_argument("--status", default=None, help="STATUS file path (regress terminus)")
    a = ap.parse_args()

    with open(a.pub) as f:
        pub = f.read().strip()
    rep = verify_log(a.log, pub)

    if rep["torn_tail"] or not rep["ok"]:
        status, code = "BROKEN", 2
        detail = f"torn_tail={rep['torn_tail']} failures={rep['failures']}"
        last_ok = None
        age = None
    elif rep["entries"] == 0:
        status, code = "STALE", 3
        detail = "no entries: loop has never stamped"
        last_ok = None
        age = None
    else:
        last = None
        with open(a.log) as f:
            for line in f:
                last = json.loads(line)
        try:
            stamped = datetime.fromisoformat(last["ts_display"])
            age = (datetime.now(timezone.utc) - stamped).total_seconds()
        except (ValueError, KeyError):
            age = float("inf")
        last_ok = last["verify_ok"]
        if age > a.tolerance * a.interval:
            status, code = "STALE", 3
            detail = f"last beat {age:.1f}s ago > {a.tolerance}x{a.interval}s"
        elif last_ok is False:
            status, code = "DEGRADED", 1
            detail = "last entry is a failure record (loop alive, state broken)"
        else:
            status, code = "HEALTHY", 0
            detail = f"last beat {age:.1f}s ago, chain ok"

    report = {"status": status, "detail": detail,
              "entries": rep["entries"], "last_seq": rep["last_seq"],
              "last_verify_ok": last_ok,
              # DISPLAY-ONLY: the watcher's own clock, never ordering evidence.
              "checked_at_display": datetime.now(timezone.utc).isoformat(),
              "log": a.log}
    print(json.dumps(report, indent=2))
    if a.status:
        tmp = a.status + ".tmp"
        with open(tmp, "w") as f:
            json.dump(report, f, indent=2)
        os.replace(tmp, a.status)
    return code


if __name__ == "__main__":
    sys.exit(main())
