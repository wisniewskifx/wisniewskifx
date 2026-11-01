"""Karty wskaźników: wartość, percentyl, momentum (vs średnia 3d/10d) i werdykt."""
import numpy as np
import pandas as pd

# status: far = daleko od dna, approach = zbliżamy się, zone = strefa dna,
#         past = dno prawdopodobnie za nami, risk = ryzyko pogłębienia (systemowe)


def _f(x):
    return None if x is None or (isinstance(x, float) and np.isnan(x)) else float(x)


def _mom(s):
    s = s.dropna()
    if len(s) < 11:
        return None, None
    v = s.iloc[-1]
    return _f(v - s.iloc[-3:].mean()), _f(v - s.iloc[-10:].mean())


def _pct(s):
    s = s.dropna()
    return _f((s < s.iloc[-1]).mean()) if len(s) > 250 else None


def _spark(s, n=120):
    s = s.iloc[-n:]
    ma = s.rolling(10, min_periods=1).mean()
    return {"d": [x.strftime("%Y-%m-%d") for x in s.index],
            "v": [None if pd.isna(x) else round(float(x), 4) for x in s],
            "ma": [None if pd.isna(x) else round(float(x), 4) for x in ma]}


def card(key, label, s, unit, status, verdict, explain, scale=1.0, dec=1):
    s = s * scale
    d3, d10 = _mom(s)
    last = s.dropna()
    return {"key": key, "label": label, "value": _f(last.iloc[-1]) if len(last) else None,
            "unit": unit, "dec": dec, "pct": _pct(s), "d3": d3, "d10": d10,
            "status": status, "verdict": verdict, "explain": explain, "spark": _spark(s)}


def build_cards(d, cfg):
    r = d.iloc[-1]
    vn = cfg["vol_name"] if not d.attrs.get("vol_fallback") else "VIX (zastępczo)"
    out = []

    # 1. Drawdown
    dd = r["dd"]
    st = "far" if dd > -0.05 else "approach" if dd > -0.10 else "zone" if dd > -0.20 else "risk"
    out.append(card("dd", "Drawdown od rekordu", d["dd"], "%", st,
                    f"{dd:.1%} od szczytu, {int(r['days_from_peak'])} sesji. "
                    + ("Brak korekty." if dd > -0.05 else "Pullback." if dd > -0.10 else
                       "Korekta (mediana historyczna kończy się ok. −12/−13%)." if dd > -0.20 else
                       "Terytorium bessy."),
                    "Ile indeks jest pod rekordem. Korekta = −10%, bessa = −20%.", scale=100))

    # 2. Indeks zmienności
    vp, off, peak15 = r["vol_pct"], r["vol_off_high"], r["vol_peak15_pct"]
    if peak15 >= 0.70 and off <= -0.20:
        st, v = "past", f"Strach opada: {off:.0%} od 10-dniowego szczytu. Historycznie dołek zwykle był 0–5 sesji przed takim odwrotem."
    elif vp >= 0.90 and off > -0.12:
        st, v = "zone", f"Panika ({vp:.0%} pct). Strefa, w której powstają dołki — czekaj na odwrót {vn}."
    elif r["vol_d10"] > 0.05:
        st, v = "approach", f"{vn} rośnie (+{r['vol_d10']:.0%} vs śr. 10d). Strach narasta — dno raczej przed nami."
    elif vp < 0.5:
        st, v = "far", f"{vn} nisko ({vp:.0%} pct). Brak strachu = brak dna."
    else:
        st, v = "approach", f"{vn} podwyższony ({vp:.0%} pct), bez wyraźnego kierunku."
    out.append(card("vol", vn, d["vol"], "", st, v,
                    f"Implikowana zmienność opcji na {cfg['name']}. Szpic + odwrót = klasyczny timer dołka."))

    # 3. Odwrót zmienności
    st = "past" if off <= -0.20 else "zone" if off > -0.05 and vp >= 0.85 else "approach" if off > -0.10 else "far"
    out.append(card("vol_off", f"{vn} vs szczyt 10d", d["vol_off_high"], "%", st,
                    f"{off:.0%} pod 10-dniowym maksimum. " +
                    ("Odwrót potwierdzony (≤ −20%)." if off <= -0.20 else
                     "Zmienność przy szczycie — jeśli to panika, dołek jest blisko." if off > -0.05 else
                     "Pierwsze oznaki uspokojenia."),
                    "Sygnał: zamknięcie ≥20% pod szczytem 10d po szpicu = strach się wyczerpał.", scale=100))

    # 4. Struktura terminowa
    tm, tmax = r["vix_term"], r["vix_term_max15"]
    if tmax >= 1 and tm < 1:
        st, v = "past", f"VIX/VIX3M {tm:.2f}: wrócił do contango po panice — jeden z najlepszych sygnałów dna."
    elif tm >= 1:
        st, v = "zone", f"VIX/VIX3M {tm:.2f} > 1: backwardation = panika krótkoterminowa. Strefa dna."
    elif tm >= 0.93:
        st, v = "approach", f"VIX/VIX3M {tm:.2f}: zbliża się do 1 — napięcie rośnie."
    else:
        st, v = "far", f"VIX/VIX3M {tm:.2f}: normalne contango, brak paniki."
    out.append(card("term", "VIX / VIX3M", d["vix_term"], "", st, v,
                    "Struktura terminowa. >1 = rynek boi się bardziej teraz niż za 3 mies. (panika).", dec=2))

    # 5. VVIX
    if d["vvix"].notna().sum() > 300:
        vv = r["vvix_pct"]
        st = "zone" if vv >= 0.85 else "approach" if vv >= 0.65 else "far"
        out.append(card("vvix", "VVIX (zmienność VIX)", d["vvix"], "", st,
                        f"VVIX {r['vvix']:.0f} ({vv:.0%} pct). " +
                        ("Popyt na ochronę ekstremalny — typowe dla kapitulacji." if vv >= 0.85 else
                         "Podwyższony." if vv >= 0.65 else "Spokojny."),
                        "Zmienność samego VIX. Skacze >120–130 przy kapitulacjach."))

    # 6. Spread vs VIX
    if d["spread"].notna().sum() > 300:
        sp = r["spread"]
        sp10 = d["spread"].iloc[-10:].mean()
        sec = sp > sp10 + 1
        out.append(card("spread", f"Spread {vn} − VIX", d["spread"], " pkt",
                        "approach" if sec else "far",
                        f"{sp:+.1f} pkt (śr. 10d {sp10:+.1f}). " +
                        ("Rozszerza się → stres specyficzny dla tego indeksu (rotacja sektorowa), nie panika rynkowa."
                         if sec else "Stabilny — stres rozłożony równo z S&P 500."),
                        "Ile więcej strachu jest w tym indeksie niż w S&P 500."))

    # 7. Kredyt
    cr = r["credit_20d"]
    st = "risk" if cr <= -0.025 else "approach" if cr <= -0.01 else "far"
    out.append(card("credit", "Kredyt HYG/IEF (20d)", d["credit_20d"], "%", st,
                    f"{cr:+.1%} w 20 sesji. " +
                    ("Stres kredytowy — ryzyko, że to duża korekta/bessa, nie mała." if cr <= -0.025 else
                     "Lekkie pogorszenie." if cr <= -0.01 else
                     "Kredyt spokojny — rynek nie wycenia problemu w gospodarce (sprzyja małej korekcie)."),
                    "Obligacje śmieciowe vs skarbowe. Spadek = ucieczka od ryzyka kredytowego.", scale=100))

    # 8. HY OAS
    if d["oas"].notna().sum() > 300:
        o, o20 = r["oas"], r["oas_20d"]
        st = "risk" if o20 >= 1.0 else "approach" if o20 >= 0.4 else "far"
        out.append(card("oas", "HY OAS (FRED)", d["oas"], "%", st,
                        f"{o:.2f}% ({o20:+.2f} pp w 20 sesji). " +
                        ("Spready eksplodują — stres systemowy." if o20 >= 1.0 else
                         "Spready rosną." if o20 >= 0.4 else "Spready stabilne."),
                        "Premia za ryzyko obligacji high yield. Wzrost >1pp w miesiąc = alarm.", dec=2))

    # 9. Breadth
    if d["breadth_20d"].notna().sum() > 300:
        b = r["breadth_20d"]
        st = "zone" if b <= -0.03 else "approach" if b <= -0.01 else "far"
        out.append(card("breadth", "Breadth: equal-weight vs cap (20d)", d["breadth_20d"], "%", st,
                        f"{b:+.1%}. " + ("Szeroka wyprzedaż — sprzedają wszystko (typowe przy dnie)." if b <= -0.03
                                          else "Equal-weight słabszy." if b <= -0.01 else
                                          "Spadek skupiony w liderach, szeroki rynek się trzyma."),
                        "Czy spadek jest szeroki (cały rynek), czy wąski (kilku gigantów).", scale=100))

    # 10. VRP
    vr = r["vrp"]
    st = "zone" if vr <= 0 else "approach" if vr <= 3 else "far"
    out.append(card("vrp", "Premia za zmienność (implied − realized)", d["vrp"], " pkt", st,
                    f"{vr:+.1f} pkt. " + ("Realized ≥ implied — rynek faktycznie się wali, typowe dla kapitulacji."
                                          if vr <= 0 else "Premia niska." if vr <= 3 else "Normalna premia — strach 'na zapas'."),
                    "Implied (opcje) minus realized vol 20d. Ujemna rzadko i zwykle przy dołkach."))

    # 11. RSI
    rs = r["rsi"]
    rmin = d["rsi"].iloc[-10:].min()
    if rmin <= 32 and rs > 40:
        st, v = "past", f"RSI {rs:.0f} — odbił z wyprzedania ({rmin:.0f}). Momentum zawróciło."
    elif rs <= 30:
        st, v = "zone", f"RSI {rs:.0f} — silne wyprzedanie."
    elif rs <= 40:
        st, v = "approach", f"RSI {rs:.0f} — słabość."
    else:
        st, v = "far", f"RSI {rs:.0f} — neutralnie."
    out.append(card("rsi", "RSI(14)", d["rsi"], "", st, v, "Momentum ceny. <30 wyprzedanie.", dec=0))

    # 12. MA200
    m2 = r["ma200_dist"]
    out.append(card("ma200", "Dystans od MA200", d["ma200_dist"], "%",
                    "far" if m2 > 0 else "approach" if m2 > -0.08 else "zone",
                    f"{m2:+.1%}. " + ("Nad MA200 — trend długoterminowy w górę." if m2 > 0 else
                                      "Pod MA200 — trend osłabiony." if m2 > -0.08 else "Głęboko pod MA200 — skrajne rozciągnięcie."),
                    "Odległość od 200-sesyjnej średniej.", scale=100))

    # 13. Dywergencja
    dv = r["div_recent"] >= 1
    out.append(card("div", "Dywergencja cena vs strach", d["divergence"].rolling(10).max(), "",
                    "past" if dv else "far",
                    "TAK — cena zrobiła nowy dołek przy niższym strachu. Sprzedający się wyczerpują."
                    if dv else "Brak — strach rośnie razem ze spadkami (lub brak nowych dołków).",
                    "Nowy 20-dniowy dołek ceny, a zmienność ≥15% pod swoim szczytem.", dec=0))
    return out
