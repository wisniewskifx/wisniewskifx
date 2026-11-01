"""Sprawdzalność: co system pokazywał w dniach historycznych dołków + statystyki sygnałów."""
import numpy as np
import pandas as pd

from config import PHASES
from phases import conditions

SHORT = {k: v["short"] for k, v in PHASES.items()}


def _f(x, d=4):
    return None if x is None or pd.isna(x) else round(float(x), d)


def _counts(row):
    c = conditions(row)
    return {str(p): {"ok": int(sum(v for _, v in items)), "n": len(items), "must": bool(m),
                     "items": [[lbl, bool(v)] for lbl, v in items]}
            for p, (m, items) in c.items()}


def _pct_of(series, value):
    s = series.dropna()
    return None if not len(s) or pd.isna(value) else float((s < value).mean())


def troughs(d, thr=-0.08):
    """Lista dołków (zakończone epizody z dd <= thr + bieżący, jeśli <= thr)."""
    out = []
    for e, seg in d.groupby("episode"):
        if seg["dd"].min() > thr:
            continue
        out.append((e, seg, bool(seg["ep_complete"].iloc[0])))
    return out


def trough_detail(d, seg, complete):
    tdate = seg["close"].idxmin()
    i = d.index.get_loc(tdate)
    win = d.iloc[max(0, i - 5): i + 6]
    row = d.loc[tdate]
    cnt = _counts(row)
    # najlepszy wynik Kapitulacji w oknie ±5 sesji
    best4 = max((sum(v for _, v in conditions(r)[4][1]) for r in win.to_dict("records")), default=0)
    after = d.iloc[i: i + 21]
    p5 = after.index[after["phase"] == 5]
    p4w = win.index[win["phase"] == 4]
    ph = int(row["phase"]) if pd.notna(row["phase"]) else None
    # Eskalacja w dniu dna jest niemal automatyczna (cena przy 10d dołku), więc liczy się dopiero Kapitulacja
    if not complete:
        verdict = "TRWA"
    elif len(p4w):
        verdict = "KAPITULACJA"
    elif ph == 6:
        verdict = "BESSA"
    elif ph in (3, 5):
        verdict = "TYLKO ESKALACJA"
    else:
        verdict = "PRZEGAPIONE"
    pre5 = seg.loc[:tdate].index[seg.loc[:tdate, "phase"] == 5]
    false5 = int(((d.loc[pre5, "close"] / seg["close"].min() - 1) > 0.03).sum() > 0) if len(pre5) else 0
    lo, hi = max(0, i - 45), min(len(d), i + 30)
    w2 = d.iloc[lo:hi]
    c4 = [sum(v for _, v in conditions(r)[4][1]) for r in w2.to_dict("records")]
    c5 = [sum(v for _, v in conditions(r)[5][1]) for r in w2.to_dict("records")]
    return {
        "peak": str(seg.index[0].date()), "trough": str(tdate.date()), "complete": complete,
        "depth": _f(seg["dd"].min()), "days": int(row["days_from_peak"]),
        "phase": ph, "phase_raw": int(row["phase_raw"]) if pd.notna(row["phase_raw"]) else None,
        "phases_win": sorted({int(x) for x in win["phase"].dropna()}),
        "verdict": verdict,
        "counts": cnt, "best4_win": int(best4),
        "vol": _f(row["vol"], 2), "vol_pct": _f(row["vol_pct"]),
        "vol_max_win": _f(win["vol"].max(), 2), "vol_max_pct": _f(win["vol_pct"].max()),
        "term_max_win": _f(win["vix_term"].max(), 3),
        "vvix_max_win": _f(win["vvix"].max(), 1), "vvix_max_pct": _f(win["vvix_pct"].max()) if "vvix_pct" in win else None,
        "rsi_min_win": _f(win["rsi"].min(), 1), "credit_20d": _f(row["credit_20d"]),
        "oas_20d": _f(row["oas_20d"], 2), "breadth_20d": _f(row["breadth_20d"]),
        "stress_max_win": _f(win["stress"].max(), 1), "bottom": _f(row["bottom_score"], 1),
        "bottom2": _f(row.get("bottom_v2"), 1),
        "bottom_base": _f(row["bottom_base"], 1),
        "p5_lag": int(d.index.get_loc(p5[0]) - i) if len(p5) else None,
        "p5_vs_low": _f(d.at[p5[0], "close"] / seg["close"].min() - 1) if len(p5) else None,
        "false5_before": false5,
        "chart": {"d": [x.strftime("%Y-%m-%d") for x in w2.index], "close": [_f(x, 2) for x in w2["close"]],
                  "vol": [_f(x, 2) for x in w2["vol"]], "phase": [None if pd.isna(x) else int(x) for x in w2["phase"]],
                  "c4": c4, "c5": c5, "t": str(tdate.date())},
    }


def signal_stats(d):
    """Jakość sygnałów faz 4 i 5 na całej historii (zakończone epizody)."""
    out = {}
    a = d[d["fwd_ret60"].notna() & d["phase"].notna()]
    if len(a):
        out["all"] = {"signals": int(len(a)), "further_med": None, "within3": None, "deeper10": None,
                      "ret20_med": _f(a["fwd_ret20"].median()), "ret60_med": _f(a["fwd_ret60"].median()),
                      "win60": _f((a["fwd_ret60"] > 0).mean())}
    b = d[(d["dd"] <= -0.10) & d["ep_complete"] & d["phase"].notna()]
    if len(b):
        out["base"] = {"signals": int(len(b)), "further_med": _f(b["further"].median()),
                       "within3": _f((b["further"] >= -0.03).mean()), "deeper10": _f((b["further"] <= -0.10).mean()),
                       "ret20_med": _f(b["fwd_ret20"].median()), "ret60_med": _f(b["fwd_ret60"].median()),
                       "win60": _f((b["fwd_ret60"] > 0).mean())}
    starts = d[(d["phase"] != d["phase"].shift()) & d["ep_complete"]]
    for p in (3, 4, 5):
        s = starts[starts["phase"] == p]
        if not len(s):
            out[str(p)] = None
            continue
        fur = s["further"]
        out[str(p)] = {
            "signals": int(len(s)),
            "further_med": _f(fur.median()),
            "within3": _f((fur >= -0.03).mean()),
            "deeper10": _f((fur <= -0.10).mean()),
            "ret20_med": _f(s["fwd_ret20"].median()), "ret60_med": _f(s["fwd_ret60"].median()),
            "win60": _f((s["fwd_ret60"] > 0).mean()),
        }
    return out


def model_verdict(val):
    if not val or val.get("skill") is None:
        return {"level": "na", "text": "Za mało danych do oceny."}
    s = val["skill"]
    cal = val["calib"]
    mono = all(cal[i]["real"] <= cal[i + 1]["real"] + 0.03 for i in range(len(cal) - 1)) if len(cal) > 1 else False
    if s > 0.05 and mono:
        return {"level": "good", "text": f"Bottom Score dodaje informację (skill {s:+.1%}), kalibracja rosnąca."}
    if s > 0.0:
        return {"level": "weak", "text": f"Bottom Score minimalnie lepszy od base rate (skill {s:+.1%}). Traktuj orientacyjnie."}
    return {"level": "bad", "text": f"Bottom Score NIE jest lepszy od samego drawdownu (skill {s:+.1%}). Nie używaj go do decyzji — patrz na fazy."}


def build(d, val):
    tr = [trough_detail(d, seg, comp) for _, seg, comp in troughs(d)]
    done = [t for t in tr if t["complete"] and t["depth"] <= -0.10]
    n = len(done)
    summ = None
    if n:
        summ = {
            "n": n,
            "hit": sum(t["verdict"] == "KAPITULACJA" for t in done) / n,
            "esc_only": sum(t["verdict"] in ("TYLKO ESKALACJA", "BESSA") for t in done) / n,
            "missed": sum(t["verdict"] == "PRZEGAPIONE" for t in done) / n,
            "cap_reached": sum(4 in t["phases_win"] for t in done) / n,
            "p5_found": sum(t["p5_lag"] is not None for t in done) / n,
            "p5_lag_med": float(np.median([t["p5_lag"] for t in done if t["p5_lag"] is not None])) if any(t["p5_lag"] is not None for t in done) else None,
            "p5_slip_med": float(np.median([t["p5_vs_low"] for t in done if t["p5_vs_low"] is not None])) if any(t["p5_vs_low"] is not None for t in done) else None,
            "phase_at": {SHORT[p]: sum(t["phase"] == p for t in done) for p in range(1, 7)},
        }
    return {"troughs": tr, "summary": summ, "signals": signal_stats(d), "model": model_verdict(val)}


def conclusions(name, v):
    """Wnioski liczone automatycznie z danych sprawdzalności (zmieniają się razem z danymi)."""
    s, g = v.get("summary"), v.get("signals") or {}
    if not s:
        return []
    p = lambda x: "—" if x is None else f"{x * 100:.0f}%"
    pp = lambda x: "—" if x is None else f"{x * 100:+.1f}%"
    L = []
    base, al, k4, k5 = g.get("base"), g.get("all"), g.get("4"), g.get("5")
    if base and al:
        L.append(f"Kupno w dowolnym dniu spadku ≥10%: zysk po 60 sesjach w {p(base['win60'])} przypadków, mediana {pp(base['ret60_med'])} "
                 f"(dowolny dzień w ogóle: {p(al['win60'])}, {pp(al['ret60_med'])}). To jest główna przewaga: kupowanie korekt.")
    L.append(f"{s['n']} dołków ≥10%: w {p(s['hit'])} dno wypadło w oknie Kapitulacji (±5 sesji). "
             f"Bez paniki (tylko Eskalacja/Bessa): {p(s['esc_only'])}. Przegapione: {p(s['missed'])}.")
    if k4 and base:
        better = (k4["ret60_med"] or 0) > (base["ret60_med"] or 0)
        L.append(f"Wejście w Kapitulację: mediana zwrotu 60 sesji {pp(k4['ret60_med'])} vs {pp(base['ret60_med'])} dla losowego dnia spadku — "
                 + ("lepiej od przypadku." if better else "nie lepiej od przypadku. Kapitulacja to miejsce dna, nie gwarancja lepszego wyniku (w bessie bywa kilka).")
                 + f" Ryzyko >10% niżej: {p(k4['deeper10'])} vs {p(base['deeper10'])}.")
    if k5 and base:
        L.append(f"„Dno zaliczone”: ryzyko >10% niżej {p(k5['deeper10'])} vs {p(base['deeper10'])}, zysk po 60 sesjach {p(k5['win60'])} vs {p(base['win60'])}. "
                 f"Sygnał przychodzi z opóźnieniem (mediana {s['p5_lag_med'] if s['p5_lag_med'] is not None else '—'} sesji, {pp(s['p5_slip_med'])} nad dołkiem) i nie po każdym dnie ({p(s['p5_found'])}).")
    return L
