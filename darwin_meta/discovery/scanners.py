"""DARWIN Discovery — Anomaly Scanners

Deterministic sweeps over real market data. Each scanner emits Anomaly
records carrying VERIFIED statistics. Scanners never decide significance:
all p-values from all scanners go into ONE global Benjamini–Hochberg
step-up in the discovery loop. trials_tested = every test run, whether it
survived or not.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from statistics import mean

from laboratory.stats import welch_t, lag_autocorr

WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


@dataclass
class Anomaly:
    scanner: str
    target: str              # e.g. "IWM" or "BASKET"
    signature: str           # stable dedupe key, e.g. "weekday:IWM:Tuesday"
    description: str
    effect: float
    unit: str
    n: int
    t: float | None
    p: float | None
    window: tuple[str, str]  # data window actually used
    extra: dict = field(default_factory=dict)
    # filled in by the discovery loop after global FDR control:
    fdr_significant: bool = False
    trials_tested: int = 0


def _returns(series: list) -> tuple[list[datetime], list[float]]:
    dts, rets = [], []
    for (d0, c0), (d1, c1) in zip(series, series[1:]):
        if c0:
            dts.append(d1)
            rets.append(c1 / c0 - 1)
    return dts, rets


def _window(dts: list[datetime]) -> tuple[str, str]:
    return (dts[0].date().isoformat(), dts[-1].date().isoformat()) if dts else ("", "")


def scan_weekday_effects(data: dict, min_n: int = 20) -> list[Anomaly]:
    """Daily series × weekday: is this weekday's mean return different from
    all other weekdays? Welch t vs the matched rest-of-week control.
    Also scans the equal-weight basket of all series."""
    if data.get("freq") != "1d":
        return []
    out = []
    per_series = {}
    for name, series in data["series"].items():
        per_series[name] = _returns(series)

    def sweep(label: str, dts, rets) -> None:
        for wd in range(5):  # weekdays only for equities-style calendars
            grp = [r for d, r in zip(dts, rets) if d.weekday() == wd]
            rest = [r for d, r in zip(dts, rets) if d.weekday() != wd]
            if len(grp) < min_n or len(rest) < min_n:
                continue
            res = welch_t(grp, rest)
            if res.get("p") is None:
                continue
            out.append(Anomaly(
                scanner="weekday_effect",
                target=label,
                signature=f"weekday:{label}:{WEEKDAYS[wd]}",
                description=f"{label} {WEEKDAYS[wd]} mean return "
                            f"{mean(grp)*1e4:+.1f} bps/day vs rest-of-week "
                            f"{mean(rest)*1e4:+.1f} bps/day",
                effect=round((mean(grp) - mean(rest)) * 1e4, 2),
                unit="bps/day vs rest-of-week",
                n=len(grp),
                t=res["t"], p=res["p"],
                window=_window(dts),
                extra={"weekday": WEEKDAYS[wd], "n_control": len(rest)},
            ))

    for name, (dts, rets) in per_series.items():
        sweep(name, dts, rets)

    # basket sweep: equal-weight mean return across series, aligned by date
    by_date: dict = {}
    for name, (dts, rets) in per_series.items():
        for d, r in zip(dts, rets):
            by_date.setdefault(d.date(), []).append((d, r))
    bdts, brets = [], []
    for day in sorted(by_date):
        vals = by_date[day]
        if len(vals) >= max(3, len(per_series) // 2):
            bdts.append(vals[0][0])
            brets.append(mean(v for _, v in vals))
    if len(brets) >= min_n * 5:
        sweep("BASKET", bdts, brets)
    return out


def scan_hour_of_day(data: dict, min_n: int = 30) -> list[Anomaly]:
    """Hourly series × hour-of-day (UTC): is this hour's mean return
    different from all other hours?"""
    if data.get("freq") != "1h":
        return []
    out = []
    for name, series in data["series"].items():
        dts, rets = _returns(series)
        for h in range(24):
            grp = [r for d, r in zip(dts, rets) if d.hour == h]
            rest = [r for d, r in zip(dts, rets) if d.hour != h]
            if len(grp) < min_n or len(rest) < min_n:
                continue
            res = welch_t(grp, rest)
            if res.get("p") is None:
                continue
            out.append(Anomaly(
                scanner="hour_of_day",
                target=name,
                signature=f"hour:{name}:{h:02d}UTC",
                description=f"{name} hour {h:02d}:00 UTC mean return "
                            f"{mean(grp)*1e4:+.2f} bps/h vs other hours "
                            f"{mean(rest)*1e4:+.2f} bps/h",
                effect=round((mean(grp) - mean(rest)) * 1e4, 2),
                unit="bps/hour vs other hours",
                n=len(grp),
                t=res["t"], p=res["p"],
                window=_window(dts),
                extra={"hour_utc": h, "n_control": len(rest)},
            ))
    return out


def scan_return_autocorr(data: dict, min_n: int = 60) -> list[Anomaly]:
    """Per-series lag-1 return autocorrelation. Bartlett SE ≈ 1/sqrt(n)
    under the null of no autocorrelation; p from the normal distribution."""
    import math
    from laboratory.stats import _norm_cdf  # deterministic helper, single source

    out = []
    for name, series in data["series"].items():
        _, rets = _returns(series)
        if len(rets) < min_n:
            continue
        ac = lag_autocorr(rets, lag=1)
        if ac is None:
            continue
        n = len(rets)
        z = ac * math.sqrt(n)
        p = 2 * (1 - _norm_cdf(abs(z)))
        out.append(Anomaly(
            scanner="return_autocorr",
            target=name,
            signature=f"autocorr:{name}:{data['freq']}",
            description=f"{name} lag-1 return autocorrelation {ac:+.4f} "
                        f"({'momentum' if ac > 0 else 'mean-reversion'} tendency)",
            effect=round(ac, 4),
            unit=f"lag-1 autocorr of {data['freq']} returns",
            n=n,
            t=round(z, 4), p=round(p, 6),
            window=(series[0][0].date().isoformat(), series[-1][0].date().isoformat()),
            extra={"freq": data["freq"]},
        ))
    return out


SCANNERS = {
    "weekday_effect": scan_weekday_effects,
    "hour_of_day": scan_hour_of_day,
    "return_autocorr": scan_return_autocorr,
}
