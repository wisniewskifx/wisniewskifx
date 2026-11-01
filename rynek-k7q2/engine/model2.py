"""Testy z kryteriami ustalonymi PRZED testem (pre-rejestracja):

1) Bottom Score v2 — regresja logistyczna, refit co rok walk-forward.
   ZALICZA, jeśli skill (Brier vs base rate) >= +5% na >= 3 z 4 indeksów
   ORAZ kalibracja rośnie (tolerancja 3 pp). Inaczej Bottom Score znika ze strony.

2) Prognoza dna (analogi) — walk-forward, co 5. dzień od 2010.
   ZALICZA, jeśli pokrycie przedziału 80% mieści się w 70–90%
   ORAZ mediana błędu głębokości <= błąd prognozy naiwnej, na >= 3 z 4 indeksów.
   Inaczej strona pokazuje tabelę empiryczną (naiwną) zamiast prognozy z analogów.
"""
import numpy as np
import pandas as pd

from config import NEAR

V2_FEATS = ["dd", "vol_pct", "vol_off_high", "term_flip", "vix_term", "credit_20d", "ph3", "ph4", "ph5", "ph6"]
SKILL_MIN = 0.05
PASS_N = 3


# ------------------------------------------------------------ logistyczna
def _fit(X, y, lam=1.0, it=30):
    mu, sd = X.mean(0), X.std(0) + 1e-9
    Z = np.c_[np.ones(len(X)), (X - mu) / sd]
    w = np.zeros(Z.shape[1])
    R = np.eye(Z.shape[1]) * lam
    R[0, 0] = 0
    for _ in range(it):
        p = 1 / (1 + np.exp(-Z @ w))
        g = Z.T @ (p - y) + R @ w
        Hm = (Z * (p * (1 - p))[:, None]).T @ Z + R
        step = np.linalg.solve(Hm, g)
        w -= step
        if np.abs(step).max() < 1e-6:
            break
    return w, mu, sd


def _pred(model, X):
    w, mu, sd = model
    Z = np.c_[np.ones(len(X)), (X - mu) / sd]
    return 1 / (1 + np.exp(-Z @ w))


def add_v2_features(d):
    d["term_flip"] = ((d["vix_term_max15"] >= 1) & (d["vix_term"] < 1)).astype(float)
    for p in (3, 4, 5, 6):
        d[f"ph{p}"] = (d["phase"] == p).astype(float)


def bottom_v2(d):
    """Walk-forward: model na rok Y uczony tylko na epizodach zakończonych przed 1 stycznia Y."""
    add_v2_features(d)
    feats = [f for f in V2_FEATS if d[f].notna().mean() > 0.6]
    m = (d["dd"] <= -0.05) & d[feats].notna().all(axis=1)
    pool = d[m]
    y_all = (pool["further"] >= NEAR).astype(float)
    out = pd.Series(np.nan, index=d.index)
    for yr in range(pool.index.year.min() + 3, d.index.year.max() + 1):
        cut = pd.Timestamp(f"{yr}-01-01")
        tr = pool[(pool["ep_complete"]) & (pool["ep_end"] < cut)]
        if tr["episode"].nunique() < 6 or len(tr) < 150:
            continue
        model = _fit(tr[feats].to_numpy(float), y_all.loc[tr.index].to_numpy())
        te = pool[pool.index.year == yr]
        if len(te):
            out.loc[te.index] = _pred(model, te[feats].to_numpy(float)) * 100
    d["bottom_v2"] = out
    return feats


def score_eval(d, col, start="2011-01-01"):
    h = d[(d.index >= start) & d["ep_complete"] & d[col].notna() & d["bottom_base"].notna()]
    if len(h) < 60:
        return None
    P, B = h[col].to_numpy() / 100, h["bottom_base"].to_numpy() / 100
    Y = (h["further"] >= NEAR).to_numpy(float)
    bins = np.quantile(P, [0, .2, .4, .6, .8, 1])
    cal = []
    for lo, hi in zip(bins[:-1], bins[1:]):
        mk = (P >= lo) & (P <= hi)
        if mk.sum() >= 20:
            cal.append({"pred": float(P[mk].mean()), "real": float(Y[mk].mean()), "n": int(mk.sum())})
    bs, bb = float(((P - Y) ** 2).mean()), float(((B - Y) ** 2).mean())
    mono = all(cal[i]["real"] <= cal[i + 1]["real"] + 0.03 for i in range(len(cal) - 1)) and len(cal) >= 3
    return {"calib": cal, "brier": bs, "brier_base": bb, "skill": 1 - bs / bb if bb > 0 else None,
            "monotone": bool(mono), "n": int(len(h)), "episodes": int(h["episode"].nunique())}


# ------------------------------------------------------------ prognoza
def episodes_table(d):
    rows = []
    for e, seg in d.groupby("episode"):
        if not seg["ep_complete"].iloc[0] or seg["dd"].min() > -0.05:
            continue
        rows.append({"ep": e, "end": seg.index[-1], "final_dd": float(seg["dd"].min()),
                     "dd": seg["dd"].to_numpy(), "t_low": int(np.argmin(seg["close"].to_numpy()))})
    return rows


def naive_dist(eps, date, dd_low):
    """Zakończone przed `date` epizody, które doszły co najmniej do dd_low: rozkład końcowej głębokości."""
    sel = [e for e in eps if e["end"] < date and e["final_dd"] <= dd_low + 1e-9]
    if len(sel) < 5:
        return None
    fd = np.array([e["final_dd"] for e in sel])
    days = []
    for e in sel:
        first = int(np.argmax(e["dd"] <= dd_low + 1e-9))
        days.append(max(0, e["t_low"] - first))
    return {"n": len(sel), "p10": float(np.percentile(fd, 10)), "p25": float(np.percentile(fd, 25)),
            "p50": float(np.percentile(fd, 50)), "p75": float(np.percentile(fd, 75)),
            "p90": float(np.percentile(fd, 90)), "days_med": float(np.median(days)),
            "days_p25": float(np.percentile(days, 25)), "days_p75": float(np.percentile(days, 75)),
            "p_beyond": {f"{k}": float((fd <= k / 100).mean()) for k in (-15, -20, -25, -30)}}


def forecast_eval(d, pool, step=5, start="2010-01-01", shrink=6):
    eps = episodes_table(d)
    h = d[(d.index >= start) & (d["dd"] <= -0.05) & d["ep_complete"] & d[pool.feats].notna().all(axis=1)].iloc[::step]
    rng = np.random.default_rng(7)
    A, N = [], []
    for t, row in h.iterrows():
        nd = naive_dist(eps, t, row["dd_low_so_far"])
        r = pool.neighbors(row[pool.feats].to_numpy(float), t)
        if nd is None or r is None:
            continue
        sel, w, base = r
        lam = shrink / (len(np.unique(pool.ep[sel])) + shrink)
        allp = np.concatenate([sel, base])
        ww = np.concatenate([w * (1 - lam), np.full(len(base), lam / len(base))])
        pick = rng.choice(allp, size=1500, p=ww)
        trough = np.minimum(row["close"] * (1 + pool.further[pick]), row["low_so_far"])
        depth = trough / row["peak"] - 1
        real = row["final_dd"]
        q10, q50, q90 = np.percentile(depth, [10, 50, 90])
        A.append((q10 <= real <= q90, abs(q50 - real)))
        N.append((nd["p10"] <= real <= nd["p90"], abs(nd["p50"] - real)))
    if len(A) < 30:
        return None
    A, N = np.array(A, float), np.array(N, float)
    return {"n": int(len(A)), "cov_analog": float(A[:, 0].mean()), "mae_analog": float(np.median(A[:, 1])),
            "cov_naive": float(N[:, 0].mean()), "mae_naive": float(np.median(N[:, 1]))}


def naive_now(d):
    eps = episodes_table(d)
    r = d.iloc[-1]
    if r["dd_low_so_far"] > -0.05:
        return None
    nd = naive_dist(eps, d.index[-1] + pd.Timedelta(days=1), r["dd_low_so_far"])
    if nd is None:
        return None
    nd.update({"peak": float(r["peak"]), "close": float(r["close"]), "dd": float(r["dd"]),
               "dd_low": float(r["dd_low_so_far"]),
               "lvl_p10": float(r["peak"] * (1 + nd["p10"])), "lvl_p25": float(r["peak"] * (1 + nd["p25"])),
               "lvl_p50": float(r["peak"] * (1 + nd["p50"])), "lvl_p75": float(r["peak"] * (1 + nd["p75"])),
               "lvl_p90": float(r["peak"] * (1 + nd["p90"]))})
    return nd


def decide(results, key_eval):
    """results: {idx: eval}; zwraca (pass, ile_zaliczonych, szczegóły)."""
    ok = {k: key_eval(v) for k, v in results.items() if v}
    n = sum(ok.values())
    return n >= PASS_N, n, ok
