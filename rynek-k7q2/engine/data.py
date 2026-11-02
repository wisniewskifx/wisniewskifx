"""Pobieranie danych: Yahoo Finance, FRED, CNN Fear & Greed."""
import io
import time

import pandas as pd
import requests

from config import START, INDICES, COMMON

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"}


def all_tickers():
    t = set(COMMON)
    for c in INDICES.values():
        t.update([c["price"], c["vol"]])
        if c["ew"]:
            t.update(c["ew"])
    return sorted(t)


def fetch_yahoo(tickers=None, retries=3):
    import yfinance as yf
    tickers = tickers or all_tickers()
    last = None
    for i in range(retries):
        try:
            raw = yf.download(tickers, start=START, auto_adjust=True,
                              progress=False, threads=True)
            df = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw[["Close"]]
            df = df.dropna(how="all")
            if len(df) > 1000:
                df.index = pd.to_datetime(df.index).tz_localize(None)
                return _refill(df, tickers)
        except Exception as e:  # noqa
            last = e
        time.sleep(5 * (i + 1))
    raise RuntimeError(f"Yahoo download failed: {last}")


def _refill(df, tickers, start=START):
    """Yahoo czasem zwraca w paczce puste/dziurawe serie — dociągnij je pojedynczo."""
    import yfinance as yf
    for t in tickers:
        bad = t not in df or df[t].iloc[-500:].notna().mean() < 0.9
        if not bad:
            continue
        for k in range(3):
            try:
                x = yf.download(t, start=start, auto_adjust=True, progress=False)
                if len(x):
                    c = x["Close"]
                    c = c.iloc[:, 0] if isinstance(c, pd.DataFrame) else c
                    c.index = pd.to_datetime(c.index).tz_localize(None)
                    df[t] = c.reindex(df.index)
                    break
            except Exception:  # noqa
                pass
            time.sleep(3 * (k + 1))
    return df


def fetch_long(start="1985-01-01", retries=3):
    """Długa historia samych indeksów (do analizy Nasdaq vs szeroki rynek)."""
    import yfinance as yf
    tick = ["^NDX", "^GSPC", "^DJI", "^RUT", "XLK", "XLF", "XLE", "XLV", "XLY", "XLP", "XLI", "XLU", "XLB", "^TNX", "^IRX"]
    for i in range(retries):
        try:
            raw = yf.download(tick, start=start, auto_adjust=True, progress=False, threads=True)
            df = raw["Close"].dropna(how="all")
            df.index = pd.to_datetime(df.index).tz_localize(None)
            if len(df) > 5000:
                return _refill(df, tick, start)
        except Exception:  # noqa
            pass
        time.sleep(5 * (i + 1))
    return None


def fetch_fred(series="BAMLH0A0HYM2"):
    try:
        r = requests.get(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}",
                         headers=UA, timeout=30)
        s = pd.read_csv(io.StringIO(r.text))
        s.columns = ["date", "v"]
        s["date"] = pd.to_datetime(s["date"])
        s["v"] = pd.to_numeric(s["v"], errors="coerce")
        return s.dropna().set_index("date")["v"]
    except Exception:
        return None


def fetch_fear_greed():
    try:
        r = requests.get("https://production.dataviz.cnn.io/index/fearandgreed/graphdata",
                         headers=UA, timeout=20)
        j = r.json()
        fg = j["fear_and_greed"]
        hist = j.get("fear_and_greed_historical", {}).get("data", [])
        h = [(pd.to_datetime(p["x"], unit="ms").strftime("%Y-%m-%d"), round(p["y"], 1))
             for p in hist][-250:]
        return {"score": round(float(fg["score"])), "rating": fg.get("rating", ""),
                "prev_week": round(float(fg.get("previous_1_week", 0) or 0)),
                "prev_month": round(float(fg.get("previous_1_month", 0) or 0)),
                "hist": h}
    except Exception:
        return None
