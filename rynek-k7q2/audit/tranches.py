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
 H  Więcej od razu                 60% T1, 40% w pierwszym DNO ZALICZONE

TEST WARUNKOWY (kryteria ustalone przed liczeniem):
 Kredyt w T1: zmiana HYG/IEF w 20 sesjach ≤ −2,5% = STRES, inaczej SPOKÓJ (próg już używany w monitorze).
 T1: P(bessa ≥20% | stres) ≥ 2 × P(bessa | spokój), przy ≥ 5 epizodach w grupie stres.
 T2: reguła (stres → B, spokój → H) ma średnią i medianę wyniku vs A > 0, średnią wyższą niż każdy plan bezwarunkowy,
     i średnią > 0 na ≥ 3 z 4 indeksów.
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
    if plan == "H":
        j = first(lambda j: ph[j] == 5)
        return [(i1, 0.6), (j if j is not None else end, 0.4)]
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
         "F": "40% + 30% kolejna Kapitulacja + 30% Dno zaliczone", "G": "4 × 25% co 20 sesji",
         "H": "60% + 40% w Dno zaliczone"}

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
             "further": float(trough / c[i1] - 1), "big": bool(final_dd <= -0.20),
             "credit20": float(d["credit_20d"].iat[i1]) if pd.notna(d["credit_20d"].iat[i1]) else None}
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
# ---------------- TEST WARUNKOWY ----------------
cd = df[df.credit20.notna()].copy()
cd["stress"] = cd.credit20 <= -0.025
cd["rule"] = np.where(cd.stress, cd.val_B, cd.val_H)
rel = lambda col: cd[col] / cd.val_A - 1
ns, nc = int(cd.stress.sum()), int((~cd.stress).sum())
pb_s = cd[cd.stress].big.mean() if ns else float("nan")
pb_c = cd[~cd.stress].big.mean() if nc else float("nan")
t1 = ns >= 5 and pb_c >= 0 and pb_s >= 2 * pb_c
rr = rel("rule")
uncond = {p: rel(f"val_{p}").mean() for p in PLANS}
per_idx = cd.assign(r=rr).groupby("idx").r.mean()
t2 = rr.mean() > 0 and rr.median() > 0 and all(rr.mean() > v for p, v in uncond.items() if p != "A") and (per_idx > 0).sum() >= 3
L += ["## Test warunkowy: kredyt w dniu T1", "",
      f"Epizody z danymi kredytu (od 2007): {len(cd)} — STRES (HYG/IEF 20 sesji ≤ −2,5%): {ns}, SPOKÓJ: {nc}.", "",
      "| Grupa | n | Udział bess (≥20%) | Mediana dalszego spadku po T1 | Najlepszy plan (średnio vs A) |", "|---|---|---|---|---|"]
for lab, g in (("STRES", cd[cd.stress]), ("SPOKÓJ", cd[~cd.stress])):
    if len(g):
        best = max(PLANS, key=lambda p: (g[f"val_{p}"] / g.val_A - 1).mean())
        L.append(f"| {lab} | {len(g)} | {g.big.mean()*100:.0f}% | {g.further.median()*100:.1f}% | {best}. {PLANS[best]} ({(g[f'val_{best}']/g.val_A-1).mean()*100:+.1f}%) |")
L += ["", f"**T1 — rozróżnianie bess:** {pb_s*100:.0f}% vs {pb_c*100:.0f}% → {'✅ ZALICZONY' if t1 else '❌ NIEZALICZONY'} (wymóg: ≥2× i ≥5 epizodów w stresie)", "",
      "| Plan | Średnio vs A | Mediana vs A | Lepszy od A |", "|---|---|---|---|"]
for p in PLANS:
    x = rel(f"val_{p}")
    L.append(f"| {p}. {PLANS[p]} | {x.mean()*100:+.1f}% | {x.median()*100:+.1f}% | {(x > 0.0005).mean()*100:.0f}% |")
L += [f"| **Reguła: stres → B, spokój → H** | **{rr.mean()*100:+.1f}%** | **{rr.median()*100:+.1f}%** | **{(rr > 0.0005).mean()*100:.0f}%** |", "",
      "Reguła per indeks (średnio vs A): " + ", ".join(f"{k} {v*100:+.1f}%" for k, v in per_idx.items()), "",
      f"**T2 — reguła warunkowa:** {'✅ ZALICZONY' if t2 else '❌ NIEZALICZONY'}", "",
      "Wrażliwość progu (tylko informacyjnie, decyzja na −2,5%):"]
for th in (-0.015, -0.02, -0.03, -0.035):
    st = cd.credit20 <= th
    r_ = np.where(st, cd.val_B, cd.val_H) / cd.val_A - 1
    L.append(f"- próg {th*100:.1f}%: stres n={int(st.sum())}, bessy w stresie {cd[st].big.mean()*100 if st.any() else float('nan'):.0f}% vs spokój {cd[~st].big.mean()*100:.0f}%, reguła średnio {np.mean(r_)*100:+.1f}%")
L += ["", "Epizody w grupie STRES: " + ", ".join(f"{r.idx} {r.t1} ({r.credit20*100:.1f}%, korekta {r.final_dd*100:.0f}%)" for _, r in cd[cd.stress].iterrows()), ""]
R["conditional"] = {"t1": bool(t1), "t2": bool(t2), "n_stress": ns, "n_calm": nc, "big_stress": float(pb_s), "big_calm": float(pb_c),
                    "rule_mean": float(rr.mean()), "rule_med": float(rr.median()), "uncond": {k: float(v) for k, v in uncond.items()}}

L += ["## Epizody", "", "| Indeks | T1 | DD w T1 | Dalszy spadek | Korekta | " + " | ".join(f"{p} vs A" for p in PLANS if p != "A") + " |",
      "|---|---|---|---|---|" + "---|" * (len(PLANS) - 1)]
for _, r in df.sort_values("t1").iterrows():
    L.append(f"| {r.idx} | {r.t1} | {r.dd_t1*100:.1f}% | {r.further*100:.1f}% | {r.final_dd*100:.1f}% | "
             + " | ".join(f"{(r[f'val_{p}']/r['val_A']-1)*100:+.1f}%" for p in PLANS if p != "A") + " |")
open(os.path.join(HERE, "tranches.md"), "w", encoding="utf-8").write("\n".join(L))
json.dump({"summary": R, "episodes": rows}, open(os.path.join(HERE, "tranches.json"), "w"), default=float, indent=1)
print("\n".join(L[:60]))
