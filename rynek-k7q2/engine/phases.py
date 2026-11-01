"""Klasyfikacja 6 faz rynku (przyczynowa: tylko dane do dnia t)."""
import numpy as np
import pandas as pd

from config import P_FEAR, P_PANIC, DD_PULLBACK, DD_CORRECTION, DD_BEAR


def _b(x):
    return bool(x) if pd.notna(x) else False


def conditions(row):
    """Zwraca warunki każdej fazy dla jednego dnia: {faza: (obowiązkowe_ok, [(etykieta, ok), ...])}."""
    dd, vp = row["dd"], row["vol_pct"]
    term = row["vix_term"]
    out = {}

    # 4 KAPITULACJA
    must4 = dd <= -0.07 and (_b(vp >= P_PANIC) or _b(term >= 1.0)) and _b(row["vol_off_high"] > -0.12)
    out[4] = (must4, [
        ("Zmienność ≥ 90. percentyl historii", _b(vp >= P_PANIC)),
        ("VIX/VIX3M ≥ 1 (backwardation, panika)", _b(term >= 1.0)),
        ("VVIX ≥ 85. percentyl (panika na opcjach)", _b(row["vvix_pct"] >= 0.85)),
        ("RSI(14) ≤ 30 (wyprzedanie)", _b(row["rsi"] <= 30)),
        ("Realized vol ≥ implied (VRP ≤ 0)", _b(row["vrp"] <= 0)),
        ("Zmienność wciąż przy szczycie (≤12% pod 10d max)", _b(row["vol_off_high"] > -0.12)),
    ])

    # 6 BESSA
    credit_stress = _b(row["credit_20d"] <= -0.025) or _b(row["oas_20d"] >= 1.0)
    long_dd = _b(row["days_from_peak"] >= 150) and _b(row["close"] <= row["min10"] * 1.01)
    must6 = dd <= DD_BEAR and (credit_stress or long_dd)
    out[6] = (must6, [
        (f"Drawdown ≤ {DD_BEAR:.0%}", dd <= DD_BEAR),
        ("Stres kredytowy (HYG/IEF −2,5% w 20d lub OAS +1pp)", credit_stress),
        ("Spadek trwa ≥150 sesji i cena przy dołkach", long_dd),
        ("Cena pod MA200", _b(row["ma200_dist"] < 0)),
    ])

    # 5 DNO ZALICZONE
    spike = _b(row["vol_peak15_pct"] >= 0.70)
    fear_off = _b(row["vol_off_high"] <= -0.20)
    bounce = _b(row["close"] >= row["min10"] * 1.015)
    must5 = dd <= -0.06 and spike and fear_off and bounce
    out[5] = (must5, [
        ("Był szpic strachu w ostatnich 15 sesjach (≥70. pct)", spike),
        ("Zmienność ≥20% pod 10-dniowym szczytem", fear_off),
        ("Cena ≥1,5% nad 10-dniowym dołkiem", bounce),
        ("VIX/VIX3M wrócił < 1 po panice", _b(row["vix_term"] < 1) and _b(row["vix_term_max15"] >= 1)),
        ("Dywergencja cena vs strach (10d)", _b(row["div_recent"] >= 1)),
        ("RSI odbił > 40", _b(row["rsi"] > 40)),
    ])

    # 3 ESKALACJA
    rising = _b(row["vol_d10"] > 0)
    at_lows = _b(row["close"] <= row["min10"] * 1.01)
    must3 = dd <= DD_CORRECTION and (rising or at_lows)
    out[3] = (must3, [
        (f"Drawdown ≤ {DD_CORRECTION:.0%}", dd <= DD_CORRECTION),
        ("Zmienność powyżej średniej 10d (strach rośnie)", rising),
        ("Cena przy 10-dniowych dołkach", at_lows),
        ("Breadth się pogarsza (equal-weight słabszy)", _b(row["breadth_20d"] < -0.01)),
        ("Zmienność ≥ 75. pct", _b(vp >= P_FEAR)),
    ])

    # 2 PULLBACK
    must2 = dd <= DD_PULLBACK
    out[2] = (must2, [
        (f"Drawdown ≤ {DD_PULLBACK:.0%}", dd <= DD_PULLBACK),
        ("Zmienność < 75. pct (brak paniki)", _b(vp < P_FEAR)),
        ("Brak stresu kredytowego", not credit_stress),
    ])
    out[1] = (True, [(f"Drawdown > {DD_PULLBACK:.0%}", dd > DD_PULLBACK),
                     ("Zmienność < 75. pct", _b(vp < P_FEAR))])
    return out


ORDER = [4, 6, 5, 3, 2, 1]


def classify_row(row):
    conds = conditions(row)
    for p in ORDER:
        ok, items = conds[p]
        if ok:
            conf = np.mean([v for _, v in items]) if items else 1.0
            return p, float(conf), conds
    return 1, 1.0, conds


def classify(d):
    need = ["dd", "vol_pct", "vol_off_high", "min10"]
    phases = pd.Series(np.nan, index=d.index)
    conf = pd.Series(np.nan, index=d.index)
    ok = d[need].notna().all(axis=1)
    idx = d.index[ok]
    res = [classify_row(r)[:2] for r in d.loc[ok].to_dict("records")]
    if res:
        phases.loc[idx] = [r[0] for r in res]
        conf.loc[idx] = [r[1] for r in res]
    # histereza: zmiana fazy dopiero gdy nowa utrzyma się 2 sesje (kapitulacja i bessa natychmiast)
    raw = phases.to_numpy()
    sm = raw.copy()
    for i in range(1, len(raw)):
        if np.isnan(raw[i]) or np.isnan(sm[i - 1]):
            continue
        if raw[i] != sm[i - 1] and raw[i] not in (4, 6):
            if i + 0 >= 1 and raw[i - 1] != raw[i]:
                sm[i] = sm[i - 1]
    d["phase_raw"] = phases
    d["phase"] = pd.Series(sm, index=d.index)
    d["phase_conf"] = conf
    return d


def phase_stats(d):
    """Statystyki historyczne każdej fazy (na zakończonych epizodach)."""
    h = d[d["phase"].notna() & d["ep_complete"]]
    troughs = (d[d["ep_complete"] & (d["final_dd"] <= -0.10)]
               .groupby("episode")["close"].idxmin())
    trough_phase = d.loc[troughs, "phase"] if len(troughs) else pd.Series(dtype=float)
    runs = (d["phase"] != d["phase"].shift()).cumsum()
    run_len = d.groupby(runs).agg(p=("phase", "first"), n=("phase", "size"))
    out = []
    for p in range(1, 7):
        s = h[h["phase"] == p]
        rl = run_len[run_len["p"] == p]["n"]
        out.append({
            "phase": p,
            "days": int(len(s)),
            "avg_run": float(rl.mean()) if len(rl) else None,
            "further_med": float(s["further"].median()) if len(s) else None,
            "p_near": float((s["further"] >= -0.03).mean()) if len(s) else None,
            "ret20_med": float(s["fwd_ret20"].median()) if len(s) else None,
            "ret60_med": float(s["fwd_ret60"].median()) if len(s) else None,
            "troughs_here": int((trough_phase == p).sum()),
            "troughs_total": int(len(trough_phase)),
        })
    return out
