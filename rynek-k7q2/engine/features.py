"""Cechy (wskaźniki) i wyniki historyczne epizodów dla jednego indeksu."""
import numpy as np
import pandas as pd


def expanding_pct(s, min_periods=250):
    """Percentyl bieżącej wartości względem całej dotychczasowej historii (bez lookahead)."""
    return s.expanding(min_periods=min_periods).rank(pct=True)


def rsi(c, n=14):
    d = c.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + up / dn)


def build(raw, cfg, oas=None):
    """raw: DataFrame z kolumnami tickerów Yahoo. Zwraca DataFrame cech dziennych."""
    c = raw[cfg["price"]].dropna()
    d = pd.DataFrame(index=c.index)
    d["close"] = c
    r = raw.reindex(c.index).ffill(limit=5)

    vix = r["^VIX"]
    vol = r.get(cfg["vol"])
    fallback = False
    if vol is None or vol.iloc[-20:].isna().mean() > 0.5 or vol.notna().sum() < 1500:
        vol, fallback = vix, True
    d["vol"] = vol
    d["vix"] = vix
    d.attrs["vol_fallback"] = fallback

    # --- drawdown / epizody
    peak = c.cummax()
    d["peak"] = peak
    d["dd"] = c / peak - 1
    d["episode"] = (c >= peak).cumsum()
    d["days_from_peak"] = d.groupby("episode").cumcount()
    d["low_so_far"] = d.groupby("episode")["close"].cummin()
    d["dd_low_so_far"] = d["low_so_far"] / peak - 1

    # --- zmienność
    d["vol_pct"] = expanding_pct(vol)
    d["vol_off_high"] = vol / vol.rolling(10).max() - 1
    d["vol_d3"] = vol / vol.rolling(3).mean() - 1
    d["vol_d10"] = vol / vol.rolling(10).mean() - 1
    d["vol_peak15_pct"] = d["vol_pct"].rolling(15).max()
    d["vix_term"] = r["^VIX"] / r["^VIX3M"]
    d["vix_term_max15"] = d["vix_term"].rolling(15).max()
    d["vvix"] = r.get("^VVIX")
    d["vvix_pct"] = expanding_pct(d["vvix"]) if d["vvix"].notna().sum() > 300 else np.nan
    d["spread"] = (vol - vix) if not fallback and cfg["vol"] != "^VIX" else np.nan
    rv20 = c.pct_change().rolling(20).std() * np.sqrt(252) * 100
    d["rv20"] = rv20
    d["vrp"] = vol - rv20

    # --- kredyt / breadth
    ratio = r["HYG"] / r["IEF"]
    d["credit_20d"] = ratio / ratio.shift(20) - 1
    if oas is not None and len(oas):
        o = oas.reindex(c.index).ffill(limit=10)
        d["oas"] = o
        d["oas_20d"] = o - o.shift(20)
    else:
        d["oas"] = np.nan
        d["oas_20d"] = np.nan
    if cfg["ew"] and all(t in r for t in cfg["ew"]):
        br = r[cfg["ew"][0]] / r[cfg["ew"][1]]
        d["breadth_20d"] = br / br.shift(20) - 1
    else:
        d["breadth_20d"] = np.nan

    # --- technika
    d["rsi"] = rsi(c)
    d["ma200_dist"] = c / c.rolling(200).mean() - 1
    d["min10"] = c.rolling(10).min()
    new_low = c <= c.rolling(20).min()
    d["divergence"] = (new_low & (vol < 0.85 * vol.rolling(20).max())).astype(float)
    d["div_recent"] = d["divergence"].rolling(10).max()

    # --- stress score 0-100 (ile strachu teraz)
    parts = [d["vol_pct"],
             expanding_pct(d["vix_term"]),
             d["vvix_pct"] if isinstance(d["vvix_pct"], pd.Series) else None,
             1 - expanding_pct(d["credit_20d"]),
             1 - expanding_pct(d["rsi"]),
             1 - expanding_pct(d["dd"])]
    parts = [p for p in parts if p is not None]
    d["stress"] = pd.concat(parts, axis=1).mean(axis=1, skipna=True) * 100

    add_outcomes(d)
    return d


def add_outcomes(d):
    """Wyniki 'z przyszłości' (do uczenia na zakończonych epizodach)."""
    c = d["close"]
    n = len(d)
    ep = d["episode"].values
    last_ep = ep[-1]
    d["ep_complete"] = d["episode"] != last_ep

    # min od t do końca epizodu (włącznie z t)
    fmin = d.iloc[::-1].groupby("episode")["close"].cummin().iloc[::-1]
    d["further"] = fmin / c - 1                     # dalszy spadek do dna epizodu (<=0)
    d["bottomed"] = (fmin >= d["low_so_far"] * (1 - 1e-9)).astype(float)
    g = d.groupby("episode")
    ep_min = g["close"].transform("min")
    ep_peak = g["peak"].transform("first")
    d["final_dd"] = ep_min / ep_peak - 1
    d["ep_end"] = g.apply(lambda x: x.index[-1], include_groups=False).reindex(d["episode"]).values

    # sesje do dna (dla epizodów z dd <= -5%)
    dtl = np.full(n, np.nan)
    vals = c.values
    for e, idx in g.indices.items():
        if len(idx) < 3 or d["final_dd"].iat[idx[0]] > -0.05:
            continue
        seg = vals[idx]
        # odwrotny running argmin
        best = len(seg) - 1
        out = np.empty(len(seg))
        for j in range(len(seg) - 1, -1, -1):
            if seg[j] <= seg[best]:
                best = j
            out[j] = best - j
        dtl[idx] = out
    d["days_to_low"] = dtl

    fut = c[::-1].rolling(60, min_periods=60).min()[::-1].shift(-1)
    d["fwd_maxdd60"] = fut / c - 1
    d["fwd_ret20"] = c.shift(-20) / c - 1
    d["fwd_ret60"] = c.shift(-60) / c - 1
    d["ret"] = c.pct_change()
