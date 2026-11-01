"""Co kupić: ranking 4 indeksów na podstawie historycznie podobnych sytuacji.

Dla każdego indeksu k szukamy dni (od 1990), w których:
  - spadek k od 52-tyg. szczytu był podobny do dzisiejszego (±3 pp),
  - typ rynku był taki sam jak dziś (selektywna / szeroka korekta / brak korekty),
  - rola k była taka sama (lider spadków / środek / najsilniejszy).
Zwroty k po 60/120/250 sesjach od tych dni = rozkład „co dawało kupno tego indeksu w takiej sytuacji”.

REGUŁA DECYZYJNA (ustalona przed obliczeniem):
  Zwycięzca = najwyższa mediana zwrotu 120 sesji liczona po epizodach (każdy epizod = 1 głos). Wskazujemy go TYLKO, jeśli:
   (a) ma >= 8 niezależnych epizodów i drugi też >= 8,
   (b) przewaga mediany nad drugim >= 2 pp,
   (c) w bootstrapie po epizodach P(zwycięzca > drugi) >= 75%.
  Inaczej: REMIS STATYSTYCZNY — wtedy wskazujemy indeks o najmniejszym ryzyku (najwyższy 10. percentyl).
"""
import numpy as np
import pandas as pd

IDX = ["NDX", "SPX", "DJI", "RUT"]
NAMES = {"NDX": "Nasdaq-100", "SPX": "S&P 500", "DJI": "Dow Jones", "RUT": "Russell 2000"}
BAND = 0.03
H = (60, 120, 250)
GAP = 20
SEL = -0.06


def _f(x, d=4):
    return None if x is None or pd.isna(x) else round(float(x), d)


def market_type(row):
    v = row.dropna()
    if len(v) < 3:
        return None
    lead, lag = v.min(), v.max()
    if lead > -0.08:
        return "none"
    return "selective" if lag > SEL else "broad"


def roles(row):
    v = row.dropna().sort_values()
    out = {}
    for i, k in enumerate(v.index):
        out[k] = "leader" if i == 0 else ("laggard" if i == len(v) - 1 else "middle")
    return out


def episodes(idx_pos):
    """Grupuje dni w niezależne epizody (przerwa > GAP sesji)."""
    ep, last, cur = [], None, -1
    for p in idx_pos:
        if last is None or p - last > GAP:
            cur += 1
        ep.append(cur)
        last = p
    return np.array(ep)


def rank(px):
    px = px[[k for k in IDX if k in px]].copy()
    dd = px / px.rolling(252, min_periods=60).max() - 1
    dd = dd[dd.index >= "1990-01-01"]
    mt = dd.apply(market_type, axis=1)
    rl = dd.apply(roles, axis=1)
    now = dd.iloc[-1]
    mt_now, rl_now = mt.iloc[-1], rl.iloc[-1]
    rows = {}
    rng = np.random.default_rng(11)
    for k in px.columns:
        if pd.isna(now.get(k)):
            continue
        pos_all = np.arange(len(px))
        fwd = {h: px[k].shift(-h) / px[k] - 1 for h in H}
        m = ((dd[k] - now[k]).abs() <= BAND) & (mt == mt_now) & rl.map(lambda r: r.get(k) == rl_now.get(k))
        m &= fwd[120].reindex(dd.index).notna()
        m.iloc[-1] = False
        days = dd.index[m]
        if len(days) < 5:
            rows[k] = {"n_days": int(len(days)), "n_eps": 0}
            continue
        pos = px.index.get_indexer(days)
        ep = episodes(pos)
        st = {"n_days": int(len(days)), "n_eps": int(ep.max() + 1), "dd_now": _f(now[k]), "role": rl_now.get(k)}
        for h in H:
            r = fwd[h].reindex(days).dropna()
            st[f"med{h}"] = _f(r.median()) if len(r) else None
            st[f"win{h}"] = _f((r > 0).mean()) if len(r) else None
            st[f"p10_{h}"] = _f(r.quantile(0.10)) if len(r) else None
            st[f"p90_{h}"] = _f(r.quantile(0.90)) if len(r) else None
        # mediana na poziomie epizodów (żeby długie epizody nie dominowały)
        r120 = fwd[120].reindex(days).to_numpy()
        ep_med = np.array([np.nanmedian(r120[ep == e]) for e in range(ep.max() + 1)])
        st["ep_med120"] = _f(np.median(ep_med))
        st["_ep_meds"] = ep_med
        # ODPORNOŚĆ (pokazywana obok reguły, nie zmienia jej): okresy, nadwyżka nad typowym wynikiem, najgorsze epizody
        ser120 = fwd[120].reindex(days)
        for lab, lo, hi in (("pre2010", "1990-01-01", "2009-12-31"), ("post2010", "2010-01-01", "2100-01-01")):
            x = ser120[(ser120.index >= lo) & (ser120.index <= hi)].dropna()
            e = ep[(days >= lo) & (days <= hi)]
            st[f"{lab}_med120"] = _f(x.median()) if len(x) else None
            st[f"{lab}_eps"] = int(len(np.unique(e))) if len(e) else 0
            st[f"{lab}_win120"] = _f((x > 0).mean()) if len(x) else None
        worst = []
        for e_ in range(ep.max() + 1):
            dsel = days[ep == e_]
            worst.append((str(dsel[0].date()), float(np.nanmedian(r120[ep == e_]))))
        worst.sort(key=lambda z: z[1])
        st["worst_eps"] = [{"start": w0, "r120": _f(w1)} for w0, w1 in worst[:5]]
        base = fwd[120].dropna()
        st["base_med120"] = _f(base.median())
        st["base_win120"] = _f((base > 0).mean())
        rows[k] = st
    ranked = sorted([k for k in rows if rows[k].get("n_eps", 0) > 0], key=lambda k: (rows[k]["n_eps"] < 8, -(rows[k]["ep_med120"] if rows[k].get("ep_med120") is not None else -9)))
    verdict = {"type": "brak danych"}
    if len(ranked) >= 2:
        a, b = rows[ranked[0]], rows[ranked[1]]
        boot = []
        for _ in range(2000):
            sa = rng.choice(a["_ep_meds"], len(a["_ep_meds"]))
            sb = rng.choice(b["_ep_meds"], len(b["_ep_meds"]))
            boot.append(np.median(sa) > np.median(sb))
        p = float(np.mean(boot))
        diff = (a["ep_med120"] or 0) - (b["ep_med120"] or 0)
        ok = a["n_eps"] >= 8 and b["n_eps"] >= 8 and diff >= 0.02 and p >= 0.75
        safest = max(ranked, key=lambda k: rows[k]["p10_120"] if rows[k]["p10_120"] is not None else -9)
        verdict = {"type": "przewaga" if ok else "remis", "winner": ranked[0], "second": ranked[1],
                   "diff120": _f(diff), "p_boot": _f(p), "safest": safest,
                   "rule": "zwycięzca tylko gdy: ≥8 epizodów u obu, przewaga mediany 120 sesji ≥2 pp i P(bootstrap) ≥75%"}
    for k in rows:
        rows[k].pop("_ep_meds", None)
    return {"market_type": mt_now, "roles": rl_now, "dd_now": {k: _f(now[k]) for k in now.index},
            "rows": rows, "ranking": ranked, "verdict": verdict, "text": explain(rows, ranked, verdict, mt_now),
            "robust": robust_text(rows, ranked)}


def robust_text(rows, ranked):
    p = lambda x: "—" if x is None else f"{x * 100:+.1f}%"
    out = []
    for k in ranked:
        r = rows[k]
        ex = (r["ep_med120"] or 0) - (r["base_med120"] or 0)
        w = ", ".join(f"{z['start'][:7]} {p(z['r120'])}" for z in r.get("worst_eps", [])[:3])
        out.append(f"{NAMES[k]}: nadwyżka nad typowym wynikiem indeksu {p(ex)}; 1990–2009: {p(r.get('pre2010_med120'))} ({r.get('pre2010_eps', 0)} ep.), "
                   f"od 2010: {p(r.get('post2010_med120'))} ({r.get('post2010_eps', 0)} ep.); najgorsze epizody: {w}.")
    if len(ranked) >= 2:
        exs = {k: (rows[k]["ep_med120"] or 0) - (rows[k]["base_med120"] or 0) for k in ranked}
        best_ex = max(exs, key=exs.get)
        same = best_ex == ranked[0]
        out.append(("Po odjęciu typowego wyniku każdego indeksu kolejność " + ("się utrzymuje" if same else "się zmienia")
                    + f" — największa nadwyżka: {NAMES[best_ex]} ({p(exs[best_ex])})."))
    return out


def explain(rows, ranked, v, mt):
    p = lambda x: "—" if x is None else f"{x * 100:+.1f}%"
    q = lambda x: "—" if x is None else f"{x * 100:.0f}%"
    typ = {"selective": "selektywna korekta (jeden indeks prowadzi, reszta się trzyma)",
           "broad": "szeroka korekta", "none": "brak istotnej korekty"}.get(mt, mt)
    rol = {"leader": "lider spadków", "laggard": "najsilniejszy", "middle": "środek stawki"}
    out = [f"Sytuacja dziś: {typ}."]
    for i, k in enumerate(ranked, 1):
        r = rows[k]
        thin = " [ZA MAŁO EPIZODÓW — orientacyjnie]" if r["n_eps"] < 8 else ""
        out.append(f"{i}. {NAMES[k]}{thin} ({rol.get(r['role'], r['role'])}, {q(r['dd_now'])} od 52-tyg. szczytu): w {r['n_eps']} podobnych epizodach "
                   f"mediana {p(r['ep_med120'])} po 120 sesjach (zysk w {q(r['win120'])} dni), 10% najgorszych ≤ {p(r['p10_120'])}; "
                   f"po 250 sesjach {p(r['med250'])}. Typowo dla tego indeksu: {p(r['base_med120'])} / 120 sesji.")
    if v.get("type") == "przewaga":
        out.append(f"WERDYKT: {NAMES[v['winner']]} — przewaga {p(v['diff120'])} nad {NAMES[v['second']]} po 120 sesjach, "
                   f"w bootstrapie wygrywa w {q(v['p_boot'])} przypadków. Spełnia regułę decyzyjną.")
    elif v.get("type") == "remis":
        out.append(f"WERDYKT: REMIS STATYSTYCZNY. {NAMES[v['winner']]} ma najwyższą medianę, ale przewaga nad {NAMES[v['second']]} "
                   f"({p(v['diff120'])}, bootstrap {q(v['p_boot'])}) nie spełnia reguły. Przy remisie wybór pod ryzyko: najpłytszy "
                   f"„najgorszy scenariusz” ma {NAMES[v['safest']]}.")
    return out
