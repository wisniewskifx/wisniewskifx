"""Niezależny audyt: pobiera dane od nowa i przelicza kluczowe liczby OSOBNYM kodem
(nie importuje silnika), porównuje z data.json i ze znanymi notowaniami historycznymi.
Wynik: audit.md (czytelny) i audit.json.
"""
import json
import os
import sys

import numpy as np
import pandas as pd
import yfinance as yf

HERE = os.path.dirname(__file__)
DATA = os.path.join(HERE, "..", "data.json")
OUT_MD = os.path.join(HERE, "audit.md")
OUT_JS = os.path.join(HERE, "audit.json")

T = ["^GSPC", "^NDX", "^IXIC", "^DJI", "^RUT", "^VIX", "^VXN", "^VIX3M", "^VVIX", "^RVX", "^VXD", "HYG", "IEF"]
raw = yf.download(T, start="1985-01-01", auto_adjust=True, progress=False)["Close"]
raw.index = pd.to_datetime(raw.index).tz_localize(None)
import time
for t in T:  # dociągnij pojedynczo serie, których batch nie zwrócił
    if t not in raw or raw[t].notna().sum() < 100:
        for _ in range(3):
            x = yf.download(t, start="1985-01-01", auto_adjust=True, progress=False)
            if len(x):
                c = x["Close"]
                c = c.iloc[:, 0] if isinstance(c, pd.DataFrame) else c
                c.index = pd.to_datetime(c.index).tz_localize(None)
                raw[t] = c.reindex(raw.index.union(c.index)).reindex(raw.index)
                break
            time.sleep(5)
D = json.load(open(DATA, encoding="utf-8"))
L = []
res = {"checks": [], "fail": 0}


def chk(name, got, exp, tol=0.005):
    ok = got is not None and exp is not None and not pd.isna(got) and abs(got / exp - 1) <= tol
    res["checks"].append({"name": name, "got": None if got is None or pd.isna(got) else float(got), "exp": exp, "ok": bool(ok)})
    if not ok:
        res["fail"] += 1
    L.append(f"| {'✅' if ok else '❌'} | {name} | {got if got is None or pd.isna(got) else round(float(got), 2)} | {exp} |")


def close(t, d):
    s = raw[t].dropna()
    d = pd.Timestamp(d)
    return s.loc[d] if d in s.index else None


# 1) KOTWICE: znane zamknięcia z historii
L += ["# Audyt danych i obliczeń", f"Wygenerowano z danych do {raw.index[-1].date()}", "",
      "## 1. Kotwice — znane historyczne zamknięcia (tolerancja 0,5%)", "", "| | Test | Dane Yahoo | Oczekiwane |", "|---|---|---|---|"]
for t, d, v in [("^GSPC", "2009-03-09", 676.53), ("^GSPC", "2018-12-24", 2351.10), ("^GSPC", "2020-03-23", 2237.40),
                ("^GSPC", "2022-10-12", 3577.03), ("^GSPC", "2025-04-08", 4982.77),
                ("^VIX", "2008-11-20", 80.86), ("^VIX", "2020-03-16", 82.69), ("^VIX", "2024-08-05", 38.57), ("^VIX", "2025-04-08", 52.33),
                ("^IXIC", "2020-02-19", 9817.18), ("^IXIC", "2020-03-23", 6860.67), ("^IXIC", "2021-11-19", 16057.44), ("^IXIC", "2022-12-28", 10213.29),
                ("^IXIC", "2025-10-29", 24019.99), ("^IXIC", "2026-03-30", 20794.64), ("^IXIC", "2026-06-01", 27190.21), ("^IXIC", "2026-07-29", 24442.94),
                ("^IXIC", "2026-10-30", 25437.00), ("^NDX", "2026-10-06", 31224.47), ("^NDX", "2026-10-30", 28384.85)]:
    chk(f"{t} {d}", close(t, d), v)


# 2) Korekty Nasdaq Composite >=10% od rekordu (zamknięcia) — do weryfikacji tabeli z pierwszej odpowiedzi
def corrections(s, thr=-0.10, since="2015-06-01", complete_only=False):
    s = s.dropna()
    pk = s.cummax()
    ep = (s >= pk).cumsum()
    out = []
    for e, seg in s.groupby(ep):
        dd = seg / seg.iloc[0] - 1
        if complete_only and seg.index[-1] == s.index[-1]:
            continue
        if dd.min() <= thr and seg.index[0] >= pd.Timestamp(since):
            t = seg.idxmin()
            out.append((seg.index[0].date(), round(float(seg.iloc[0]), 2), t.date(), round(float(seg.min()), 2),
                        round(float(dd.min()) * 100, 1), (t - seg.index[0]).days))
    return out


L += ["", "## 2. Korekty Nasdaq Composite ≥10% od rekordu (od 2015) — przeliczone z danych", "",
      "| Szczyt | Zamknięcie | Dno | Zamknięcie | Spadek % | Dni kalend. |", "|---|---|---|---|---|---|"]
cx = corrections(raw["^IXIC"])
for r in cx:
    L.append("| " + " | ".join(str(x) for x in r) + " |")
res["ixic_corrections"] = [list(map(str, r)) for r in cx]

# VIX w okolicy dołków (max zamknięcia ±3 sesje)
L += ["", "### VIX w okolicy dołków Composite (max zamknięcie ±3 sesje)", "", "| Dno | VIX max ±3 | VXN max ±3 |", "|---|---|---|"]
for r in cx:
    t = pd.Timestamp(r[2])
    i = raw.index.get_loc(t)
    w = raw.iloc[max(0, i - 3): i + 4]
    L.append(f"| {r[2]} | {w['^VIX'].max():.1f} | {w['^VXN'].max():.1f} |")

# 3) Zgodność silnika: drawdown dziś i lista korekt
L += ["", "## 3. Zgodność z silnikiem (data.json) — przeliczenie niezależne", "", "| | Test | Niezależnie | Silnik |", "|---|---|---|---|"]
M = {"SPX": "^GSPC", "NDX": "^NDX", "RUT": "^RUT", "DJI": "^DJI"}
for k, t in M.items():
    s = raw[t].dropna()
    s = s[s.index >= "2004-01-01"]
    dd = float(s.iloc[-1] / s.cummax().iloc[-1] - 1)
    eng = D["indices"][k]["dd"]
    ok = abs(dd - eng) < 0.002
    res["fail"] += 0 if ok else 1
    L.append(f"| {'✅' if ok else '❌'} | {k} drawdown dziś | {dd:.4f} | {eng:.4f} |")
    ind = corrections(s, -0.10, "2004-01-01", complete_only=True)
    eng_c = [c for c in D["indices"][k]["corrections"] if not c["ongoing"]]
    n_ok = len(ind) == len(eng_c)
    L.append(f"| {'✅' if n_ok else '❌'} | {k} liczba zakończonych korekt ≥10% od 2004 | {len(ind)} | {len(eng_c)} |")
    res["fail"] += 0 if n_ok else 1
    worst_i = min(r[4] for r in ind) / 100 if ind else None
    worst_e = min(c["depth"] for c in eng_c) if eng_c else None
    okw = worst_i is not None and abs(worst_i - worst_e) < 0.002
    L.append(f"| {'✅' if okw else '❌'} | {k} najgłębsza korekta | {worst_i:.4f} | {worst_e:.4f} |")
    res["fail"] += 0 if okw else 1

# 4) Wartości wskaźników w dniach dołków NDX (z tabeli Sprawdzalności)
L += ["", "## 4. Wartości w dniach dołków NDX — niezależnie vs silnik", "",
      "| Dno | VXN max ±5 (niez.) | silnik | VIX/VIX3M max ±5 (niez.) | silnik | RSI min ±5 (niez.) | silnik |", "|---|---|---|---|---|---|---|"]
s = raw["^NDX"].dropna()
dlt = s.diff()
up = dlt.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
dn = (-dlt.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
rsi = 100 - 100 / (1 + up / dn)
term = raw["^VIX"] / raw["^VIX3M"]
for t in D["indices"]["NDX"]["verify"]["troughs"][-6:]:
    d = pd.Timestamp(t["trough"])
    i = s.index.get_loc(d)
    w = s.index[max(0, i - 5): i + 6]
    vxn = raw["^VXN"].reindex(w).max()
    tm = term.reindex(w).max()
    rm = rsi.reindex(w).min()
    L.append(f"| {t['trough']} | {vxn:.2f} | {t['vol_max_win']} | {tm:.3f} | {t['term_max_win']} | {rm:.1f} | {t['rsi_min_win']} |")
    for a, b, n in [(vxn, t["vol_max_win"], "VXN"), (tm, t["term_max_win"], "term"), (rm, t["rsi_min_win"], "RSI")]:
        if b is None or abs(a - b) > max(0.02 * abs(b), 0.05):
            res["fail"] += 1
            res["checks"].append({"name": f"NDX {t['trough']} {n}", "got": float(a), "exp": b, "ok": False})

# 5) Statystyka bazowa: zwrot 60 sesji po dniach z DD<=-10% (bez filtra kompletności epizodu — przybliżenie)
L += ["", "## 5. Statystyki bazowe — niezależnie (bez filtra zakończonych epizodów, więc ±)", "",
      "| Indeks | DD≤−10%: mediana 60 ses. (niez.) | silnik | % zysku (niez.) | silnik | Dowolny dzień mediana (niez.) | silnik |", "|---|---|---|---|---|---|---|"]
for k, t in M.items():
    s = raw[t].dropna()
    s = s[s.index >= "2006-01-01"]
    dd = s / s.cummax() - 1
    f60 = s.shift(-60) / s - 1
    m = (dd <= -0.10) & f60.notna()
    g = D["indices"][k]["verify"]["signals"]
    L.append(f"| {k} | {f60[m].median():+.4f} | {g['base']['ret60_med']:+.4f} | {(f60[m] > 0).mean():.3f} | {g['base']['win60']:.3f} | "
             f"{f60.dropna().median():+.4f} | {g['all']['ret60_med']:+.4f} |")

# 6) Liderzy: niezależne przeliczenie 'lider vs najsilniejszy' (52-tyg. szczyt, start: lider dotyka -10%)
L += ["", "## 6. Liderzy spadków — niezależny przelicznik", ""]
px = pd.DataFrame({k: raw[t] for k, t in M.items()}).dropna(subset=["^GSPC" if False else "SPX"]).ffill(limit=5)
dd52 = px / px.rolling(252, min_periods=1).max() - 1
R = D.get("rotation") or {}
ev = [e for e in R.get("events", []) if e["complete"]]
mism = 0
for e in ev:
    t10 = pd.Timestamp(e["t10"])
    i = px.index.get_loc(t10)
    if i + 250 >= len(px):
        continue
    rl = px[e["leader"]].iat[i + 250] / px[e["leader"]].iat[i] - 1
    eng = e["fwd"]["250"][e["leader"]]
    if eng is None or abs(rl - eng) > 1e-3:
        mism += 1
L.append(f"Zgodność zwrotów 250 sesji lidera z silnikiem: {len(ev) - mism}/{len(ev)} zdarzeń zgodnych.")
res["fail"] += mism
sel = [e for e in ev if e["selective"] and e["fwd"]["250"][e["leader"]] is not None and e["fwd"]["250"][e["laggard_at10"]] is not None]
if sel:
    rel = np.median([e["fwd"]["250"][e["leader"]] - e["fwd"]["250"][e["laggard_at10"]] for e in sel])
    L.append(f"Selektywne: mediana lider−najsilniejszy po 250 sesjach (niezależnie z listy zdarzeń): {rel:+.4f}; silnik: {R['leader_vs_laggard']['selective']['250']['rel_med']:+.4f}")

# 7) Dostępność danych zmienności
L += ["", "## 7. Kompletność danych", "", "| Seria | Pierwsza data | Ostatnia data | Braki w ostatnich 60 sesjach |", "|---|---|---|---|"]
for t in ["^VIX", "^VIX3M", "^VVIX", "^VXN", "^RVX", "^VXD", "HYG", "IEF"]:
    s = raw[t]
    L.append(f"| {t} | {s.first_valid_index().date() if s.notna().any() else '—'} | {s.last_valid_index().date() if s.notna().any() else '—'} | {int(s.iloc[-60:].isna().sum())} |")

L += ["", f"## Wynik: {'✅ wszystko zgodne' if res['fail'] == 0 else f'❌ niezgodności: {res[chr(102)+chr(97)+chr(105)+chr(108)]}'}"]
open(OUT_MD, "w", encoding="utf-8").write("\n".join(L))
json.dump(res, open(OUT_JS, "w"), ensure_ascii=False, indent=1, default=str)
print("\n".join(L))
