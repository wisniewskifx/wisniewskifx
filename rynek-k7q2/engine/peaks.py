"""Szczyty i wzrosty.

Kryteria (ustalone PRZED liczeniem):
  Zdarzenie: w ciągu H sesji od dnia t indeks znajdzie się >= 10% pod swoim rekordem (korekta jak w monitorze).
  Próba testowa: dni blisko rekordu (spadek od szczytu nie większy niż 3%).
  Składnik ZALICZA, jeśli dla H=120: P(korekta | świeci) / P(korekta | dzień blisko rekordu) >= 1.3,
     przy >= 8 niezależnych epizodach sygnału, na >= 3 indeksach (lub na wszystkich, gdzie składnik jest dostępny, jeśli < 3).
  Termometr (regresja logistyczna, refit co rok, walk-forward bez przecieku przyszłości) ZALICZA, jeśli skill >= +5%
     względem częstości bazowej i kalibracja rośnie, na >= 3 z 4 indeksów.
  Wyprzedzenie: dla pierwszego dnia każdego epizodu sygnału liczymy sesje do szczytu następnej korekty >= 10%
     oraz ile indeks jeszcze urósł do tego szczytu.
"""
import numpy as np
import pandas as pd

from model2 import _fit, _pred

NEAR = -0.03
H = (60, 120, 250)
GAP = 20
LIFT_MIN, EPS_MIN, PASS_N, SKILL_MIN = 1.3, 8, 3, 0.05
EW = {"SPX": ("RSP", "SPY"), "NDX": ("QQEW", "QQQ"), "DJI": ("RSP", "SPY"), "RUT": ("RSP", "SPY")}
SECT = ["XLK", "XLF", "XLE", "XLV", "XLY", "XLP", "XLI", "XLU", "XLB"]

COMP = {
    "credit": ("Kredyt vs akcje", "Indeks wyżej niż 60 sesji temu, a HYG/IEF spadł o ponad 1% — obligacje śmieciowe słabną mimo wzrostów akcji."),
    "breadth_ew": ("Szerokość: equal-weight", "Indeks rośnie (60 sesji), a wersja równoważona traci ponad 2% do ważonej — wzrost niesie coraz mniej spółek."),
    "smallcap": ("Szerokość: małe spółki", "Indeks rośnie, a Russell 2000 traci ponad 3% do S&P 500 w 60 sesji."),
    "sectors": ("Szerokość: sektory", "Indeks blisko rekordu, a nad swoją MA200 jest najwyżej 4 z 9 sektorów S&P."),
    "defensive": ("Rotacja defensywna", "Indeks rośnie, a użyteczność + dobra podstawowe + zdrowie biją technologię i dobra cykliczne o ponad 3% w 60 sesji."),
    "overext": ("Rozciągnięcie ceny", "Dystans od MA200 w górnych 10% całej historii indeksu."),
    "vol_div": ("VIX rośnie z indeksem", "Indeks +1% w 20 sesji, a VIX +10% w tym samym czasie — rynek kupuje ochronę mimo wzrostów."),
    "rates": ("Szybki wzrost stóp", "Rentowność 10-latek USA wzrosła o co najmniej 0,75 pp w 3 miesiące."),
}


def _f(x, d=4):
    return None if x is None or (isinstance(x, float) and np.isnan(x)) or pd.isna(x) else round(float(x), d)


def _sig(cond, valid):
    return pd.Series(np.where(valid, cond.astype(float), np.nan), index=cond.index)


def components(d, raw, long_df, key):
    idx = d.index
    c = d["close"]
    R = raw.reindex(idx).ffill(limit=5)
    L = long_df.reindex(idx).ffill(limit=5) if long_df is not None else pd.DataFrame(index=idx)
    r60, r20 = c / c.shift(60) - 1, c / c.shift(20) - 1
    up60 = r60 > 0
    out = {}
    if {"HYG", "IEF"} <= set(R.columns):
        cr = R["HYG"] / R["IEF"]
        cr60 = cr / cr.shift(60) - 1
        out["credit"] = _sig(up60 & (cr60 < -0.01), cr60.notna() & r60.notna())
    a, b = EW[key]
    if {a, b} <= set(R.columns):
        ew = R[a] / R[b]
        ew60 = ew / ew.shift(60) - 1
        out["breadth_ew"] = _sig(up60 & (ew60 < -0.02), ew60.notna() & r60.notna())
    if key != "RUT" and {"^RUT", "^GSPC"} <= set(L.columns):
        rs = L["^RUT"] / L["^GSPC"]
        rs60 = rs / rs.shift(60) - 1
        out["smallcap"] = _sig(up60 & (rs60 < -0.03), rs60.notna() & r60.notna())
    sec = [s for s in SECT if s in L.columns]
    if len(sec) >= 7:
        above = pd.concat([(L[s] > L[s].rolling(200).mean()).where(L[s].rolling(200).mean().notna()) for s in sec], axis=1)
        cnt, avail = above.sum(axis=1, min_count=7), above.notna().sum(axis=1)
        out["sectors"] = _sig((cnt <= 4) & (d["dd"] >= NEAR), avail >= 7)
        d.attrs["sectors_cnt"] = cnt
    dfn = [s for s in ("XLU", "XLP", "XLV") if s in L.columns]
    cyc = [s for s in ("XLK", "XLY") if s in L.columns]
    if len(dfn) == 3 and len(cyc) == 2:
        lr = lambda s: np.log(L[s] / L[s].shift(60))
        d60 = sum(lr(s) for s in dfn) / 3 - sum(lr(s) for s in cyc) / 2
        out["defensive"] = _sig(up60 & (d60 > 0.03), d60.notna() & r60.notna())
    ma = c.rolling(200).mean()
    dist = c / ma - 1
    pct = dist.expanding(min_periods=250).rank(pct=True)
    out["overext"] = _sig(pct >= 0.90, pct.notna())
    d["overext_pct"] = pct
    if "^VIX" in R:
        v20 = R["^VIX"] / R["^VIX"].shift(20) - 1
        out["vol_div"] = _sig((r20 > 0.01) & (v20 > 0.10), v20.notna() & r20.notna())
    if "^TNX" in L.columns:
        tnx = L["^TNX"]
        dt = tnx - tnx.shift(63)
        out["rates"] = _sig(dt >= 0.75, dt.notna())
    return out


def outcomes(d):
    dd = d["dd"].to_numpy()
    c = d["close"].to_numpy()
    n = len(dd)
    ev = {}
    for h in H:
        e = np.full(n, np.nan)
        for i in range(n):
            j = min(n, i + 1 + h)
            if i + 1 < n and np.nanmin(dd[i + 1:j]) <= -0.10:
                e[i] = 1.0
            elif i + h < n:
                e[i] = 0.0
        ev[h] = e
    # szczyty korekt >= 10% (rekord przed epizodem z dd <= -10%)
    peaks = []
    for e_, seg in d.groupby("episode"):
        if seg["dd"].min() <= -0.10:
            peaks.append(d.index.get_loc(seg.index[0]))
    peaks = np.array(sorted(peaks))
    to_peak = np.full(n, np.nan)
    gain = np.full(n, np.nan)
    for i in range(n):
        k = np.searchsorted(peaks, i)
        if k < len(peaks):
            p = peaks[k]
            to_peak[i] = p - i
            gain[i] = c[p] / c[i] - 1
    return ev, peaks, to_peak, gain


def _episodes(pos):
    ep, last, cur = [], None, -1
    for p in pos:
        if last is None or p - last > GAP:
            cur += 1
        ep.append(cur)
        last = p
    return np.array(ep, dtype=int)


def evaluate(comp, near, ev, to_peak, gain):
    out = {}
    valid = near & comp.notna() & ~np.isnan(ev[120])
    base = ev[120][valid.to_numpy()]
    lit = valid & (comp == 1)
    pos = np.flatnonzero(lit.to_numpy())
    if len(base) < 50:
        return None
    out["base120"] = _f(base.mean())
    out["n_days"] = int(len(pos))
    if len(pos) == 0:
        out.update({"n_eps": 0, "p120": None, "lift120": None})
        return out
    eps = _episodes(pos)
    out["n_eps"] = int(eps.max() + 1)
    for h in H:
        vb = near & comp.notna() & ~np.isnan(ev[h])
        vl = vb & (comp == 1)
        pb = ev[h][vb.to_numpy()].mean() if vb.sum() else np.nan
        pl = ev[h][vl.to_numpy()].mean() if vl.sum() else np.nan
        out[f"p{h}"] = _f(pl)
        out[f"base{h}"] = _f(pb)
        out[f"lift{h}"] = _f(pl / pb) if pb and pb > 0 and not np.isnan(pl) else None
    # wyprzedzenie: pierwszy dzień każdego epizodu sygnału
    first = np.array([pos[eps == e][0] for e in range(eps.max() + 1)])
    tp, gn = to_peak[first], gain[first]
    m = ~np.isnan(tp)
    out["lead_med"] = _f(np.median(tp[m])) if m.any() else None
    out["lead_p25"] = _f(np.percentile(tp[m], 25)) if m.any() else None
    out["lead_p75"] = _f(np.percentile(tp[m], 75)) if m.any() else None
    out["gain_med"] = _f(np.median(gn[m])) if m.any() else None
    out["gain_p75"] = _f(np.percentile(gn[m], 75)) if m.any() else None
    out["late_share"] = _f(np.mean(tp[m] > 60)) if m.any() else None
    out["first_n"] = int(m.sum())
    out["passed"] = bool(out["lift120"] is not None and out["lift120"] >= LIFT_MIN and out["n_eps"] >= EPS_MIN)
    return out


def thermometer(d, comps, near, ev):
    keys = list(comps)
    X = pd.concat([comps[k].fillna(0).rename(k) for k in keys] + [d["overext_pct"].fillna(0.5).rename("oxp")], axis=1)
    y = pd.Series(ev[120], index=d.index)
    m = near & X.notna().all(axis=1)
    pred = pd.Series(np.nan, index=d.index)
    pos = np.arange(len(d))
    years = sorted(set(d.index.year))
    for yr in years:
        cut = pd.Timestamp(f"{yr}-01-01")
        icut = d.index.searchsorted(cut)
        tr = m & y.notna() & (pd.Series(pos, index=d.index) + 120 < icut)
        if tr.sum() < 400 or y[tr].nunique() < 2:
            continue
        te = m & (d.index.year == yr)
        if not te.any():
            continue
        model = _fit(X[tr].to_numpy(float), y[tr].to_numpy(float), lam=2.0)
        pred[te] = _pred(model, X[te].to_numpy(float))
        d.loc[te, "_base_wf"] = float(y[tr].mean())
    h = d[m & pred.notna() & y.notna()]
    if len(h) < 200:
        return pred, None
    P, Y = pred[h.index].to_numpy(), y[h.index].to_numpy()
    B = d.loc[h.index, "_base_wf"].to_numpy()
    bs, bb = float(((P - Y) ** 2).mean()), float(((B - Y) ** 2).mean())
    qs = np.quantile(P, [0, .2, .4, .6, .8, 1])
    cal = []
    for lo, hi in zip(qs[:-1], qs[1:]):
        k = (P >= lo) & (P <= hi)
        if k.sum() >= 30:
            cal.append({"pred": float(P[k].mean()), "real": float(Y[k].mean()), "n": int(k.sum())})
    mono = len(cal) >= 3 and all(cal[i]["real"] <= cal[i + 1]["real"] + 0.03 for i in range(len(cal) - 1))
    sk = 1 - bs / bb if bb > 0 else None
    return pred, {"brier": bs, "brier_base": bb, "skill": sk, "monotone": bool(mono), "calib": cal, "n": int(len(h)),
                  "passed": bool(sk is not None and sk >= SKILL_MIN and mono)}


def peak_profile(d, comps, peaks, near):
    out = []
    keys = list(comps)
    lit_now_cnt = pd.concat([comps[k] for k in keys], axis=1).sum(axis=1, min_count=1)
    rand = lit_now_cnt[near].mean()
    for p in peaks:
        t = d.index[p]
        seg = d[d["episode"] == d.at[t, "episode"]]
        row = {"peak": str(t.date()), "depth": _f(seg["dd"].min()), "complete": bool(seg["ep_complete"].iloc[0]), "c": {}}
        for k in keys:
            s = comps[k]
            v = s.iat[p]
            w = s.iloc[max(0, p - 250): p + 1]
            litpos = np.flatnonzero(w.to_numpy() == 1)
            first = None
            if len(litpos):
                # najwcześniejszy dzień ostatniego klastra sygnału przed szczytem
                cl = _episodes(litpos)
                last_cl = litpos[cl == cl.max()]
                first = int(len(w) - 1 - last_cl[0])
                lastd = int(len(w) - 1 - last_cl[-1])
            row["c"][k] = {"at": None if pd.isna(v) else bool(v == 1),
                           "in60": bool((s.iloc[max(0, p - 60): p + 1] == 1).any()) if s.iloc[max(0, p - 60): p + 1].notna().any() else None,
                           "lead": first, "last": lastd if len(litpos) else None}
        row["lit_at"] = _f(lit_now_cnt.iat[p], 1)
        row["lit_60"] = int(sum(1 for k in keys if row["c"][k]["in60"]))
        out.append(row)
    return out, _f(rand, 2)


def rallies(d, peaks):
    c = d["close"]
    eps = []
    for e_, seg in d.groupby("episode"):
        if seg["dd"].min() <= -0.10:
            eps.append({"peak": seg.index[0], "trough": seg["close"].idxmin(), "end": seg.index[-1],
                        "complete": bool(seg["ep_complete"].iloc[0]), "peak_px": float(seg["close"].iloc[0])})
    rows = []
    for i in range(1, len(eps)):
        prev, cur = eps[i - 1], eps[i]
        if not prev["complete"]:
            continue
        t0 = prev["trough"]
        rec = c.loc[t0:]
        rec_d = rec.index[rec >= prev["peak_px"]]
        rows.append({"from": str(t0.date()), "to": str(cur["peak"].date()),
                     "gain": _f(c[cur["peak"]] / c[t0] - 1),
                     "sessions": int(d.index.get_loc(cur["peak"]) - d.index.get_loc(t0)),
                     "after_rec_sessions": int(d.index.get_loc(cur["peak"]) - d.index.get_loc(rec_d[0])) if len(rec_d) else None,
                     "after_rec_gain": _f(c[cur["peak"]] / c[rec_d[0]] - 1) if len(rec_d) else None})
    cur = None
    if eps and eps[-1]["complete"]:
        t0 = eps[-1]["trough"]
        g = float(c.iloc[-1] / c[t0] - 1)
        s = int(len(d) - 1 - d.index.get_loc(t0))
        gains = np.array([r["gain"] for r in rows if r["gain"] is not None])
        sess = np.array([r["sessions"] for r in rows])
        cur = {"from": str(t0.date()), "gain": _f(g), "sessions": s,
               "ended_before_gain": _f((gains < g).mean()) if len(gains) else None,
               "ended_before_time": _f((sess < s).mean()) if len(sess) else None}
    elif eps:
        cur = {"in_correction": True, "peak": str(eps[-1]["peak"].date())}
    g = np.array([r["gain"] for r in rows if r["gain"] is not None])
    s = np.array([r["sessions"] for r in rows])
    summ = {"n": len(rows), "gain_med": _f(np.median(g)) if len(g) else None, "gain_p25": _f(np.percentile(g, 25)) if len(g) else None,
            "gain_p75": _f(np.percentile(g, 75)) if len(g) else None, "sess_med": _f(np.median(s)) if len(s) else None,
            "sess_p25": _f(np.percentile(s, 25)) if len(s) else None, "sess_p75": _f(np.percentile(s, 75)) if len(s) else None}
    ar = [r for r in rows if r["after_rec_sessions"] is not None]
    if ar:
        summ["after_rec_sess_med"] = _f(np.median([r["after_rec_sessions"] for r in ar]))
        summ["after_rec_gain_med"] = _f(np.median([r["after_rec_gain"] for r in ar]))
    return rows, summ, cur


def buy_at_ath(d):
    c = d["close"]
    out = {}
    ath = d["dd"] >= -1e-9
    for h in H:
        f = c.shift(-h) / c - 1
        a, b = f[ath].dropna(), f.dropna()
        out[str(h)] = {"ath_med": _f(a.median()), "ath_win": _f((a > 0).mean()), "all_med": _f(b.median()), "all_win": _f((b > 0).mean()),
                       "n_ath": int(len(a))}
    return out


def build_index(key, d, raw, long_df):
    d = d.copy()
    comps = components(d, raw, long_df, key)
    near = d["dd"] >= NEAR
    ev, peaks, to_peak, gain = outcomes(d)
    tests = {k: evaluate(s, near, ev, to_peak, gain) for k, s in comps.items()}
    pred, therm = thermometer(d, comps, near, ev)
    prof, rand = peak_profile(d, comps, peaks, near)
    rows, rsum, rcur = rallies(d, peaks)
    now = {k: (None if pd.isna(s.iat[-1]) else bool(s.iat[-1] == 1)) for k, s in comps.items()}
    last60 = {k: int((s.iloc[-60:] == 1).sum()) for k, s in comps.items()}
    ch = d.iloc[-760:]
    lit = pd.concat([comps[k] for k in comps], axis=1).sum(axis=1, min_count=1)
    return {
        "key": key, "dd": _f(d["dd"].iat[-1]), "near": bool(near.iat[-1]), "close": _f(d["close"].iat[-1], 2),
        "now": now, "last60": last60, "tests": tests, "therm": therm,
        "therm_now": _f(pred.iat[-1]) if pd.notna(pred.iat[-1]) else None,
        "overext_pct": _f(d["overext_pct"].iat[-1]),
        "profile": prof, "rand_lit": rand, "rallies": rows, "rally_sum": rsum, "rally_now": rcur, "ath": buy_at_ath(d),
        "chart": {"d": [x.strftime("%Y-%m-%d") for x in ch.index], "close": [_f(x, 2) for x in ch["close"]],
                  "lit": [None if pd.isna(x) else int(x) for x in lit.loc[ch.index]],
                  "therm": [_f(x) for x in pred.loc[ch.index]],
                  "c": {k: [None if pd.isna(x) else int(x) for x in comps[k].loc[ch.index]] for k in comps}},
    }


def build(frames, raw, long_df, names):
    res = {}
    for k, d in frames.items():
        try:
            res[k] = build_index(k, d, raw, long_df)
            res[k]["name"] = names.get(k, k)
        except Exception:  # noqa
            import traceback; traceback.print_exc()
    summary = {}
    for c in COMP:
        av = [k for k in res if res[k]["tests"].get(c)]
        ok = [k for k in av if res[k]["tests"][c].get("passed")]
        need = min(PASS_N, len(av)) if av else 1
        summary[c] = {"available": av, "passed_on": ok, "pass": bool(av) and len(ok) >= need, "need": need}
    th = [k for k in res if res[k]["therm"]]
    th_ok = [k for k in th if res[k]["therm"]["passed"]]
    therm_pass = len(th_ok) >= PASS_N
    out = {"indices": res, "summary": summary, "comp": {k: {"label": v[0], "desc": v[1]} for k, v in COMP.items()},
           "therm": {"pass": therm_pass, "passed_on": th_ok, "available": th},
           "rules": {"comp": f"lift (H=120) ≥ {LIFT_MIN} przy ≥ {EPS_MIN} niezależnych epizodach, na ≥ {PASS_N} indeksach",
                     "therm": f"skill ≥ +{int(SKILL_MIN * 100)}% i rosnąca kalibracja na ≥ {PASS_N} z 4 indeksów",
                     "near": "dzień blisko rekordu = spadek od szczytu ≤ 3%", "event": "korekta = indeks ≥ 10% pod rekordem w ciągu H sesji"}}
    out["conclusions"] = conclusions(out)
    return out


def conclusions(o):
    p = lambda x: "—" if x is None else f"{x * 100:.0f}%"
    L = []
    passed = [o["comp"][k]["label"] for k, s in o["summary"].items() if s["pass"]]
    failed = [o["comp"][k]["label"] for k, s in o["summary"].items() if not s["pass"] and s["available"]]
    L.append(("Składniki, które przeszły test: " + ", ".join(passed) + ".") if passed else "Żaden składnik nie przeszedł testu jako sygnał szczytu.")
    s = o["summary"].get("breadth_ew")
    if s and s["pass"] and set(s["passed_on"]) - {"NDX"} and len(set(s["passed_on"]) & {"SPX", "DJI", "RUT"}) >= 2:
        L.append("Uwaga: „Szerokość: equal-weight” dla S&P 500, Dow i Russella liczona jest z tej samej pary RSP/SPY — te wyniki nie są od siebie niezależne. "
                 + ("Na Nasdaq-100 (własna para QQEW/QQQ) " + ("też przechodzi." if "NDX" in s["passed_on"] else "NIE przechodzi.") if "NDX" in s["available"] else "Na Nasdaq-100 brak danych do testu."))
    if failed:
        L.append("Nie przeszły (tylko opis stanu): " + ", ".join(failed) + ".")
    L.append("Termometr łączny: " + ("ZALICZONY — pokazywany." if o["therm"]["pass"] else "NIEZALICZONY — nie jest pokazywany jako prognoza."))
    leads = []
    for k in o["comp"]:
        v = [o["indices"][i]["tests"].get(k) for i in o["indices"]]
        v = [x for x in v if x and x.get("lead_med") is not None]
        if v:
            leads.append((o["comp"][k]["label"], np.median([x["lead_med"] for x in v]), np.median([x["gain_med"] for x in v if x["gain_med"] is not None])))
    if leads:
        L.append("Typowe wyprzedzenie (pierwszy dzień sygnału → szczyt przed korektą ≥10%): "
                 + "; ".join(f"{a}: ~{b:.0f} sesji, w tym czasie indeks jeszcze +{c * 100:.0f}%" for a, b, c in leads) + ".")
    sp = o["indices"].get("SPX") or next(iter(o["indices"].values()))
    a = sp["ath"]["120"]
    L.append(f"Kupno na rekordzie ({sp['name']}): mediana zwrotu 120 sesji {a['ath_med'] * 100:+.1f}% (zysk w {p(a['ath_win'])}) vs dowolny dzień {a['all_med'] * 100:+.1f}% ({p(a['all_win'])}).")
    return L
