"""Główny skrypt: pobiera dane, liczy wszystko, zapisuje data.json, wysyła alerty.

python build.py --out ..            (dane z Yahoo/FRED/CNN)
python build.py --out .. --synthetic  (test offline)
"""
import argparse
import json
import math
import os
import sys
from datetime import datetime, timezone

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
from config import INDICES, PHASES, CHART_DAYS          # noqa: E402
import features, phases, model, cards, alerts           # noqa: E402


def clean(o):
    if isinstance(o, dict):
        return {k: clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    if isinstance(o, (np.floating, float)):
        return None if (math.isnan(o) or math.isinf(o)) else round(float(o), 6)
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    return o


def ser(s, dec=4):
    return [None if pd.isna(x) else round(float(x), dec) for x in s]


def lean_text(d):
    bs = d["bottom_score"].dropna()
    st = d["stress"].dropna()
    if len(bs) < 11:
        return "neutral", "—"
    db = bs.iloc[-1] - bs.iloc[-10:].mean()
    ds = st.iloc[-1] - st.iloc[-10:].mean()
    p = d["phase"].iloc[-1]
    if p == 5 or (db > 8 and ds < -3):
        return "past", "Strach opada, Bottom Score rośnie — dołek najpewniej za nami lub tuż za nami."
    if ds > 5 and db > 5:
        return "approach", "Strach i Bottom Score rosną — zbliżamy się do strefy dna."
    if ds > 5:
        return "approach", "Strach narasta, ale bez sygnałów wyczerpania — dno jeszcze przed nami."
    if db < -8:
        return "far", "Bottom Score spada — szansa na bliskie dno maleje (spadki mogą się pogłębić)."
    return "neutral", "Bez wyraźnego kierunku w ostatnich 10 sesjach."


def headline(key, cfg, d, fc):
    r = d.iloc[-1]
    p = int(r["phase"])
    ph = PHASES[p]["short"]
    if fc is None:
        return f"{cfg['name']}: {ph}. Drawdown {r['dd']:.1%} — brak aktywnej korekty, prognoza dna nieaktywna."
    s = (f"{cfg['name']}: {ph}. Prognoza dna: {fc['trough_med']:,.0f} ({fc['depth_med']:.1%} od szczytu)"
         f" za ~{fc['days_med']:.0f} sesji. Przedział 80%: {fc['depth_p90']:.1%} / {fc['depth_p10']:.1%}."
         f" P(dno już zaliczone): {fc['p_bottomed']:.0%}. Strefa kupna (IQR dna): "
         f"{fc['trough_p25']:,.0f}–{fc['trough_p75']:,.0f}.")
    return s.replace(",", " ")


def process(key, cfg, raw, oas):
    d = features.build(raw, cfg, oas)
    phases.classify(d)
    pool = model.Pool(d)
    model.bottom_score_series(d, pool, days=len(d))
    fc = model.forecast(d, pool)
    r = d.iloc[-1]
    p = int(r["phase"])
    _, _, conds = phases.classify_row(r)
    conf = float(np.mean([v for _, v in conds[p][1]]))
    runs = (d["phase"] != d["phase"].shift()).cumsum()
    since = int((runs == runs.iloc[-1]).sum())
    lean, lean_txt = lean_text(d)
    tl = d["phase"].iloc[-60:]
    ch = d.iloc[-CHART_DAYS:]
    fan_dates = None
    if fc and fc["fan"]:
        fan_dates = [x.strftime("%Y-%m-%d") for x in
                     pd.bdate_range(d.index[-1] + pd.Timedelta(days=1), periods=60)]
    bs = d["bottom_score"].dropna()
    return d, {
        "key": key, "name": cfg["name"], "vol_name": cfg["vol_name"],
        "vol_fallback": bool(d.attrs.get("vol_fallback")),
        "last_date": str(d.index[-1].date()), "close": float(r["close"]),
        "chg1d": float(d["close"].pct_change().iloc[-1]),
        "dd": float(r["dd"]), "days_from_peak": int(r["days_from_peak"]),
        "peak": float(r["peak"]), "vol": float(r["vol"]),
        "stress": float(r["stress"]),
        "stress_d3": float(r["stress"] - d["stress"].iloc[-3:].mean()),
        "stress_d10": float(r["stress"] - d["stress"].iloc[-10:].mean()),
        "bottom": float(bs.iloc[-1]) if len(bs) and bs.index[-1] == d.index[-1] else None,
        "bottom_base": float(r["bottom_base"]) if pd.notna(r["bottom_base"]) else None,
        "bottom_d3": float(bs.iloc[-1] - bs.iloc[-3:].mean()) if len(bs) > 10 and bs.index[-1] == d.index[-1] else None,
        "bottom_d10": float(bs.iloc[-1] - bs.iloc[-10:].mean()) if len(bs) > 10 and bs.index[-1] == d.index[-1] else None,
        "phase": {"id": p, **PHASES[p], "conf": conf, "since": since,
                  "raw": int(r["phase_raw"]) if pd.notna(r["phase_raw"]) else p, "lean": lean, "lean_txt": lean_txt,
                  "conditions": {str(k): {"ok": v[0], "items": v[1]} for k, v in conds.items()},
                  "timeline": {"d": [x.strftime("%Y-%m-%d") for x in tl.index], "p": ser(tl, 0)}},
        "headline": headline(key, cfg, d, fc),
        "forecast": fc, "fan_dates": fan_dates,
        "cards": cards.build_cards(d, cfg),
        "chart": {"d": [x.strftime("%Y-%m-%d") for x in ch.index], "close": ser(ch["close"], 2),
                  "peak": ser(ch["peak"], 2), "dd": ser(ch["dd"]), "vol": ser(ch["vol"], 2),
                  "bottom": ser(ch["bottom_score"], 1), "stress": ser(ch["stress"], 1),
                  "phase": ser(ch["phase"], 0)},
        "dd_hist": {"d": [x.strftime("%Y-%m-%d") for x in d.index[::5]], "dd": ser(d["dd"].iloc[::5])},
        "corrections": model.corrections_table(d),
        "phase_stats": phases.phase_stats(d),
        "validation": model.validate(d, pool),
        "troughs": model.trough_check(d),
    }


def usa_summary(res, fg, d_any):
    tot = sum(INDICES[k]["weight"] for k in res)
    w = {k: INDICES[k]["weight"] / tot for k in res}
    avg = lambda f: sum(w[k] * (res[k][f] or 0) for k in res if res[k][f] is not None)
    votes = {}
    for k in res:
        votes[res[k]["phase"]["id"]] = votes.get(res[k]["phase"]["id"], 0) + w[k]
    cons = max(votes, key=votes.get)
    bott = [res[k]["bottom"] for k in res if res[k]["bottom"] is not None]
    r = d_any.iloc[-1]
    worst = min(res, key=lambda k: res[k]["dd"])
    txt = (f"USA: konsensus {PHASES[cons]['short']} ({votes[cons]:.0%} wagi). "
           f"Najsłabszy: {res[worst]['name']} ({res[worst]['dd']:.1%}). "
           f"Stress {avg('stress'):.0f}/100" +
           (f", Bottom Score {sum(w[k]*res[k]['bottom'] for k in res if res[k]['bottom'] is not None)/max(1e-9,sum(w[k] for k in res if res[k]['bottom'] is not None)):.0f}/100." if bott else "."))
    return {
        "consensus": {"id": cons, **PHASES[cons], "share": votes[cons]},
        "stress": avg("stress"), "stress_d10": avg("stress_d10"),
        "bottom": (sum(w[k] * res[k]["bottom"] for k in res if res[k]["bottom"] is not None) /
                   max(1e-9, sum(w[k] for k in res if res[k]["bottom"] is not None))) if bott else None,
        "headline": txt,
        "vix": float(r["vix"]), "vix_term": float(r["vix_term"]),
        "credit_20d": float(r["credit_20d"]),
        "oas": None if pd.isna(r["oas"]) else float(r["oas"]),
        "oas_20d": None if pd.isna(r["oas_20d"]) else float(r["oas_20d"]),
        "fg": fg,
        "weights": w,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(os.path.dirname(__file__), ".."))
    ap.add_argument("--synthetic", action="store_true")
    ap.add_argument("--no-alerts", action="store_true")
    a = ap.parse_args()

    if a.synthetic:
        import synth
        raw, oas, fg = synth.make()
    else:
        import data
        raw = data.fetch_yahoo()
        oas = data.fetch_fred()
        fg = data.fetch_fear_greed()

    res, frames = {}, {}
    for key, cfg in INDICES.items():
        try:
            frames[key], res[key] = process(key, cfg, raw, oas)
            print(f"[ok] {key}: {res[key]['headline']}")
        except Exception as e:  # noqa
            import traceback; traceback.print_exc()
            print(f"[skip] {key}: {e}")
    if not res:
        raise SystemExit("Brak danych dla żadnego indeksu")

    out = {"generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
           "synthetic": a.synthetic,
           "usa": usa_summary(res, fg, frames[next(iter(frames))]),
           "indices": res, "phases": {str(k): v for k, v in PHASES.items()}}
    out = clean(out)
    path = os.path.join(a.out, "data.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    print(f"[ok] zapisano {path} ({os.path.getsize(path)/1e6:.2f} MB)")

    if not a.no_alerts:
        alerts.run(out, os.path.join(a.out, "state.json"))


if __name__ == "__main__":
    main()
