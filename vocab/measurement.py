"""Descriptive statistics. Wilson (1927), doi:10.1080/01621459.1927.10502953."""
from math import sqrt


def wilson_interval(successes: int, trials: int) -> tuple[float, float] | None:
    """95% Wilson score interval for independent Bernoulli trials.

    Repeated reviews and curated items violate random-sampling assumptions;
    this interval describes sampling uncertainty, not language proficiency.
    """
    if trials < 0 or successes < 0 or successes > trials:
        raise ValueError("Require 0 <= successes <= trials")
    if trials == 0:
        return None
    z = 1.959963984540054
    p = successes / trials
    denominator = 1 + z * z / trials
    centre = (p + z * z / (2 * trials)) / denominator
    margin = z * sqrt(p * (1 - p) / trials + z * z / (4 * trials * trials)) / denominator
    return max(0.0, centre - margin), min(1.0, centre + margin)
