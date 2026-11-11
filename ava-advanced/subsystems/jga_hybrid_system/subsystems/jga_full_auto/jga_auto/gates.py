"""Task Error Rate gate + Phase A/B logic (Amendment 13, build item 2).

Nothing ships as "AI end to end" until its error rate is measured on
reviewed samples. Phase A = supervised: every sampled output is reviewed
and scored. Phase B = full auto, unlocked only when:
  - at least ERROR_RATE_MIN_SAMPLES reviewed samples exist, AND
  - measured error rate <= ERROR_RATE_THRESHOLD.
Below that bar, the system stays in Phase A no matter who asks.
"""
from . import config


class ErrorTracker:
    def __init__(self):
        self.samples = []  # list of bool: True = error found on review

    def record(self, error_found: bool):
        self.samples.append(bool(error_found))

    @property
    def count(self) -> int:
        return len(self.samples)

    @property
    def error_rate(self) -> float:
        if not self.samples:
            return 0.0
        return sum(self.samples) / len(self.samples)

    def phase_b_ready(self, threshold=None, min_samples=None) -> bool:
        threshold = config.ERROR_RATE_THRESHOLD if threshold is None else threshold
        min_samples = config.ERROR_RATE_MIN_SAMPLES if min_samples is None else min_samples
        return self.count >= min_samples and self.error_rate <= threshold

    def report(self) -> str:
        ready = self.phase_b_ready()
        return (
            f"samples={self.count} errors={sum(self.samples)} "
            f"rate={self.error_rate:.3f} threshold={config.ERROR_RATE_THRESHOLD} "
            f"min_samples={config.ERROR_RATE_MIN_SAMPLES} "
            f"phase_b_ready={ready}"
        )
