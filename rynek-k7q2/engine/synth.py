"""Dane syntetyczne do testów offline (nie odzwierciedlają rynku)."""
import numpy as np
import pandas as pd


def make(seed=19):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2004-01-02", "2026-10-30")
    n = len(idx)
    # zmienność reżimowa (GARCH-like) + szoki
    sig = np.empty(n); r = np.empty(n)
    s = 0.009
    shocks = {int(n * f): (m, l) for f, m, l in
              [(0.17, 0.0012, 300), (0.27, 0.003, 40), (0.33, 0.002, 60), (0.52, 0.008, 30),
               (0.63, 0.0012, 250), (0.71, 0.004, 30), (0.80, 0.0035, 70), (0.87, 0.003, 40),
               (0.93, 0.004, 25)]}
    drag = np.zeros(n)
    for st, (m, l) in shocks.items():
        drag[st:st + l] += m
    for t in range(n):
        s = np.sqrt(0.0000015 + 0.08 * (r[t - 1] if t else 0) ** 2 + 0.9 * s ** 2)
        sig[t] = s + drag[t] * 1.5
        r[t] = 0.0009 - drag[t] * 0.6 + sig[t] * rng.standard_t(5) / np.sqrt(5 / 3)
    r[-18:] = -0.0045 + rng.normal(0, 0.006, 18)
    ann = pd.Series(sig * np.sqrt(252) * 100, index=idx).rolling(5, min_periods=1).mean()
    vix = (ann * 1.15 + 3 + rng.normal(0, 0.8, n)).clip(9, 85)

    def px(beta, base, noise=0.004):
        return base * np.exp(np.cumsum(r * beta + rng.normal(0, noise, n)))

    df = pd.DataFrame(index=idx)
    df["^GSPC"] = px(1.0, 1100)
    df["^NDX"] = px(1.25, 1450, 0.005)
    df["^RUT"] = px(1.2, 580, 0.006)
    df["^DJI"] = px(0.9, 10400, 0.003)
    df["^VIX"] = vix
    df["^VXN"] = vix * 1.15 + 2 + rng.normal(0, 0.6, n)
    df["^RVX"] = vix * 1.2 + 3 + rng.normal(0, 0.7, n)
    df["^VXD"] = vix * 0.95 + rng.normal(0, 0.5, n)
    df["^VIX3M"] = (vix.rolling(30, min_periods=1).mean() * 0.6 + 0.4 * vix) * 0.9 + 3
    df["^VVIX"] = 80 + (vix.pct_change(5).fillna(0) * 150).clip(-20, 80) + vix * 0.8
    df["HYG"] = px(0.35, 50, 0.002)
    df["IEF"] = 80 * np.exp(np.cumsum(-r * 0.15 + rng.normal(0.00005, 0.002, n)))
    df["SPY"] = df["^GSPC"] / 10
    df["RSP"] = px(1.05, 40, 0.004)
    df["QQQ"] = df["^NDX"] / 40
    df["QQEW"] = px(1.2, 30, 0.005)
    df.loc[:"2006-07-01", "^VIX3M"] = np.nan
    df.loc[:"2007-01-01", "^VVIX"] = np.nan
    oas = pd.Series((3 + vix.values * 0.12 + rng.normal(0, 0.05, n)), index=idx)
    fg = {"score": 31, "rating": "fear", "prev_week": 42, "prev_month": 61,
          "hist": [(d.strftime("%Y-%m-%d"), float(v)) for d, v in
                   zip(idx[-250:], np.clip(100 - vix.values[-250:] * 2.5, 2, 98))]}
    return df, oas, fg
