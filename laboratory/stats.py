"""DARWIN Labs — falsification statistics toolkit.

The statistician's instruments. Pure-python (math/statistics only) so the lab
runs anywhere; scipy-grade tests can be layered on later.

Philosophy: these functions exist to KILL hypotheses, not to prove them.
A discovery that survives everything here earns the right to be tested forward.
"""

from __future__ import annotations

import math
from statistics import mean, stdev
from typing import Iterable, Sequence


def _f(values):
    """Coerce to plain python floats (numpy scalars break statistics.stdev)."""
    return [float(v) for v in values]


def one_sample_t(values: Sequence[float]) -> dict:
    """t-stat for mean(values) != 0. Returns t, n, and approx two-sided p
    via the normal approximation (fine for n >= ~20; conservative warning
    flag returned for small n)."""
    values = _f(values)
    n = len(values)
    if n < 2:
        return {"t": None, "n": n, "p": None, "warning": "n<2"}
    m = mean(values)
    sd = stdev(values)
    if sd == 0:
        return {"t": None, "n": n, "p": None, "warning": "zero variance"}
    t = m / (sd / math.sqrt(n))
    p = 2 * (1 - _norm_cdf(abs(t)))
    out = {"t": round(t, 4), "n": n, "p": round(p, 6), "mean": m}
    if n < 30:
        out["warning"] = "small sample: normal approx, treat p as optimistic"
    return out


def welch_t(a: Sequence[float], b: Sequence[float]) -> dict:
    """Welch two-sample t-test (flagged vs control, e.g. hl_monitor style)."""
    a, b = _f(a), _f(b)
    na, nb = len(a), len(b)
    if na < 2 or nb < 2:
        return {"t": None, "p": None, "warning": "need n>=2 per group"}
    ma, mb = mean(a), mean(b)
    va, vb = stdev(a) ** 2, stdev(b) ** 2
    se = math.sqrt(va / na + vb / nb)
    if se == 0:
        return {"t": None, "p": None, "warning": "zero variance"}
    t = (ma - mb) / se
    df = (va / na + vb / nb) ** 2 / ((va / na) ** 2 / (na - 1) + (vb / nb) ** 2 / (nb - 1))
    p = 2 * (1 - _norm_cdf(abs(t)))
    return {"t": round(t, 4), "df": round(df, 1), "p": round(p, 6),
            "mean_a": ma, "mean_b": mb}


def sign_consistency(k: int, n: int, p_null: float = 0.5) -> dict:
    """Binomial test: k successes out of n (e.g. 'Thursday negative in 12/12
    coins'). Sign consistency across an independent universe is often stronger
    evidence than per-name t-stats."""
    if not (0 <= k <= n):
        raise ValueError("k must be within [0, n]")
    tail = sum(_binom(n, i) * p_null ** i * (1 - p_null) ** (n - i)
               for i in range(k, n + 1))
    return {"k": k, "n": n, "p_one_sided": tail}


def benjamini_hochberg(p_values: Sequence[float], alpha: float = 0.05) -> dict:
    """Multiple-testing control. When DARWIN generates 113 hypotheses a day,
    raw p<0.05 means nothing. BH-FDR tells you which survive contact with
    the multiple-comparison reality."""
    m = len(p_values)
    if m == 0:
        return {"rejected": [], "m": 0, "alpha": alpha}
    order = sorted(range(m), key=lambda i: p_values[i])
    rejected = []
    for rank, i in enumerate(order, start=1):
        if p_values[i] <= (rank / m) * alpha:
            rejected.append(i)
    return {"rejected": sorted(rejected), "m": m, "alpha": alpha,
            "note": f"{len(rejected)}/{m} survive FDR {alpha}"}


def walk_forward_splits(n: int, train: int, test: int, step: int | None = None) -> list[dict]:
    """Anchored walk-forward split indices. Never let the test window touch
    the discovery window — that was hl_monitor H1's in-sample lesson."""
    step = step or test
    splits = []
    start = 0
    while start + train + test <= n:
        splits.append({
            "train": (start, start + train),
            "test": (start + train, start + train + test),
        })
        start += step
    return splits


def sharpe(returns: Iterable[float], periods_per_year: float = 1.0) -> float | None:
    r = list(returns)
    if len(r) < 2:
        return None
    sd = stdev(r)
    if sd == 0:
        return None
    return round(mean(r) / sd * math.sqrt(periods_per_year), 4)


def max_drawdown(equity: Sequence[float]) -> float | None:
    if not equity:
        return None
    peak, mdd = equity[0], 0.0
    for x in equity:
        peak = max(peak, x)
        if peak > 0:
            mdd = min(mdd, x / peak - 1)
    return round(mdd, 6)


def lag_autocorr(values: Sequence[float], lag: int = 1) -> float | None:
    n = len(values)
    if n <= lag + 1:
        return None
    m = mean(values)
    num = sum((values[i] - m) * (values[i - lag] - m) for i in range(lag, n))
    den = sum((v - m) ** 2 for v in values)
    return round(num / den, 5) if den else None


def _binom(n: int, k: int) -> int:
    return math.comb(n, k)


def _norm_cdf(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))
