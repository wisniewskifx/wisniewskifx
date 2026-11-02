"""Backtest planów transz (plany ustalone PRZED liczeniem).

Epizod: korekta (od rekordu, jak w monitorze), w której wystąpiła faza KAPITULACJA.
T1 = pierwszy dzień Kapitulacji w epizodzie, cena P1 = zamknięcie.
Termin: 120 sesji po T1 — niewydany kapitał kupowany na zamknięciu w dniu terminu.
Wynik: wartość całego kapitału 250 sesji po T1 (wszystkie plany porównywane na tę samą datę).

Plany:
 A  All-in na Kapitulacji          100% T1
 B  Siatka −5/−10%                 40% T1, 30% gdy cena ≤ P1·0,95, 30% gdy ≤ P1·0,90
 C  Siatka −10/−20%                40% T1, 30% przy −10%, 30% przy −20% od P1
 D  Kapitulacja + Dno zaliczone    40% T1, 60% w pierwszym dniu fazy DNO ZALICZONE po T1
 E  Mieszany                       40% T1, 30% przy −10% od P1, 30% w pierwszym DNO ZALICZONE (co nie zadziała — w terminie)
 F  Kolejne Kapitulacje            40% T1, 30% przy kolejnym wejściu w Kapitulację (po wyjściu z niej), 30% w DNO ZALICZONE
 G  Uśrednianie w czasie           25% T1 i po 25% co 20 sesji
"""
import json
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "engine"))
import data, features, phases  # noqa: E402
from config import INDICES  # noqa: E402

DEADLINE, HOR = 120, 250
raw = data.fetch_yahoo()
oas = data.fetch_fred()


def plan_buys(d, i1, plan):
    """Zwraca listę (indeks_dnia, udział) dla planu, z terminem."""
    c = d["close"].to_numpy()
    ph = d["phase"].to_numpy()
    P1 = c[i1]
    end = min(len(d) - 1, i1 + DEADLINE)
    buys = [(i1, 0.4)]
    def first(cond, start=i1 + 1):
        for j in range(start, end + 1):
            if cond(j):
                return j
        return None
    if plan == "A":
        return [(i1, 1.0)]
    if plan == "G":
        return [(min(i1 + 20 * k, end), 0.25) for k in range(4)]
    if plan in ("B", "C"):
        l1, l2 = (0.95, 0.90) if plan == "B" else (0.90, 0.80)
        j1 = first(lambda j: c[j] <= P1 * l1)
        j2 = first(lambda j: c[j] <= P1 * l2)
        return buys + [(j1 if j1 is not None else end, 0.3), (j2 if j2 is not None else end, 0.3)]
    if plan == "D":
        j = first(lambda j: ph[j] == 5)
        return buys + [(j if j is not None else end, 0.6)]
    if plan == "E":
        j1 = first(lambda j: c[j] <= P1 * 0.90)
        j2 = first(lambda j: ph[j] == 5)
        return buys + [(j1 if j1 is not None else end, 0.3), (j2 if j2 is not None else end, 0.3)]
    if plan == "F":
        left = first(lambda j: ph[j] != 4)
        j1 = first(lambda j: ph[j] == 4 and ph[j - 1] != 4, (left or end) + 1) if left else None
        j2 = first(lambda j: ph[j] == 5)
        return buys + [(j1 if j1 is not None else end, 0.3), (j2 if j2 is not None else end, 0.3)]
    raise ValueError(plan)


PLANS = {"A": "All-in na Kapitulacji", "B": "40% + siatka −5/−10%", "C": "40% + siatka −10/−20%",
         "D": "40% + 60% w Dno zaliczone", "E": "40% + 30% przy −10% + 30% w Dno zaliczone",
         "F": "40% + 30% kolejna Kapitulacja + 30% Dno zaliczone", "G": "4 × 25% co 20 sesji"}

rows = []
for key, cfg in INDICES.items():
    try:
        d = features.build(raw, cfg, oas)
        phases.classify(d)
    except Exception as e:  # noqa
        print("skip", key, e)
        continue
    c = d["close"].to_numpy()
    for e, seg in d.groupby("episode"):
        p4 = seg.index[seg["phase"] == 4]
        if not len(p4):
            continue
        i1 = d.index.get_loc(p4[0])
        if i1 + HOR >= len(d):
            continue
        trough = seg["close"].min()
        final_dd = seg["dd"].min()
        r = {"idx": key, "t1": str(p4[0].date()), "dd_t1": float(d["dd"].iat[i1]), "final_dd": float(final_dd),
             "further": float(trough / c[i1] - 1), "big": bool(final_dd <= -0.20)}
        vals = {}
        for p in PLANS:
            b = plan_buys(d, i1, p)
            units = sum(w / c[j] for j, w in b)
            cost = 1.0 / units
            vals[p] = units * c[i1 + HOR]
            r[f"cost_{p}"] = float(cost / c[i1] - 1)          # średnia cena vs P1
            r[f"vs_trough_{p}"] = float(cost / trough - 1)     # średnia cena vs dno
            r[f"val_{p}"] = float(vals[p])
            r[f"deadline_{p}"] = float(sum(w for j, w in b if j == min(len(d) - 1, i1 + DEADLINE) and j != i1))
        rows.append(r)

df = pd.DataFrame(rows)
L = ["# Backtest planów transz (od 2006, fazy z monitora)", "",
     f"Epizody z Kapitulacją: {len(df)} (S&P {sum(df.idx=='SPX')}, Nasdaq {sum(df.idx=='NDX')}, Russell {sum(df.idx=='RUT')}, Dow {sum(df.idx=='DJI')}). "
     f"W tym duże (≥20%): {int(df.big.sum())}. Po pierwszej Kapitulacji rynek spadał dalej: mediana {df.further.median()*100:.1f}%, "
     f"w {(df.further < -0.05).mean()*100:.0f}% epizodów o ponad 5%, w {(df.further < -0.10).mean()*100:.0f}% o ponad 10%.", ""]


def table(sub, title):
    out = [f"## {title} (n={len(sub)})", "", "| Plan | Śr. cena vs T1 | Śr. cena vs dno | Wynik po 250 sesjach vs All-in (mediana) | Lepszy od All-in | Najgorszy epizod vs All-in | Kapitał kupiony w terminie |",
           "|---|---|---|---|---|---|---|"]
    res = {}
    for p, name in PLANS.items():
        rel = sub[f"val_{p}"] / sub["val_A"] - 1
        res[p] = {"cost": sub[f"cost_{p}"].median(), "vs_trough": sub[f"vs_trough_{p}"].median(), "rel_med": rel.median(),
                  "rel_mean": rel.mean(), "win": (rel > 0.0005).mean(), "worst": rel.min(), "deadline": sub[f"deadline_{p}"].mean()}
        x = res[p]
        out.append(f"| {p}. {name} | {x['cost']*100:+.1f}% | {x['vs_trough']*100:+.1f}% | {x['rel_med']*100:+.1f}% (śr. {x['rel_mean']*100:+.1f}%) | "
                   f"{x['win']*100:.0f}% | {x['worst']*100:+.1f}% | {x['deadline']*100:.0f}% |")
    return out + [""], res


R = {}
for sub, title, k in [(df, "Wszystkie epizody", "all"), (df[~df.big], "Małe korekty (<20%)", "small"), (df[df.big], "Duże korekty / bessy (≥20%)", "big"),
                      (df[df.idx == "NDX"], "Tylko Nasdaq-100", "ndx")]:
    if len(sub):
        t, R[k] = table(sub, title)
        L += t
L += ["## Epizody", "", "| Indeks | T1 | DD w T1 | Dalszy spadek | Korekta | " + " | ".join(f"{p} vs A" for p in PLANS if p != "A") + " |",
      "|---|---|---|---|---|" + "---|" * (len(PLANS) - 1)]
for _, r in df.sort_values("t1").iterrows():
    L.append(f"| {r.idx} | {r.t1} | {r.dd_t1*100:.1f}% | {r.further*100:.1f}% | {r.final_dd*100:.1f}% | "
             + " | ".join(f"{(r[f'val_{p}']/r['val_A']-1)*100:+.1f}%" for p in PLANS if p != "A") + " |")
open(os.path.join(HERE, "tranches.md"), "w", encoding="utf-8").write("\n".join(L))
json.dump({"summary": R, "episodes": rows}, open(os.path.join(HERE, "tranches.json"), "w"), default=float, indent=1)
print("\n".join(L[:60]))
