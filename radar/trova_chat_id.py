"""Trova il chat id del gruppo Telegram e lo scrive nel file .env.

Prima: metti il token del bot in .env, aggiungi il bot al gruppo e scrivi /start nel gruppo.
Poi:   python -m radar.trova_chat_id           (gruppo principale: TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID)
       python -m radar.trova_chat_id amici     (gruppo degli amici: TELEGRAM_BOT_TOKEN_2 / TELEGRAM_CHAT_ID_2)
"""
from __future__ import annotations

import os
import re
import sys

import requests

from .config import ROOT
from .profili import PROFILI

ENV = ROOT / ".env"


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    nome = sys.argv[1] if len(sys.argv) > 1 else "noi"
    p = next((x for x in PROFILI if x.nome == nome), None)
    if p is None:
        print(f"Profilo sconosciuto: {nome}. Profili: " + ", ".join(x.nome for x in PROFILI))
        return
    tok_var, chat_var = p.token_env, p.chat_env
    if not ENV.exists():
        print("Non trovo il file .env nella cartella del radar.")
        return
    text = ENV.read_text(encoding="utf-8-sig")
    m = re.search(rf"^{tok_var}=(.*)$", text, re.M)
    token = (m.group(1) if m else "").strip().strip('"').strip("'").replace(" ", "")
    if not token:
        print(f"Nel file .env manca il token: scrivilo dopo {tok_var}= e salva.")
        return
    if token.lower().startswith("bot"):
        token = token[3:]   # errore comune: "bot" incollato davanti al token
    try:
        r = requests.get(f"https://api.telegram.org/bot{token}/getUpdates", timeout=30)
        data = r.json()
    except Exception as e:
        print(f"Non riesco a contattare Telegram: {e}")
        return
    if not data.get("ok"):
        print("Telegram dice che il token non è valido. Ricopialo da BotFather "
              "(/mybots → il tuo bot → API Token), tutto intero, e salva di nuovo il file .env.")
        return
    chats = {}
    for upd in data.get("result", []):
        msg = (upd.get("message") or upd.get("edited_message") or upd.get("channel_post")
               or upd.get("my_chat_member") or {})  # anche "il bot è stato aggiunto al gruppo"
        chat = msg.get("chat") or {}
        if chat.get("id") is not None:
            chats[chat["id"]] = chat.get("title") or chat.get("first_name") or chat.get("username") or ""
    if not chats:
        print("Il token è giusto, ma il bot non ha ancora ricevuto messaggi.\n"
              "Aggiungi il bot al gruppo, scrivi /start nel gruppo e rilancia questo programma.")
        return
    gruppi = [(k, v) for k, v in chats.items() if k < 0]
    chat_id, name = (gruppi or list(chats.items()))[-1]
    new = re.sub(rf"^{chat_var}=.*$", f"{chat_var}={chat_id}", text, flags=re.M)
    if new == text and f"{chat_var}={chat_id}" not in text:
        new = text.rstrip("\n") + f"\n{chat_var}={chat_id}\n"
    ENV.write_text(new, encoding="utf-8")
    os.environ[chat_var] = str(chat_id)
    print(f"Trovato! Chat id {chat_id} ({name}). L'ho scritto nel file .env come {chat_var}.")
    r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                      data={"chat_id": chat_id, "text": f"✅ {p.titolo} collegato a questo gruppo. Scrivete /stato per i comandi."},
                      timeout=30)
    print("Ti ho mandato un messaggio di conferma su Telegram." if r.ok else
          "Chat id salvato, ma il messaggio di conferma non è partito.")


if __name__ == "__main__":
    main()
