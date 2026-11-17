"""Un giro del radar case: legge gli avvisi email, valuta, scrive nel gruppo Telegram.

Uso:
    python -m radar.main                  # un giro
    python -m radar.main --ogni 15        # un giro ogni 15 minuti
    python -m radar.main --dry-run        # niente Telegram: stampa a video
    python -m radar.main --file email.eml # prova su un'email salvata
"""
from __future__ import annotations

import argparse
import email
import hashlib
import json
import os
import re
import sys
import time
import traceback
from datetime import datetime, timezone

from . import config, email_avvisi, telegram
from .annunci import leggi
from .valuta import LIVELLI, da_notificare, valuta

STATO = config.ROOT / "data" / "stato.json"


def adesso():
    """Ora italiana anche sui server di GitHub (che sono in UTC)."""
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("Europe/Rome"))
    except Exception:
        return datetime.now(timezone.utc).astimezone()


def carica_env():
    f = config.ROOT / ".env"
    if f.exists():
        for line in f.read_text(encoding="utf-8-sig").splitlines():
            k, sep, v = line.partition("=")
            if sep and not line.lstrip().startswith("#") and v.strip() and not os.getenv(k.strip()):
                os.environ[k.strip()] = v.strip().strip('"').strip("'")


def carica():
    try:
        s = json.loads(STATO.read_text(encoding="utf8"))
    except (FileNotFoundError, json.JSONDecodeError):
        s = {}
    s.setdefault("annunci", {})
    s.setdefault("email_lette", [])
    return s


def salva(s):
    STATO.parent.mkdir(parents=True, exist_ok=True)
    if len(s["annunci"]) > config.MAX_SALVATI:
        tieni = sorted(s["annunci"].items(), key=lambda kv: kv[1].get("visto", ""))[-config.MAX_SALVATI:]
        s["annunci"] = dict(tieni)
    s["email_lette"] = s["email_lette"][-3000:]
    tmp = STATO.with_suffix(".tmp")
    tmp.write_text(json.dumps(s, ensure_ascii=False, indent=1), encoding="utf8")
    tmp.replace(STATO)


def impronta(a) -> str:
    """Stesso appartamento pubblicato da più portali/agenzie: stessa zona, prezzo e m²."""
    base = f"{a.get('zona')}|{int(a.get('prezzo') or 0)}|{a.get('mq')}|{a.get('affitto')}"
    return hashlib.sha1(base.encode()).hexdigest()[:12]


def prepara(card: dict) -> dict:
    a = {**leggi(card["testo"]), **card}
    parti = (card.get("testo") or "").split(" | ")
    # Casa.it: "Appartamento in vendita in Via X | Libertà, Bari (BA)": titolo + zona
    a["titolo"] = (parti[0] + (", " + parti[1] if len(parti) > 1 and not re.search(r"\d|€|asta", parti[1], re.I) else ""))[:160]
    a["id"] = hashlib.sha1(card["key"].encode()).hexdigest()[:16]
    return valuta(a)


def giro(dry=False, file=None):
    s = carica()
    ora = adesso().strftime("%d/%m %H:%M")
    if telegram.attivo() and not dry:
        try:
            telegram.gestisci_aggiornamenti(s)
        except Exception:
            traceback.print_exc()

    if file:
        with open(file, "rb") as f:
            cards = email_avvisi.annunci_da_email(email.message_from_bytes(f.read()))
        letti = []
    elif email_avvisi.configurato():
        cards, letti = email_avvisi.leggi_casella(set(s["email_lette"]))
    else:
        print("Email non configurata (EMAIL_ADDRESS / EMAIL_APP_PASSWORD nel file .env).")
        cards, letti = [], []

    nuovi, impronte = [], {v.get("impronta"): k for k, v in s["annunci"].items()}
    for c in cards:
        a = prepara(c)
        old = s["annunci"].get(a["id"])
        a["impronta"] = impronta(a)
        dup = impronte.get(a["impronta"])
        if old:
            old["visto"] = ora
            # riavvisa solo se il prezzo è sceso
            if a.get("prezzo") and old.get("prezzo") and a["prezzo"] < old["prezzo"] and da_notificare(a):
                a["calo_da"] = old["prezzo"]
                a["note"] = [f"📉 Prezzo sceso da {telegram.eur(old['prezzo'])}"] + a.get("note", [])
                a["voti"] = old.get("voti", {})
                nuovi.append(a)
            continue
        if dup and dup != a["id"] and a.get("mq"):
            altri = s["annunci"][dup].setdefault("altri_link", [])
            if a["url"] not in altri and a["url"] != s["annunci"][dup].get("url"):
                altri.append(a["url"])
            continue
        a["primo"] = a["visto"] = ora
        nuovi.append(a)
        if a.get("mq"):
            impronte[a["impronta"]] = a["id"]

    da_mandare = sorted((a for a in nuovi if da_notificare(a)),
                        key=lambda a: (LIVELLI.index(a["livello"]), a.get("rapporto") or 9))
    inviati = 0
    for a in da_mandare[: config.MAX_MESSAGGI_PER_GIRO]:
        if dry or not telegram.attivo():
            print("\n" + "-" * 60 + "\n" + telegram.scheda(a))
        else:
            a["msg_id"] = telegram.invia(a)
            inviati += bool(a["msg_id"])
            time.sleep(1.1)
    extra = len(da_mandare) - config.MAX_MESSAGGI_PER_GIRO
    if extra > 0 and telegram.attivo() and not dry:
        telegram.testo(f"…e altri <b>{extra}</b> annunci interessanti: scrivi /migliori.")

    for a in nuovi:
        a.pop("testo_html", None)
        s["annunci"][a["id"]] = {**s["annunci"].get(a["id"], {}), **a}
    s["email_lette"].extend(letti)
    s["ultimo_giro"] = ora
    scartati = {}
    for a in nuovi:
        if a.get("scarta"):
            scartati[a["scarta"]] = scartati.get(a["scarta"], 0) + 1
    if not dry and not file:
        salva(s)
    print(f"Giro {ora}: {len(letti)} email nuove, {len(cards)} annunci, {len(nuovi)} nuovi, "
          f"{len(da_mandare)} da segnalare, {inviati} inviati.")
    for k, v in sorted(scartati.items(), key=lambda kv: -kv[1]):
        print(f"   scartati: {v} × {k}")
    return nuovi


def cli():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    carica_env()
    ap = argparse.ArgumentParser(description="Radar case Bari")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--ogni", type=float, default=0, help="ripeti ogni N minuti")
    ap.add_argument("--file", help="analizza un'email salvata (.eml)")
    a = ap.parse_args()
    while True:
        try:
            giro(dry=a.dry_run, file=a.file)
        except Exception:
            traceback.print_exc()
        if not a.ogni:
            break
        print(f"Prossimo giro tra {a.ogni:g} minuti.")
        time.sleep(a.ogni * 60)


if __name__ == "__main__":
    cli()
