"""Alerty Telegram: zmiana fazy, przejście Bottom Score przez progi, dzienne podsumowanie."""
import json
import os

import requests

SITE = os.environ.get("SITE_URL", "https://wisniewskifx.com/rynek-k7q2/")
EMOJI = {1: "🔵", 2: "⚪", 3: "🟠", 4: "🔴", 5: "🟢", 6: "🟤"}


def send(text):
    tok, chat = os.environ.get("TELEGRAM_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if not tok or not chat:
        print("[alert] (brak TELEGRAM_TOKEN/CHAT_ID)\n" + text)
        return
    try:
        requests.post(f"https://api.telegram.org/bot{tok}/sendMessage",
                      json={"chat_id": chat, "text": text, "disable_web_page_preview": True},
                      timeout=20)
    except Exception as e:  # noqa
        print("[alert] błąd wysyłki:", e)


def bucket(x):
    return None if x is None else (2 if x >= 70 else 1 if x >= 50 else 0)


def run(out, state_path):
    try:
        prev = json.load(open(state_path, encoding="utf-8"))
    except Exception:
        prev = {}
    msgs, state = [], {}
    for k, r in out["indices"].items():
        p, b = r["phase"]["id"], r["bottom"]
        state[k] = {"phase": p, "bucket": bucket(b)}
        pv = prev.get(k, {})
        if pv and pv.get("phase") != p:
            msgs.append(f"{EMOJI[p]} {r['name']}: {out['phases'][str(pv['phase'])]['short']} → "
                        f"{r['phase']['name']}\n{r['phase']['action']}\n{r['headline']}")
        elif pv and bucket(b) is not None and pv.get("bucket") is not None and bucket(b) > pv["bucket"]:
            msgs.append(f"📈 {r['name']}: Bottom Score {b:.0f}/100 (próg {'70' if bucket(b) == 2 else '50'})\n{r['headline']}")
    cons = out["usa"]["consensus"]["id"]
    state["USA"] = {"phase": cons}
    if prev.get("USA", {}).get("phase") not in (None, cons):
        msgs.append(f"🇺🇸 Konsensus USA → {out['usa']['consensus']['name']}")

    if os.environ.get("DAILY_SUMMARY") == "1":
        lines = [f"📊 Zamknięcie USA — {out['usa']['headline']}"]
        for k, r in out["indices"].items():
            b = f"{r['bottom']:.0f}" if r["bottom"] is not None else "—"
            lines.append(f"{EMOJI[r['phase']['id']]} {k} {r['dd']:+.1%} | {r['phase']['short']} | BS {b}")
        msgs.append("\n".join(lines))

    if msgs:
        send("\n\n".join(msgs) + f"\n\n{SITE}")
    json.dump(state, open(state_path, "w", encoding="utf-8"))
