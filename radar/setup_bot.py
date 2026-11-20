"""Configura il bot una volta: comandi nel menu "/", bottone Dashboard nella chat privata,
messaggio fisso con la dashboard nel gruppo.

Uso:  python -m radar.setup_bot
"""
from __future__ import annotations

import json
import sys

from . import config, telegram
from .main import carica_env


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    carica_env()
    if not telegram.attivo():
        print("Manca TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_ID nel file .env")
        return
    comandi = json.dumps([{"command": c, "description": d} for c, d in telegram.COMANDI])
    for scope in ({"type": "default"}, {"type": "all_group_chats"}):
        r = telegram.api("setMyCommands", commands=comandi, scope=json.dumps(scope), chat_id=None)
        print(f"Comandi del menu ({scope['type']}):", "ok" if r.ok else r.text[:150])
    # nella chat privata col bot, il bottone accanto al campo di scrittura apre la dashboard dentro Telegram
    r = telegram.api("setChatMenuButton", chat_id=None, menu_button=json.dumps(
        {"type": "web_app", "text": "Dashboard", "web_app": {"url": config.DASHBOARD}}))
    print("Bottone Dashboard nella chat privata:", "ok" if r.ok else r.text[:150])
    r = telegram.api("sendMessage", text=telegram.DASHBOARD_TESTO + "\n\n📌 Messaggio fissato: lo trovate sempre in alto.",
                     parse_mode="HTML", reply_markup=telegram.bottone_dashboard(),
                     disable_web_page_preview="true", disable_notification="true")
    if not r.ok:
        print("Messaggio nel gruppo non inviato:", r.text[:150])
        return
    mid = r.json()["result"]["message_id"]
    r = telegram.api("pinChatMessage", message_id=mid, disable_notification="true")
    print("Messaggio fissato nel gruppo:", "ok" if r.ok else
          "non riuscito (il bot deve essere amministratore del gruppo): " + r.text[:150])


if __name__ == "__main__":
    main()
