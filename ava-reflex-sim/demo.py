"""Demo for the minimal reflex simulator — SIMULATION ONLY / RESEARCH ONLY.

Runs one fixed-seed mixed campaign through both paths (REFLEX and FULL)
and prints the metrics comparison. The printed output is the canonical
deterministic metrics JSON, so running this demo twice produces
byte-identical output (resource cost — real wall time / peak RSS — is
measured separately and is NOT printed, because real timing varies
run to run).

No medical claims: this is a software-only simulation. Latency numbers
are simulated software latencies, not hardware/neural timing. Benchmark
thresholds are NOT clinical requirements. Power cost is estimated, not
measured.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from reflex_sim import canonical_metrics_json, compare_paths  # noqa: E402

FIXED_SEED = 42
CAMPAIGN_NAME = "mixed-demo"


def main() -> None:
    result = compare_paths(CAMPAIGN_NAME, seed=FIXED_SEED)
    comparison = result["comparison"]
    print("Minimal reflex simulator — SIMULATION ONLY / RESEARCH ONLY")
    print("Fixed-seed mixed campaign: seed=42, all eight fault types, "
          "100 synthetic frames per path.")
    print("Success criterion (spec section 7.3): lower latency WITHOUT "
          "silent unsafe-state escape, WITHOUT bypassing evidence, and "
          "WITHOUT the reflex certifying its own repair.")
    print()
    print("Comparison (FULL path vs REFLEX path, identical campaign):")
    print(json.dumps(comparison, sort_keys=True, indent=2))
    print()
    print("REFLEX path metrics (canonical, deterministic):")
    print(canonical_metrics_json(result["reflex"]))
    print()
    print("FULL path metrics (canonical, deterministic):")
    print(canonical_metrics_json(result["full"]))
    print()
    print("Headline: reflex median "
          f"{comparison['reflex_median_ms']} ms vs full median "
          f"{comparison['full_median_ms']} ms; "
          f"reflex silent escapes {comparison['reflex_silent_escapes']}, "
          f"full silent escapes {comparison['full_silent_escapes']}; "
          f"reflex certified resumes "
          f"{comparison['reflex_certified_resumes']} (reflex never certifies), "
          f"full certified resumes {comparison['full_certified_resumes']}.")
    print("Resource cost (wall time / peak RSS) is measured per run and "
          "excluded from this deterministic output; power is an estimate "
          "label only, never a measured claim.")


if __name__ == "__main__":
    main()
