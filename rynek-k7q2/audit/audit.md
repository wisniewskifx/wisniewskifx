# Audyt danych i obliczeń
Wygenerowano z danych do 2026-10-30

## 1. Kotwice — znane historyczne zamknięcia (tolerancja 0,5%)

| | Test | Dane Yahoo | Oczekiwane |
|---|---|---|---|
| ✅ | ^GSPC 2009-03-09 | 676.53 | 676.53 |
| ✅ | ^GSPC 2018-12-24 | 2351.1 | 2351.1 |
| ✅ | ^GSPC 2020-03-23 | 2237.4 | 2237.4 |
| ✅ | ^GSPC 2022-10-12 | 3577.03 | 3577.03 |
| ✅ | ^GSPC 2025-04-08 | 4982.77 | 4982.77 |
| ✅ | ^VIX 2008-11-20 | 80.86 | 80.86 |
| ✅ | ^VIX 2020-03-16 | 82.69 | 82.69 |
| ✅ | ^VIX 2024-08-05 | 38.57 | 38.57 |
| ✅ | ^VIX 2025-04-08 | 52.33 | 52.33 |
| ❌ | ^IXIC 2020-02-19 | None | 9817.18 |
| ❌ | ^IXIC 2020-03-23 | None | 6860.67 |
| ❌ | ^IXIC 2021-11-19 | None | 16057.44 |
| ❌ | ^IXIC 2022-12-28 | None | 10213.29 |
| ❌ | ^IXIC 2025-10-29 | None | 24019.99 |
| ❌ | ^IXIC 2026-03-30 | None | 20794.64 |
| ❌ | ^IXIC 2026-06-01 | None | 27190.21 |
| ❌ | ^IXIC 2026-07-29 | None | 24442.94 |
| ❌ | ^IXIC 2026-10-30 | None | 25437.0 |
| ✅ | ^NDX 2026-10-06 | 31224.47 | 31224.47 |
| ✅ | ^NDX 2026-10-30 | 28384.85 | 28384.85 |

## 2. Korekty Nasdaq Composite ≥10% od rekordu (od 2015) — przeliczone z danych

| Szczyt | Zamknięcie | Dno | Zamknięcie | Spadek % | Dni kalend. |
|---|---|---|---|---|---|

### VIX w okolicy dołków Composite (max zamknięcie ±3 sesje)

| Dno | VIX max ±3 | VXN max ±3 |
|---|---|---|

## 3. Zgodność z silnikiem (data.json) — przeliczenie niezależne

| | Test | Niezależnie | Silnik |
|---|---|---|---|
| ✅ | SPX drawdown dziś | -0.0305 | -0.0305 |
| ✅ | SPX liczba zakończonych korekt ≥10% od 2004 | 7 | 7 |
| ✅ | SPX najgłębsza korekta | -0.5680 | -0.5678 |
| ✅ | NDX drawdown dziś | -0.0909 | -0.0909 |
| ✅ | NDX liczba zakończonych korekt ≥10% od 2004 | 22 | 22 |
| ✅ | NDX najgłębsza korekta | -0.5370 | -0.5371 |
| ✅ | RUT drawdown dziś | -0.0836 | -0.0836 |
| ❌ | RUT liczba zakończonych korekt ≥10% od 2004 | 11 | 10 |
| ✅ | RUT najgłębsza korekta | -0.5990 | -0.5989 |
| ✅ | DJI drawdown dziś | -0.0474 | -0.0474 |
| ✅ | DJI liczba zakończonych korekt ≥10% od 2004 | 8 | 8 |
| ✅ | DJI najgłębsza korekta | -0.5380 | -0.5378 |

## 4. Wartości w dniach dołków NDX — niezależnie vs silnik

| Dno | VXN max ±5 (niez.) | silnik | VIX/VIX3M max ±5 (niez.) | silnik | RSI min ±5 (niez.) | silnik |
|---|---|---|---|---|---|---|
| 2022-12-28 | 29.11 | 29.11 | 0.933 | 0.933 | 33.6 | 33.6 |
| 2024-08-07 | 35.10 | 35.1 | 1.144 | 1.144 | 30.4 | 30.4 |
| 2025-04-08 | 43.25 | 43.25 | 1.274 | 1.274 | 23.1 | 23.1 |
| 2026-03-30 | 33.54 | 33.54 | 1.061 | 1.061 | 29.0 | 29.0 |
| 2026-07-29 | 30.84 | 30.84 | 0.961 | 0.961 | 32.1 | 32.1 |
| 2026-10-30 | 28.50 | 28.5 | 0.950 | 0.95 | 34.9 | 34.9 |

## 5. Statystyki bazowe — niezależnie (bez filtra zakończonych epizodów, więc ±)

| Indeks | DD≤−10%: mediana 60 ses. (niez.) | silnik | % zysku (niez.) | silnik | Dowolny dzień mediana (niez.) | silnik |
|---|---|---|---|---|---|---|
| SPX | +0.0413 | +0.0413 | 0.676 | 0.676 | +0.0345 | +0.0333 |
| NDX | +0.0728 | +0.0740 | 0.711 | 0.715 | +0.0451 | +0.0440 |
| RUT | +0.0504 | +0.0506 | 0.680 | 0.681 | +0.0282 | +0.0286 |
| DJI | +0.0494 | +0.0494 | 0.709 | 0.709 | +0.0280 | +0.0267 |

## 6. Liderzy spadków — niezależny przelicznik

Zgodność zwrotów 250 sesji lidera z silnikiem: 36/36 zdarzeń zgodnych.
Selektywne: mediana lider−najsilniejszy po 250 sesjach (niezależnie z listy zdarzeń): +0.0138; silnik: +0.0138

## 7. Kompletność danych

| Seria | Pierwsza data | Ostatnia data | Braki w ostatnich 60 sesjach |
|---|---|---|---|
| ^VIX | 1990-01-02 | 2026-10-30 | 0 |
| ^VIX3M | 2006-07-17 | 2026-10-30 | 1 |
| ^VVIX | 2007-01-03 | 2026-10-30 | 1 |
| ^VXN | 2001-01-23 | 2026-10-30 | 1 |
| ^RVX | — | — | 60 |
| ^VXD | 2005-11-22 | 2026-10-30 | 1 |
| HYG | 2007-04-11 | 2026-10-30 | 1 |
| IEF | 2002-07-30 | 2026-10-30 | 1 |

## Wynik: ❌ niezgodności: 10