"""Model: analogi historyczne (k-NN, walk-forward), Monte Carlo, walidacja."""
import numpy as np
import pandas as pd

from config import NEAR, K, H, BLOCK, N_SIM

FEATS = ["dd", "vol_pct", "vol_off_high", "vol_d10", "vix_term", "credit_20d", "log_days"]
W = {"dd": 2.0, "vol_pct": 1.2, "vol_off_high": 1.0, "vol_d10": 0.8,
     "vix_term": 1.0, "credit_20d": 0.8, "log_days": 0.6}
DD_POOL = -0.05
SHRINK = 6


def _prep(d):
    d["log_days"] = np.log1p(d["days_from_peak"])
    feats = [f for f in FEATS if d[f].notna().mean() > 0.6]
    return feats


class Pool:
    def __init__(self, d):
        self.d = d
        self.feats = _prep(d)
        m = (d["dd"] <= DD_POOL) & d["ep_complete"] & d[self.feats].notna().all(axis=1)
        p = d[m]
        self.X = p[self.feats].to_numpy(float)
        self.w = np.array([W[f] for f in self.feats])
        self.end = p["ep_end"].to_numpy("datetime64[ns]")
        self.dates = p.index.to_numpy("datetime64[ns]")
        self.ep = p["episode"].to_numpy()
        self.further = p["further"].to_numpy(float)
        self.bottomed = p["bottomed"].to_numpy(float)
        self.dtl = p["days_to_low"].to_numpy(float)
        self.pos = d.index.get_indexer(p.index)
        self.ret = d["ret"].fillna(0).to_numpy(float)
        self.n = len(d)

    def neighbors(self, x, date, k=K):
        """Analogi dostępne na dzień `date` (tylko epizody zakończone przed tą datą)."""
        m = self.end < np.datetime64(date)
        if m.sum() < 60 or len(np.unique(self.ep[m])) < 6:
            return None
        X = self.X[m]
        mu, sd = X.mean(0), X.std(0) + 1e-9
        z = (X - mu) / sd
        zx = (x - mu) / sd
        dist = np.sqrt((((z - zx) ** 2) * self.w).sum(1))
        kk = min(k, max(20, m.sum() // 4))
        idx = np.argpartition(dist, kk)[:kk]
        sel = np.flatnonzero(m)[idx]
        wts = 1.0 / (dist[idx] + 0.25)
        base_idx = np.flatnonzero(m)[np.argsort(np.abs(self.X[m][:, 0] - x[0]))[:kk * 2]]
        return sel, wts / wts.sum(), base_idx

    def prob_near(self, x, date):
        r = self.neighbors(x, date)
        if r is None:
            return np.nan, np.nan
        sel, w, base = r
        p = float((w * (self.further[sel] >= NEAR)).sum())
        b = float((self.further[base] >= NEAR).mean())
        # shrinkage do base rate: mało niezależnych epizodów = mniejsze zaufanie do analogów
        n_eff = len(np.unique(self.ep[sel]))
        p = (n_eff * p + SHRINK * b) / (n_eff + SHRINK)
        return p, b


def bottom_score_series(d, pool, days):
    """Bottom Score = P(dno blisko) z analogów, liczone walk-forward dla ostatnich `days` sesji."""
    out = pd.Series(np.nan, index=d.index)
    base = pd.Series(np.nan, index=d.index)
    tail = d.iloc[-days:]
    ok = (tail["dd"] <= DD_POOL) & tail[pool.feats].notna().all(axis=1)
    for t, row in tail[ok].iterrows():
        p, b = pool.prob_near(row[pool.feats].to_numpy(float), t)
        out[t], base[t] = p * 100, b * 100
    d["bottom_score"] = out
    d["bottom_base"] = base
    return d


def forecast(d, pool):
    t = d.index[-1]
    row = d.iloc[-1]
    if row["dd"] > DD_POOL or row[pool.feats].isna().any():
        return None
    x = row[pool.feats].to_numpy(float)
    r = pool.neighbors(x, t)
    if r is None:
        return None
    sel, w, base = r
    rng = np.random.default_rng(42)
    c0, peak, low = row["close"], row["peak"], row["low_so_far"]

    # shrinkage: część próbek z base rate (podobny drawdown), proporcjonalnie do małej liczby epizodów
    n_eff = len(np.unique(pool.ep[sel]))
    k0 = len(sel)
    lam = SHRINK / (n_eff + SHRINK)
    base = base[pool.pos[base] + H < pool.n] if (pool.pos[base] + H < pool.n).sum() >= 10 else base
    sel = np.concatenate([sel, base])
    w = np.concatenate([w * (1 - lam), np.full(len(base), lam / len(base))])

    # A) analogi bezpośrednio: dalszy spadek do dna epizodu
    pick = rng.choice(sel, size=N_SIM, p=w)
    a_trough = c0 * (1 + pool.further[pick])
    a_days = pool.dtl[pick]

    # B) Monte Carlo: bootstrap blokowy ścieżek następujących po analogach (bloki wyrównane w czasie)
    valid = sel[pool.pos[sel] + H < pool.n]
    wv = w[np.isin(sel, valid)]
    paths = None
    if len(valid) >= 10:
        wv = wv / wv.sum()
        nb = H // BLOCK
        R = np.empty((N_SIM, nb * BLOCK))
        src = rng.choice(valid, size=(N_SIM, nb), p=wv)
        for j in range(nb):
            starts = pool.pos[src[:, j]] + 1 + j * BLOCK
            R[:, j * BLOCK:(j + 1) * BLOCK] = pool.ret[starts[:, None] + np.arange(BLOCK)]
        paths = c0 * np.cumprod(1 + R, axis=1)
        mc_min = np.minimum(paths.min(1), c0)
        mc_days = np.where(paths.min(1) < c0, paths.argmin(1) + 1, 0)
        trough = np.concatenate([a_trough, mc_min])
        days = np.concatenate([a_days, mc_days])
    else:
        trough, days = a_trough, a_days

    trough = np.minimum(trough, c0)
    bottomed = trough >= low * 0.999
    fl = np.minimum(trough, low)       # dno epizodu = min(dotychczasowy dołek, przyszły)
    depth = fl / peak - 1
    q = lambda a, p: float(np.nanpercentile(a, p))
    nb_days = days[~bottomed]
    fan = None
    if paths is not None:
        fan = {f"p{p}": np.percentile(paths[:, :60], p, axis=0).round(2).tolist()
               for p in (5, 25, 50, 75, 95)}
    hist_y, hist_x = np.histogram(depth * 100, bins=30)
    return {
        "close": float(c0), "peak": float(peak), "low_so_far": float(low),
        "trough_med": q(fl, 50), "trough_p10": q(fl, 10), "trough_p90": q(fl, 90),
        "trough_p25": q(fl, 25), "trough_p75": q(fl, 75),
        "depth_med": q(depth, 50), "depth_p10": q(depth, 10), "depth_p90": q(depth, 90),
        "further_med": q(trough / c0 - 1, 50),
        "days_med": q(nb_days, 50) if len(nb_days) else 0.0,
        "days_p25": q(nb_days, 25) if len(nb_days) else 0.0,
        "days_p75": q(nb_days, 75) if len(nb_days) else 0.0,
        "p_bottomed": float(bottomed.mean()),
        "p_near": float((trough / c0 - 1 >= NEAR).mean()),
        "p_deep": float((trough / c0 - 1 <= -0.10).mean()),
        "p_bear": float((depth <= -0.20).mean()),
        "n_analogs": int(k0),
        "n_episodes": int(n_eff),
        "shrink": float(lam),
        "analog_eps": _top_eps(d, pool, sel, w),
        "fan": fan,
        "hist": {"x": ((hist_x[:-1] + hist_x[1:]) / 2).round(2).tolist(),
                 "y": (hist_y / hist_y.sum() * 100).round(2).tolist()},
    }


def _top_eps(d, pool, sel, w):
    df = pd.DataFrame({"ep": pool.ep[sel], "w": w, "date": pool.dates[sel]})
    g = df.groupby("ep").agg(w=("w", "sum"), date=("date", "min")).sort_values("w", ascending=False)
    out = []
    for e, r in g.head(6).iterrows():
        seg = d[d["episode"] == e]
        out.append({"start": str(seg.index[0].date()), "final_dd": float(seg["final_dd"].iloc[0]),
                    "weight": float(r["w"])})
    return out


def validate(d, pool, step=3, start="2011-01-01"):
    """Walk-forward: na każdy dzień tylko epizody zakończone wcześniej. Kalibracja + Brier."""
    h = d[(d.index >= start) & d["ep_complete"] & d["bottom_score"].notna()].iloc[::step]
    if len(h) < 30:
        return None
    P = h["bottom_score"].to_numpy() / 100
    B = h["bottom_base"].to_numpy() / 100
    Y = (h["further"] >= NEAR).to_numpy(float)
    bins = np.linspace(0, 1, 6)
    cal = []
    for lo, hi in zip(bins[:-1], bins[1:]):
        m = (P >= lo) & (P < hi + (1e-9 if hi == 1 else 0))
        if m.sum() >= 5:
            cal.append({"pred": float(P[m].mean()), "real": float(Y[m].mean()), "n": int(m.sum())})
    brier = float(((P - Y) ** 2).mean())
    brier_b = float(((B - Y) ** 2).mean())
    return {"calib": cal, "brier": brier, "brier_base": brier_b,
            "skill": float(1 - brier / brier_b) if brier_b > 0 else None, "n": int(len(P))}


def trough_check(d):
    """Jak model zachowywał się w dniach historycznych dołków (korekty ≥10%)."""
    eps = d[d["ep_complete"] & (d["final_dd"] <= -0.10)].groupby("episode")
    out = []
    for e, seg in eps:
        tdate = seg["close"].idxmin()
        i = d.index.get_loc(tdate)
        win = d.iloc[max(0, i - 5): i + 6]
        after = d.iloc[i: i + 15]
        p5 = after.index[after["phase"] == 5]
        out.append({
            "peak": str(seg.index[0].date()), "trough": str(tdate.date()),
            "depth": float(seg["final_dd"].iloc[0]),
            "days": int(seg["days_from_peak"].loc[tdate]),
            "phase_at": int(d.at[tdate, "phase"]) if pd.notna(d.at[tdate, "phase"]) else None,
            "phase4_near": bool((win["phase"] == 4).any()),
            "score_at": float(d.at[tdate, "bottom_score"]) if pd.notna(d.at[tdate, "bottom_score"]) else None,
            "p5_lag": int(d.index.get_loc(p5[0]) - i) if len(p5) else None,
            "p5_vs_low": float(d.at[p5[0], "close"] / seg["close"].min() - 1) if len(p5) else None,
        })
    return out


def corrections_table(d, thr=-0.10):
    out = []
    for e, seg in d.groupby("episode"):
        fd = seg["final_dd"].iloc[0]
        if fd > thr and seg["ep_complete"].iloc[0]:
            continue
        if not seg["ep_complete"].iloc[0] and seg["dd"].min() > -0.05:
            continue
        tdate = seg["close"].idxmin()
        out.append({"peak": str(seg.index[0].date()), "trough": str(tdate.date()),
                    "depth": float(seg["dd"].min()), "days": int(seg["days_from_peak"].loc[tdate]),
                    "recovery": (int(len(seg) - seg.index.get_loc(tdate)) if seg["ep_complete"].iloc[0] else None),
                    "vol_peak": float(seg["vol"].max()), "ongoing": not bool(seg["ep_complete"].iloc[0])})
    return out
