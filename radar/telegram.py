"""Bot Telegram per il gruppo: schede degli annunci, bottoni condivisi, comandi."""
from __future__ import annotations

import html
import json
import os
import time

import requests

from . import config

TESTA = {"super": "🚨 <b>SUPER AFFARE</b>", "buono": "💡 <b>Buon affare</b>",
         "media": "🏠 <b>Prezzo nella media</b>", "caro": "🔺 <b>Caro</b>"}
AZIONI = {"like": "❤️ Mi piace", "call": "📞 Chiamato", "visit": "🗓 Visita", "no": "❌ Scarta"}


def attivo() -> bool:
    return bool(os.getenv("TELEGRAM_BOT_TOKEN") and os.getenv("TELEGRAM_CHAT_ID"))


def api(metodo: str, **data):
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    if metodo not in ("getUpdates", "answerCallbackQuery"):
        data.setdefault("chat_id", os.environ["TELEGRAM_CHAT_ID"])
    url = f"https://api.telegram.org/bot{token}/{metodo}"
    for _ in range(2):
        r = requests.post(url, data=data, timeout=60)
        if r.status_code == 429:
            time.sleep(int(r.json().get("parameters", {}).get("retry_after", 5)) + 1)
            continue
        break
    if not r.ok:
        print(f"[telegram] {metodo}: {r.status_code} {r.text[:200]}")
    return r


def e(s) -> str:
    return html.escape(str(s if s is not None else ""))


def eur(x, dec=0) -> str:
    s = f"{x:,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return s + " €"


def si_no(v, si="sì", no="no") -> str:
    return "non indicato" if v is None else (si if v else no)


def scheda(a: dict) -> str:
    tipo = "Affitto" if a["affitto"] else ("Asta" if a.get("asta") else "Vendita")
    righe = [f"{TESTA[a['livello']]} · {tipo}"]
    titolo = a.get("titolo") or a["testo"][:120]
    righe.append(f"<b>{e(titolo)}</b>")
    righe.append(f"📍 {e(a['zona'])}" + ("" if a["gruppo"] == "Bari" else " (comune vicino)"))
    prezzo = eur(a["prezzo"]) + (" al mese" if a["affitto"] else "")
    if a.get("eur_mq"):
        diff = (a["rapporto"] - 1) * 100
        media = eur(a["media_mq"], 2 if a["affitto"] else 0)
        righe.append(f"💶 <b>{prezzo}</b> · {a['mq']} m² → {eur(a['eur_mq'], 2 if a['affitto'] else 0)}/m² "
                     f"(media zona {media}/m²: <b>{diff:+.0f}%</b>)")
    else:
        righe.append(f"💶 <b>{prezzo}</b> · m² non indicati")
    vani = a.get("locali")
    righe.append("🛏 " + " · ".join([
        f"{vani} vani" if vani else "vani non indicati",
        (f"{a['bagni']} bagn" + ("o" if a["bagni"] == 1 else "i")) if a.get("bagni") else "bagni n.d.",
        f"piano {a['piano']}" if a.get("piano") else "piano n.d."]))
    righe.append(f"🚗 Posto auto/box: {si_no(a.get('box'))} · balcone: {si_no(a.get('balcone'))}")
    for n in a.get("note", []):
        righe.append(e(n) if not n.startswith(("⚠️", "⚖️", "🔑", "🚗", "🏡", "🏗")) else n)
    righe.append(f'🔗 <a href="{html.escape(a["url"], quote=True)}">Apri su {e(a["fonte"])}</a>')
    return "\n".join(righe)


def bottoni(aid: str) -> str:
    row1 = [{"text": AZIONI[k], "callback_data": f"{k}|{aid}"} for k in ("like", "call")]
    row2 = [{"text": AZIONI[k], "callback_data": f"{k}|{aid}"} for k in ("visit", "no")]
    return json.dumps({"inline_keyboard": [row1, row2]})


def voti_testo(voti: dict) -> str:
    if not voti:
        return ""
    per = {}
    for nome, az in voti.items():
        per.setdefault(az, []).append(nome)
    return "\n\n" + " · ".join(f"{AZIONI[k]}: {', '.join(v)}" for k, v in per.items())


def invia(a: dict) -> int | None:
    silent = "true" if (config.SILENZIOSI and a["livello"] != "super") else "false"
    testo = scheda(a)
    if a.get("img") and len(testo) <= 1000:
        r = api("sendPhoto", photo=a["img"], caption=testo, parse_mode="HTML",
                reply_markup=bottoni(a["id"]), disable_notification=silent)
        if r.ok:
            return r.json()["result"]["message_id"]
    r = api("sendMessage", text=testo, parse_mode="HTML", reply_markup=bottoni(a["id"]),
            disable_web_page_preview="false", disable_notification=silent)
    return r.json()["result"]["message_id"] if r.ok else None


def testo(t: str, silent=True):
    return api("sendMessage", text=t, parse_mode="HTML", disable_web_page_preview="true",
               disable_notification="true" if silent else "false")


def gestisci_aggiornamenti(stato: dict):
    """Bottoni premuti e comandi scritti nel gruppo dall'ultimo giro."""
    off = stato.get("tg_offset", 0)
    r = api("getUpdates", offset=off, timeout=0, allowed_updates=json.dumps(["message", "callback_query"]))
    if not r.ok:
        return
    for u in r.json().get("result", []):
        stato["tg_offset"] = u["update_id"] + 1
        if "callback_query" in u:
            _bottone(stato, u["callback_query"])
        elif "message" in u:
            _comando(stato, u["message"])


def _bottone(stato, cq):
    az, _, aid = (cq.get("data") or "").partition("|")
    nome = cq.get("from", {}).get("first_name") or "?"
    a = stato["annunci"].get(aid)
    api("answerCallbackQuery", callback_query_id=cq["id"],
        text=("Segnato: " + AZIONI.get(az, az)) if a else "Annuncio non più in memoria")
    if not a or az not in AZIONI:
        return
    voti = a.setdefault("voti", {})
    if voti.get(nome) == az:
        voti.pop(nome)            # secondo tocco sullo stesso bottone = annulla
    else:
        voti[nome] = az
    msg = cq.get("message") or {}
    if not msg:
        return
    corpo = scheda(a) + voti_testo(voti)
    if "caption" in msg:
        api("editMessageCaption", message_id=msg["message_id"], caption=corpo[:1024], parse_mode="HTML",
            reply_markup=bottoni(aid))
    else:
        api("editMessageText", message_id=msg["message_id"], text=corpo, parse_mode="HTML",
            reply_markup=bottoni(aid), disable_web_page_preview="true")


def _riga(a) -> str:
    p = eur(a["prezzo"]) + ("/mese" if a["affitto"] else "")
    mq = f" · {a['mq']} m²" if a.get("mq") else ""
    v = a.get("voti", {})
    chi = (" · " + ", ".join(f"{AZIONI[x].split()[0]} {n}" for n, x in v.items())) if v else ""
    return f'• <a href="{html.escape(a["url"], quote=True)}">{e(a["zona"])}</a> {p}{mq}{chi}'


def _comando(stato, m):
    t = (m.get("text") or "").split("@")[0].strip().lower()
    ann = [a for a in stato["annunci"].values() if not a.get("scarta")]
    if t == "/preferiti":
        sel = [a for a in ann if any(x in ("like", "call", "visit") for x in a.get("voti", {}).values())]
        testo("<b>❤️ Preferiti</b>\n" + ("\n".join(_riga(a) for a in sel[-40:]) or "Ancora nessuno."))
    elif t == "/migliori":
        sel = sorted((a for a in ann if a.get("rapporto") and "no" not in a.get("voti", {}).values()),
                     key=lambda a: a["rapporto"])[:15]
        testo("<b>🏆 I 15 annunci più convenienti in memoria</b>\n" + ("\n".join(_riga(a) for a in sel) or "Nessuno."))
    elif t in ("/stato", "/start", "/aiuto"):
        testo(f"🏠 <b>Radar case Bari</b>\nUltimo giro: {e(stato.get('ultimo_giro', 'mai'))}\n"
              f"Annunci in memoria: {len(ann)}\n\n"
              "/migliori: i più convenienti\n/preferiti: quelli con ❤️ 📞 🗓\n/stato: questo messaggio\n\n"
              "Sotto ogni annuncio: ❤️ 📞 🗓 ❌. Un secondo tocco annulla.")
