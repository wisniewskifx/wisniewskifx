"""Konfiguracja monitora korekt."""

START = "2004-01-01"

INDICES = {
    "SPX": dict(name="S&P 500", price="^GSPC", vol="^VIX", vol_name="VIX",
                ew=("RSP", "SPY"), weight=0.35),
    "NDX": dict(name="Nasdaq-100", price="^NDX", vol="^VXN", vol_name="VXN",
                ew=("QQEW", "QQQ"), weight=0.35),
    "RUT": dict(name="Russell 2000", price="^RUT", vol="^RVX", vol_name="RVX",
                ew=None, weight=0.15),
    "DJI": dict(name="Dow Jones", price="^DJI", vol="^VXD", vol_name="VXD",
                ew=None, weight=0.15),
}

COMMON = ["^VIX", "^VIX3M", "^VVIX", "HYG", "IEF"]

# progi faz (percentyle historyczne indeksu zmienności danego rynku)
P_FEAR = 0.75        # strach (~VIX 22-24)
P_PANIC = 0.90       # panika (~VIX 28-30)
DD_PULLBACK = -0.05
DD_CORRECTION = -0.10
DD_BEAR = -0.20

# model
NEAR = -0.03         # "dno blisko" = do końca epizodu cena nie spadnie więcej niż 3%
K = 80               # liczba analogów
H = 120              # horyzont Monte Carlo (sesje)
BLOCK = 10           # długość bloku w bootstrapie
N_SIM = 4000
CHART_DAYS = 760     # ~3 lata na wykresach

PHASES = {
    1: dict(name="HOSSA — ZERO SYGNAŁU", short="HOSSA", color="#3b82f6",
            action="Nic nie rób. Brak korekty — nie łap dołków, nie shortuj siły."),
    2: dict(name="PULLBACK — ZA WCZEŚNIE", short="PULLBACK", color="#a3a3a3",
            action="Przygotuj poziomy i listę. Nie kupuj — spadek dopiero się rozkręca."),
    3: dict(name="ESKALACJA — DNO PRZED NAMI", short="ESKALACJA", color="#f59e0b",
            action="Transza 1 — tylko w strefie mediany korekty. Sprzedaż jeszcze trwa."),
    4: dict(name="KAPITULACJA — STREFA DNA", short="KAPITULACJA", color="#ef4444",
            action="Transza 2. Kupuj strach — tu historycznie powstają dołki."),
    5: dict(name="DNO ZALICZONE — OSTATNI DZWONEK", short="DNO ZALICZONE", color="#22c55e",
            action="Transza 3 na teście dołka, stop pod dołkiem. Strach opada."),
    6: dict(name="BESSA — NIE UŚREDNIAJ", short="BESSA", color="#7f1d1d",
            action="Wstrzymaj dokupowanie. Odbicia do sprzedania. Czekaj na kolejną kapitulację."),
}
