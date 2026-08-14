"""DARWIN Labs — falsification statistics toolkit.

The statistician's instruments. Pure-python (math/statistics only) so the lab
runs anywhere; scipy-grade tests can be layered on later.

Philosophy: these functions exist to KILL hypotheses, not to prove them.
A discovery that survives everything here earns the right to be tested forward.

v2 (research-grade):
- t-tests use the actual Student-t distribution (via the regularised
  incomplete beta function), not a normal approximation.
- benjamini_hochberg is the proper step-up procedure.
- newey_west_t: HAC-robust t-stat for autocorrelated return series.
- block_bootstrap_ci: circular block bootstrap confidence interval for the
  mean — the honest way to measure an effect on dependent time series.
- deflated_sharpe: Bailey & López de Prado DSR — deflates the observed
  Sharpe for the number of trials actually run.
- walk_forward_splits supports purge/embargo gaps so test windows never
  touch discovery windows.
"""

from __future__ import annotations

import math
import random
from statistics import mean, stdev
from typing import Iterable, Sequence


def _f(values):
    """Coerce to plain python floats (numpy scalars break statistics.stdev)."""
    return [float(v) for v in values]


def one_sample_t(values: Sequence[float]) -> dict:
    """t-stat for mean(values) != 0 against the Student-t distribution
    (df = n-1). Exact small-sample behaviour; no normal approximation."""
    values = _f(values)
    n = len(values)
    if n < 2:
        return {"t": None, "n": n, "p": None, "warning": "n<2"}
    m = mean(values)
    sd = stdev(values)
    if sd == 0:
        return {"t": None, "n": n, "p": None, "warning": "zero variance"}
    t = m / (sd / math.sqrt(n))
    p = _t_two_sided_p(abs(t), n - 1)
    out = {"t": round(t, 4), "df": n - 1, "n": n, "p": round(p, 6), "mean": m}
    if n < 30:
        out["warning"] = "small sample: p is exact under normality, but check tails"
    return out


def welch_t(a: Sequence[float], b: Sequence[float]) -> dict:
    """Welch two-sample t-test (flagged vs control, e.g. hl_monitor style).
    p from the Student-t distribution at the Welch–Satterthwaite df —
    NOT a normal approximation."""
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
    p = _t_two_sided_p(abs(t), df)
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
    """BH step-up FDR control. When DARWIN generates 113 hypotheses a day,
    raw p<0.05 means nothing.

    Step-up procedure: find the largest rank k with p_(k) <= (k/m)*alpha,
    then reject ALL hypotheses ranked 1..k. (Rejecting each p_i individually
    against its own threshold is NOT the BH procedure and under-rejects in
    a non-contiguous, invalid way.)"""
    m = len(p_values)
    if m == 0:
        return {"rejected": [], "m": 0, "alpha": alpha}
    order = sorted(range(m), key=lambda i: p_values[i])
    k = 0  # largest rank passing the threshold
    for rank, i in enumerate(order, start=1):
        if p_values[i] <= (rank / m) * alpha:
            k = rank
    rejected = sorted(order[:k])
    return {"rejected": rejected, "m": m, "alpha": alpha,
            "note": f"{len(rejected)}/{m} survive FDR {alpha}"}


def walk_forward_splits(n: int, train: int, test: int, step: int | None = None,
                        embargo: int = 0) -> list[dict]:
    """Anchored walk-forward split indices with an optional EMBARGO gap
    between train and test (purged/embargoed CV). Never let the test window
    touch the discovery window — that was hl_monitor H1's in-sample lesson."""
    step = step or test
    splits = []
    start = 0
    while start + train + embargo + test <= n:
        splits.append({
            "train": (start, start + train),
            "embargo": (start + train, start + train + embargo),
            "test": (start + train + embargo, start + train + embargo + test),
        })
        start += step
    return splits


def newey_west_t(values: Sequence[float], lag: int | None = None) -> dict:
    """HAC (Newey–West) t-stat for mean(values) != 0. Ordinary t-stats
    overstate significance on autocorrelated returns; this uses a
    Bartlett-kernel long-run variance. Default lag = floor(n^(1/3))."""
    values = _f(values)
    n = len(values)
    if n < 4:
        return {"t": None, "n": n, "p": None, "warning": "n<4"}
    m = mean(values)
    dev = [v - m for v in values]
    gamma0 = sum(d * d for d in dev) / n
    if gamma0 == 0:
        return {"t": None, "n": n, "p": None, "warning": "zero variance"}
    L = lag if lag is not None else max(1, int(n ** (1 / 3)))
    lrv = gamma0
    for l in range(1, min(L, n - 1) + 1):
        gl = sum(dev[i] * dev[i - l] for i in range(l, n)) / n
        lrv += 2 * (1 - l / (L + 1)) * gl
    if lrv <= 0:
        return {"t": None, "n": n, "p": None, "warning": "non-positive long-run variance"}
    t = m / math.sqrt(lrv / n)
    p = _t_two_sided_p(abs(t), n - 1)
    return {"t": round(t, 4), "n": n, "lag": L, "p": round(p, 6), "mean": m}


def block_bootstrap_ci(values: Sequence[float], block_len: int | None = None,
                       n_boot: int = 2000, seed: int = 42,
                       alpha: float = 0.05) -> dict:
    """Circular block bootstrap CI for the mean. Resamples BLOCKS (wrapped
    circularly) so serial dependence survives the resample — a plain iid
    bootstrap destroys it and produces fantasy-tight intervals.
    Deterministic for a given seed. Default block_len = max(2, int(sqrt(n)))."""
    values = _f(values)
    n = len(values)
    if n < 4:
        return {"mean": mean(values) if n else None, "ci": None, "warning": "n<4"}
    b = block_len or max(2, int(math.sqrt(n)))
    rng = random.Random(seed)
    boots = []
    for _ in range(n_boot):
        total, count = 0.0, 0
        while count < n:
            start = rng.randrange(n)
            for j in range(b):
                total += values[(start + j) % n]
                count += 1
                if count >= n:
                    break
        boots.append(total / n)
    boots.sort()
    lo = boots[int((alpha / 2) * n_boot)]
    hi = boots[min(n_boot - 1, int((1 - alpha / 2) * n_boot))]
    return {"mean": mean(values), "ci": [round(lo, 6), round(hi, 6)],
            "block_len": b, "n_boot": n_boot, "seed": seed}


def deflated_sharpe(sr: float, n: int, trials: int,
                    skew: float = 0.0, kurt: float = 3.0) -> dict:
    """Deflated Sharpe Ratio (Bailey & López de Prado 2014). The probability
    that an observed Sharpe is genuine GIVEN how many strategies were tried.
    A Sharpe of 1.2 after 200 trials is usually noise; this says so."""
    if n < 2 or trials < 1:
        return {"dsr": None, "warning": "need n>=2 and trials>=1"}
    var_sr = (1 - skew * sr + (kurt - 1) / 4 * sr * sr) / (n - 1)
    if var_sr <= 0:
        return {"dsr": None, "warning": "non-positive Sharpe variance estimate"}
    g = 0.5772156649015329  # Euler–Mascheroni
    # expected max Sharpe under the null across `trials` independent trials
    sr_star = math.sqrt(var_sr) * (
        (1 - g) * _norm_ppf(1 - 1 / trials) + g * _norm_ppf(1 - 1 / (trials * math.e))
    )
    dsr = _norm_cdf((sr - sr_star) / math.sqrt(var_sr))
    return {"dsr": round(dsr, 4), "sr_benchmark": round(sr_star, 4),
            "sr_observed": sr, "trials": trials, "n": n,
            "note": "dsr is the probability the Sharpe is real given trials run"}


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


def _norm_ppf(p: float) -> float:
    """Inverse standard-normal CDF (Acklam's rational approximation,
    max abs error ~1.15e-9)."""
    if not 0 < p < 1:
        raise ValueError("p must be in (0, 1)")
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
         3.754408661907416e+00]
    plow, phigh = 0.02425, 1 - 0.02425
    if p < plow:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
               ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    if p > phigh:
        q = math.sqrt(-2 * math.log(1 - p))
        return -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
                ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    q = p - 0.5
    r = q * q
    return (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / \
           (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1)


def _t_two_sided_p(t: float, df: float) -> float:
    """Two-sided p for |T| >= t under a Student-t with df degrees of freedom.
    Equals I_{df/(df+t^2)}(df/2, 1/2) — the regularised incomplete beta."""
    if df <= 0:
        return 1.0
    x = df / (df + t * t)
    return _betai(df / 2, 0.5, x)


def _betai(a: float, b: float, x: float) -> float:
    """Regularised incomplete beta I_x(a, b) via continued fraction
    (Numerical Recipes). Accurate to ~1e-10."""
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    lbeta = math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
    front = math.exp(lbeta + a * math.log(x) + b * math.log(1 - x))
    if x < (a + 1) / (a + b + 2):
        return front * _betacf(a, b, x) / a
    return 1 - front * _betacf(b, a, 1 - x) / b


def _betacf(a: float, b: float, x: float, max_iter: int = 200, eps: float = 3e-12) -> float:
    qab, qap, qam = a + b, a + 1, a - 1
    c, d = 1.0, 1 - qab * x / qap
    if abs(d) < 1e-30:
        d = 1e-30
    d = 1 / d
    h = d
    for m in range(1, max_iter + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1 + aa * d
        if abs(d) < 1e-30:
            d = 1e-30
        c = 1 + aa / c
        if abs(c) < 1e-30:
            c = 1e-30
        d = 1 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1 + aa * d
        if abs(d) < 1e-30:
            d = 1e-30
        c = 1 + aa / c
        if abs(c) < 1e-30:
            c = 1e-30
        d = 1 / d
        delta = d * c
        h *= delta
        if abs(delta - 1) < eps:
            break
    return h
