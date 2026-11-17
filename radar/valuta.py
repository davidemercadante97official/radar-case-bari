"""Decide se un annuncio conviene: prezzo al m² contro la media della zona."""
from __future__ import annotations

from . import config
from .zone import trova

LIVELLI = ["super", "buono", "media", "caro"]


def valuta(a: dict) -> dict:
    """a = annuncio con 'testo' + campi di annunci.leggi(). Aggiunge zona, livello, motivi.
    'scarta' = motivo per cui l'annuncio non interessa (None se interessa)."""
    z = trova(a.get("testo", ""))
    a["zona"] = z.nome if z else None
    a["gruppo"] = z.gruppo if z else None
    p, mq, aff = a.get("prezzo"), a.get("mq"), a.get("affitto")
    if not z:
        return {**a, "scarta": "zona non riconosciuta o non nella lista"}
    if z.regola == "escludi":
        return {**a, "scarta": f"zona esclusa ({z.nome})"}
    if z.regola == "solo_con_box" and not a.get("box"):
        return {**a, "scarta": f"{z.nome}: interessa solo con box o posto auto"}
    if (config.COMUNI_SOLO_VILLE_E_NUOVE and z.gruppo != "Bari"
            and not (a.get("indipendente") or a.get("nuova"))):
        return {**a, "scarta": "comune vicino: solo ville/villette o nuova costruzione"}
    if a.get("non_casa"):
        return {**a, "scarta": "non è un'abitazione intera (box, negozio, stanza, quota...)"}
    if a.get("asta") and a.get("non_visitabile"):
        return {**a, "scarta": "asta non visitabile"}
    if not p:
        return {**a, "scarta": "prezzo mancante"}
    if aff and p > config.MAX_AFFITTO:
        return {**a, "scarta": "affitto sopra il budget"}
    if not aff and p > config.MAX_VENDITA:
        return {**a, "scarta": "vendita sopra il budget"}
    if mq and mq < config.MQ_MIN:
        return {**a, "scarta": f"solo {mq} m²"}

    a["scarta"] = None
    a["media_mq"] = z.media(aff)
    note = []
    if z.gruppo != "Bari" and a.get("indipendente"):
        note.append("🏡 Villa / casa indipendente")
    if a.get("nuova") and not aff:
        a["media_mq"] = round(a["media_mq"] * config.NUOVO_COEFF)
        note.append("🏗 Nuova costruzione: confrontata con la media della zona +25% (il nuovo costa di più)")
    if not mq:
        a.update(livello="media", eur_mq=None, rapporto=None)
        note.append("Metri quadri non indicati: valuta tu il prezzo")
        a["note"] = note
        return a
    costo = p
    if a.get("ristrutturare") and not aff:
        lavori = config.LAVORI_MQ * mq
        costo = p + lavori
        note.append(f"Da ristrutturare: confrontato con {round(lavori, -3):,.0f} € di lavori stimati".replace(",", "."))
    a["eur_mq"] = round(p / mq, 2 if aff else 0)
    r = (costo / mq) / a["media_mq"]
    a["rapporto"] = round(r, 3)
    if r <= config.SUPER:
        liv = "super"
    elif r <= config.BUONO:
        liv = "buono"
    elif r <= config.CARO:
        liv = "media"
    else:
        liv = "caro"
    sospetto = config.SOSPETTO_AFFITTO if aff else config.SOSPETTO_VENDITA
    if r < sospetto and not a.get("asta"):
        note.append("⚠️ Prezzo troppo basso per la zona: controlla che non sia una stanza, "
                    "una nuda proprietà, una quota o un errore")
    if a.get("asta"):
        note.append("⚖️ ASTA: il prezzo è la base d'asta; si può offrire fino al 25% in meno "
                    "(offerta minima). Leggi perizia e avviso di vendita")
        if a.get("occupato"):
            note.append("🔑 Occupato: tempi più lunghi per la liberazione (ordine del giudice)")
    a["livello"] = liv
    a["note"] = note
    return a


def da_notificare(a: dict) -> bool:
    if a.get("scarta"):
        return False
    if a["livello"] in config.NOTIFICA:
        return True
    # ville e nuove costruzioni nei comuni: arrivano se il prezzo non è caro
    if config.COMUNI_SOLO_VILLE_E_NUOVE and a.get("gruppo") != "Bari" and a["livello"] == "media":
        return True
    return config.NOTIFICA_MEDIA_CON_BOX and a["livello"] == "media" and bool(a.get("box"))
