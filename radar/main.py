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
    if card.get("titolo"):
        a["titolo"] = card["titolo"]
    else:
        a["titolo"] = (parti[0] + (", " + parti[1] if len(parti) > 1 and not re.search(r"\d|€|asta", parti[1], re.I) else ""))[:160]
    a["id"] = hashlib.sha1(card["key"].encode()).hexdigest()[:16]
    return valuta(a)


def tocca_ai_siti(s, forza=False) -> bool:
    if forza:
        return True
    ultimo = s.get("ultimo_giro_siti_ts", 0)
    return time.time() - ultimo >= config.SITI_OGNI_ORE * 3600 - 300


def giro(dry=False, file=None, siti_forza=False, niente_siti=False):
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

    # siti delle agenzie: ogni SITI_OGNI_ORE ore (consumano più minuti di GitHub)
    if not file and not niente_siti and config.SITI_ATTIVI and tocca_ai_siti(s, siti_forza):
        from . import siti
        print("Siti delle agenzie:")
        try:
            cards += siti.leggi_siti(set(s["annunci"].keys()) | {v.get("key") for v in s["annunci"].values()},
                                     s.setdefault("siti", {}))
            s["ultimo_giro_siti_ts"] = time.time()
            s["ultimo_giro_siti"] = ora
        except Exception:
            traceback.print_exc()

    nuovi, impronte = [], {v.get("impronta"): k for k, v in s["annunci"].items()}
    nuovi_per_id: dict[str, dict] = {}
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
            # stesso appartamento già visto (in un giro passato o poco fa in questo giro)
            orig = s["annunci"].get(dup) or nuovi_per_id.get(dup)
            if orig is not None:
                altri = orig.setdefault("altri_link", [])
                if a["url"] not in altri and a["url"] != orig.get("url"):
                    altri.append(a["url"])
                continue
        a["primo"] = a["visto"] = ora
        nuovi.append(a)
        nuovi_per_id[a["id"]] = a
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
        # il testo completo serve solo durante il giro: la memoria resta leggera
        for k in ("testo_html", "testo", "testo_zona", "oggetto", "key"):
            a.pop(k, None)
        a.setdefault("primo_ts", int(time.time()))
        s["annunci"][a["id"]] = {**s["annunci"].get(a["id"], {}), **a}
    s["email_lette"].extend(letti)
    s["ultimo_giro"] = ora
    s["ultimo_giro_ts"] = int(time.time())
    s["fonti"] = {"Email (portali)": {"ok": email_avvisi.configurato() or bool(file),
                                      "nota": f"{len(letti)} email nuove in questo giro"}}
    scartati = {}
    for a in nuovi:
        if a.get("scarta"):
            scartati[a["scarta"]] = scartati.get(a["scarta"], 0) + 1
    if not dry and not file:
        salva(s)
        dashboard(s)
    print(f"Giro {ora}: {len(letti)} email nuove, {len(cards)} annunci, {len(nuovi)} nuovi, "
          f"{len(da_mandare)} da segnalare, {inviati} inviati.")
    for k, v in sorted(scartati.items(), key=lambda kv: -kv[1]):
        print(f"   scartati: {v} × {k}")
    return nuovi


DASH = config.ROOT / "docs" / "data"
CAMPI_DASH = ["id", "titolo", "url", "img", "fonte", "zona", "gruppo", "prezzo", "mq", "locali", "bagni",
              "piano", "box", "balcone", "terrazzo", "ascensore", "affitto", "asta", "occupato", "nuova",
              "indipendente", "ristrutturare", "transitorio", "eur_mq", "media_mq", "rapporto", "livello",
              "note", "primo", "primo_ts", "visto", "altri_link", "calo_da"]


def dashboard(s):
    """File letti dalla dashboard (docs/ = GitHub Pages): annunci validi degli ultimi 30 giorni.
    Niente nomi: dei bottoni si salvano solo le azioni."""
    limite = time.time() - 30 * 86400
    out = []
    for a in s["annunci"].values():
        if a.get("scarta") or not a.get("livello") or a.get("primo_ts", time.time()) < limite:
            continue
        # annunci salvati prima della regola dei comuni (17/11/2026): stessa regola anche qui
        if (config.COMUNI_SOLO_VILLE_E_NUOVE and a.get("gruppo") != "Bari"
                and not (a.get("indipendente") or a.get("nuova"))):
            continue
        x = {k: a.get(k) for k in CAMPI_DASH if a.get(k) not in (None, [], "")}
        if "/mailer/" in (x.get("img") or ""):      # immagine generica delle email di Casa.it
            x.pop("img")
        x["voti"] = sorted(a.get("voti", {}).values())
        x["inviato"] = a.get("msg_id") is not None
        out.append(x)
    out.sort(key=lambda x: -(x.get("primo_ts") or 0))
    stato = {"ultimo_giro": s.get("ultimo_giro"), "ultimo_giro_ts": s.get("ultimo_giro_ts"),
             "ultimo_giro_siti": s.get("ultimo_giro_siti"),
             "fonti": {**s.get("fonti", {}),
                       **{k: {"ok": v.get("ok"), "nota": f"{v.get('annunci', 0)} annunci"
                              + (f" · errore: {v['errori'][0][:90]}" if v.get("errori") else "")}
                          for k, v in s.get("siti", {}).items()}},
             "budget": {"vendita": config.MAX_VENDITA, "affitto": config.MAX_AFFITTO}}
    DASH.mkdir(parents=True, exist_ok=True)
    for nome, dati in (("annunci.json", out), ("stato.json", stato)):
        tmp = DASH / (nome + ".tmp")
        tmp.write_text(json.dumps(dati, ensure_ascii=False, separators=(",", ":")), encoding="utf8")
        tmp.replace(DASH / nome)


def cli():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    carica_env()
    ap = argparse.ArgumentParser(description="Radar case Bari")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--ogni", type=float, default=0, help="ripeti ogni N minuti")
    ap.add_argument("--file", help="analizza un'email salvata (.eml)")
    ap.add_argument("--siti", action="store_true", help="leggi i siti delle agenzie anche se non è ora")
    ap.add_argument("--senza-siti", action="store_true", help="solo email")
    a = ap.parse_args()
    while True:
        try:
            giro(dry=a.dry_run, file=a.file, siti_forza=a.siti, niente_siti=a.senza_siti)
        except Exception:
            traceback.print_exc()
        if not a.ogni:
            break
        print(f"Prossimo giro tra {a.ogni:g} minuti.")
        time.sleep(a.ogni * 60)


if __name__ == "__main__":
    cli()
