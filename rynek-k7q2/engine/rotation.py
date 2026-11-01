"""Liderzy spadków (korekta = spadek od 52-tygodniowego szczytu): czy korekty i bessy mają swój wiodący indeks/sektor i co wtedy kupować.

1) Zdarzenia rynkowe (od 1985): korekty >= 10% któregokolwiek z 4 indeksów, zgrupowane w czasie.
   Dla każdego: głębokość wszystkich indeksów i sektorów, lider, kto pierwszy odrobił rekord,
   oraz zwroty wszystkich indeksów/sektorów po 60/120/250 sesjach od dnia, gdy lider dotknął -10%.
2) Fazy (od 2006): dni wejścia indeksu w KAPITULACJĘ, gdy inny indeks był w hossie (DD > -5%):
   co dało lepszy wynik — lider spadków czy indeks, który się trzymał.
"""
import numpy as np
import pandas as pd

IDX = {"NDX": "^NDX", "SPX": "^GSPC", "DJI": "^DJI", "RUT": "^RUT"}
SECT = {"XLK": "Technologia", "XLF": "Finanse", "XLE": "Energia", "XLV": "Ochrona zdrowia",
        "XLY": "Dobra cykliczne", "XLP": "Dobra podstawowe", "XLI": "Przemysł", "XLU": "Użyteczność publ.",
        "XLB": "Materiały"}
NAMES = {"NDX": "Nasdaq-100", "SPX": "S&P 500", "DJI": "Dow Jones", "RUT": "Russell 2000"}
SELECTIVE = -0.06
H = (60, 120, 250)


def _f(x, d=4):
    return None if x is None or (isinstance(x, float) and np.isnan(x)) or pd.isna(x) else round(float(x), d)


W52 = 252


def _hi(s):
    return s.rolling(W52, min_periods=1).max()


def _episodes(s, thr=-0.10):
    """Korekta = spadek od 52-tygodniowego szczytu (standard rynkowy). Epizod kończy się nowym 52-tyg. szczytem."""
    s = s.dropna()
    hi = _hi(s)
    dd = s / hi - 1
    ep = (s >= hi).cumsum()
    out = []
    for e, seg in s.groupby(ep):
        m = dd.loc[seg.index]
        if m.min() <= thr:
            out.append({"peak": seg.index[0], "trough": seg.idxmin(), "end": seg.index[-1],
                        "depth": float(m.min()), "complete": seg.index[-1] != s.index[-1]})
    return out


def _fwd(px, col, i, h):
    j = i + h
    if col not in px or j >= len(px) or pd.isna(px[col].iat[i]) or pd.isna(px[col].iat[j]):
        return None
    return float(px[col].iat[j] / px[col].iat[i] - 1)


def market_events(px):
    dd = px / px.apply(_hi) - 1
    allep = []
    for k in IDX:
        if k in px:
            for e in _episodes(px[k]):
                allep.append({**e, "idx": k})
    allep.sort(key=lambda e: e["peak"])
    groups, gend = [], None
    for e in allep:
        if groups and e["peak"] <= gend + pd.Timedelta(days=30):
            groups[-1].append(e)
            gend = max(gend, e["trough"])
        else:
            groups.append([e])
            gend = e["trough"]
    events = []
    for g in groups:
        start = min(e["peak"] for e in g)
        last_tr = max(e["trough"] for e in g)
        i_end = min(len(px) - 1, px.index.get_loc(last_tr) + 20)
        w_end = px.index[i_end]
        win = dd.loc[start:w_end]
        depth = {k: _f(min(win[k].min(), 0)) if k in win and win[k].notna().any() else None for k in list(IDX) + list(SECT)}
        idx_d = {k: depth[k] for k in IDX if depth.get(k) is not None}
        leader = min(idx_d, key=idx_d.get)
        laggard = max(idx_d, key=idx_d.get)
        sec_d = {k: depth[k] for k in SECT if depth.get(k) is not None}
        lead_sec = min(sec_d, key=sec_d.get) if sec_d else None
        best_sec = max(sec_d, key=sec_d.get) if sec_d else None
        ls = dd[leader].loc[start:w_end]
        t10 = ls.index[np.argmax(ls.to_numpy() <= -0.10)]
        i10 = px.index.get_loc(t10)
        lag_at10 = {k: _f(dd.at[t10, k]) for k in IDX if k in dd and pd.notna(dd.at[t10, k])}
        lag_now = max(lag_at10, key=lag_at10.get)
        fwd = {h: {k: _f(_fwd(px, k, i10, h)) for k in list(IDX) + list(SECT)} for h in H}
        rec = {}
        for k in IDX:
            if k not in px:
                continue
            hist = px[k].loc[start - pd.Timedelta(days=365):start].dropna()
            if not len(hist):
                rec[k] = None
                continue
            ath = hist.max()
            lo = px[k].loc[start:w_end].idxmin()
            aft = px[k].loc[lo:]
            hit = aft.index[aft >= ath]
            rec[k] = _f((hit[0] - start).days / 365.25, 2) if len(hit) else None
        complete = all(e["complete"] for e in g)
        i0 = px.index.get_loc(start)
        L = 1800 if idx_d[leader] <= -0.30 else 520
        sub = px.iloc[i0: i0 + L: 5]
        path = {"t": [int((x - start).days) for x in sub.index]}
        for k in IDX:
            base = px[k].iat[i0] if k in px else np.nan
            path[k] = [] if pd.isna(base) else [None if pd.isna(v) else round(float(v) / float(base) * 100, 2) for v in sub[k]]
        events.append({
            "start": str(start.date()), "trough": str(last_tr.date()), "t10": str(t10.date()), "complete": complete,
            "members": sorted({e["idx"] for e in g}), "depth": depth, "leader": leader, "laggard": laggard,
            "lead_sector": lead_sec, "best_sector": best_sec, "lag_at10": lag_at10, "laggard_at10": lag_now,
            "selective": bool(lag_at10[lag_now] > SELECTIVE), "fwd": fwd, "recovery_years": rec, "path": path,
        })
    return events


def leader_vs_laggard(events):
    done = [e for e in events if e["complete"]]
    def agg(sel):
        g = [e for e in done if sel(e)]
        out = {"n": len(g)}
        for h in H:
            rel = [e["fwd"][h][e["leader"]] - e["fwd"][h][e["laggard_at10"]] for e in g
                   if e["fwd"][h][e["leader"]] is not None and e["fwd"][h][e["laggard_at10"]] is not None]
            lr = [e["fwd"][h][e["leader"]] for e in g if e["fwd"][h][e["leader"]] is not None]
            gr = [e["fwd"][h][e["laggard_at10"]] for e in g if e["fwd"][h][e["laggard_at10"]] is not None]
            out[str(h)] = {"rel_med": _f(np.median(rel)) if rel else None, "lead_wins": _f(np.mean([r > 0 for r in rel])) if rel else None,
                           "lead_med": _f(np.median(lr)) if lr else None, "lag_med": _f(np.median(gr)) if gr else None, "n": len(rel)}
        return out
    return {"all": agg(lambda e: True), "selective": agg(lambda e: e["selective"]), "broad": agg(lambda e: not e["selective"])}


def capitulation_vs_calm(frames):
    """Wejście indeksu L w Kapitulację, gdy indeks O ma DD > -5%. Co lepiej kupić: L czy O."""
    keys = [k for k in IDX if k in frames]
    if len(keys) < 2:
        return None
    rows = []
    for L in keys:
        f = frames[L]
        st = f.index[(f["phase"] == 4) & (f["phase"].shift() != 4)]
        last = None
        for t in st:
            if last is not None and f.index.get_loc(t) - f.index.get_loc(last) < 40:
                continue
            last = t
            for O in keys:
                if O == L or t not in frames[O].index:
                    continue
                o = frames[O]
                if not (o.at[t, "dd"] > -0.05):
                    continue
                i_l, i_o = f.index.get_loc(t), o.index.get_loc(t)
                r = {"date": str(t.date()), "L": L, "O": O, "L_dd": _f(f.at[t, "dd"]), "O_dd": _f(o.at[t, "dd"])}
                for h in H:
                    rl = f["close"].iat[i_l + h] / f["close"].iat[i_l] - 1 if i_l + h < len(f) else None
                    ro = o["close"].iat[i_o + h] / o["close"].iat[i_o] - 1 if i_o + h < len(o) else None
                    r[f"rL{h}"], r[f"rO{h}"] = _f(rl), _f(ro)
                    r[f"rel{h}"] = _f(rl - ro) if rl is not None and ro is not None else None
                rows.append(r)
    summ = {}
    for h in H:
        rel = [r[f"rel{h}"] for r in rows if r[f"rel{h}"] is not None]
        summ[str(h)] = {"n": len(rel), "rel_med": _f(np.median(rel)) if rel else None,
                        "lead_wins": _f(np.mean([x > 0 for x in rel])) if rel else None,
                        "L_med": _f(np.median([r[f"rL{h}"] for r in rows if r[f"rL{h}"] is not None])) if rel else None,
                        "O_med": _f(np.median([r[f"rO{h}"] for r in rows if r[f"rO{h}"] is not None])) if rel else None,
                        "L_win": _f(np.mean([r[f"rL{h}"] > 0 for r in rows if r[f"rL{h}"] is not None])) if rel else None,
                        "O_win": _f(np.mean([r[f"rO{h}"] > 0 for r in rows if r[f"rO{h}"] is not None])) if rel else None}
    return {"rows": rows, "summary": summ}


def analyze(long_df, raw=None, frames=None):
    cols = {k: long_df[t] for k, t in {**IDX, **{s: s for s in SECT}}.items() if t in long_df}
    px = pd.DataFrame(cols).dropna(subset=["SPX"]).ffill(limit=5)
    dd = px / px.apply(_hi) - 1
    ev = market_events(px)
    lvl = leader_vs_laggard(ev)
    cap = capitulation_vs_calm(frames or {})
    cur = {k: _f(dd[k].iat[-1]) for k in px.columns}
    idx_now = {k: cur[k] for k in IDX if cur.get(k) is not None}
    cur["leader"] = min(idx_now, key=idx_now.get)
    cur["laggard"] = max(idx_now, key=idx_now.get)
    cur["selective"] = bool(idx_now[cur["leader"]] <= -0.08 and idx_now[cur["laggard"]] > SELECTIVE)
    rs = (px["NDX"] / px["SPX"]).dropna()
    cur["rs_20d"], cur["rs_60d"] = _f(rs.iat[-1] / rs.iat[-21] - 1), _f(rs.iat[-1] / rs.iat[-61] - 1)
    rs_h = rs.iloc[-760::2]
    ew = None
    if raw is not None and {"RSP", "SPY"} <= set(raw.columns):
        r = (raw["RSP"] / raw["SPY"]).dropna()
        cur["ew_60d"] = _f(r.iat[-1] / r.iat[-61] - 1)
        ew = r.iloc[-760::2]
    lead_count = {}
    for e in ev:
        if e["complete"]:
            lead_count[e["leader"]] = lead_count.get(e["leader"], 0) + 1
    out = {"since": str(px.index[0].date()), "last": str(px.index[-1].date()), "events": ev,
           "leader_vs_laggard": lvl, "cap_vs_calm": cap, "current": cur, "lead_count": lead_count,
           "names": NAMES, "sectors": SECT,
           "rs_chart": {"d": [x.strftime("%Y-%m-%d") for x in rs_h.index], "v": [round(float(v), 5) for v in rs_h]},
           "ew_chart": {"d": [x.strftime("%Y-%m-%d") for x in ew.index], "v": [round(float(v), 5) for v in ew]} if ew is not None else None}
    out["conclusion"] = conclusion(out)
    return out


def conclusion(o):
    p = lambda x: "—" if x is None else f"{x * 100:.0f}%"
    pp = lambda x: "—" if x is None else f"{x * 100:+.0f} pp"
    c, lv, cap = o["current"], o["leader_vs_laggard"], o["cap_vs_calm"]
    L = []
    nm = o["names"]
    L.append(f"Dziś: lider spadków {nm[c['leader']]} ({p(c[c['leader']])}), najsilniejszy {nm[c['laggard']]} ({p(c[c['laggard']])}) → "
             + ("korekta SELEKTYWNA." if c["selective"] else "korekta szeroka." if c[c["leader"]] <= -0.08 else "brak istotnej korekty."))
    n_ev = sum(o["lead_count"].values())
    if n_ev:
        top = ", ".join(f"{nm[k]} {v}" for k, v in sorted(o["lead_count"].items(), key=lambda x: -x[1]))
        L.append(f"Na {n_ev} zakończonych zdarzeń od {o['since'][:4]} lider spadków: {top}. Korekty mają liderów — rzadko spada wszystko po równo.")
    sec = {}
    for e in o["events"]:
        if e["complete"] and e["lead_sector"]:
            sec[e["lead_sector"]] = sec.get(e["lead_sector"], 0) + 1
    if sec:
        L.append("Sektor, który spadał najmocniej (od 1999): " + ", ".join(f"{o['sectors'][k]} {v}×" for k, v in sorted(sec.items(), key=lambda x: -x[1])) + ".")
    for key, lab in (("selective", "selektywnych"), ("broad", "szerokich")):
        g = lv[key]
        if g["n"] and g["250"]["n"]:
            L.append(f"Zdarzenia {lab} ({g['n']}): kupno LIDERA spadków w dniu jego −10% vs kupno najsilniejszego indeksu — po 250 sesjach mediana różnicy {pp(g['250']['rel_med'])}, lider wygrał w {p(g['250']['lead_wins'])} przypadków.")
    if cap and cap["summary"]["250"]["n"]:
        s = cap["summary"]
        L.append(f"Od 2006: gdy indeks wchodził w KAPITULACJĘ, a inny był w hossie (n={s['250']['n']}): po 60 sesjach lider vs spokojny {pp(s['60']['rel_med'])} (lider lepszy w {p(s['60']['lead_wins'])}), po 250 sesjach {pp(s['250']['rel_med'])} ({p(s['250']['lead_wins'])}).")
    return L
