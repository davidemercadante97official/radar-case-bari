"""Dal testo di un annuncio (titolo, scheda, riga dell'email) ai dati: prezzo, m², vani, piano..."""
from __future__ import annotations

import re

from . import config

PREZZO = re.compile(r"(?:€\s*([\d.]{2,}(?:,\d{1,2})?)|([\d.]{2,}(?:,\d{1,2})?)\s*(?:€|euro\b))", re.I)
MQ = re.compile(r"(\d{2,4})(?:[.,]\d+)?\s*(?:m²|m2|mq|metri quadr|sqm)", re.I)
LOCALI = re.compile(r"(\d)\s*\+?\s*(?:locali|vani|loc\.)", re.I)
NOMI_LOCALI = {"monolocale": 1, "bilocale": 2, "trilocale": 3, "quadrilocale": 4, "pentalocale": 5}
CAMERE = re.compile(r"(\d)\s*(?:camere|camera da letto|stanze da letto)", re.I)
BAGNI = re.compile(r"(\d)\s*bagn", re.I)
PIANO = re.compile(r"(piano terra|piano rialzato|seminterrato|ultimo piano|attico|"
                   r"(\d{1,2})\s*°\s*piano|piano\s*(\d{1,2})\s*°?|(\d{1,2})°)", re.I)
BOX = re.compile(r"\b(box|garage|posto auto|posti auto|posto macchina|autorimessa|parcheggio privato)\b", re.I)
NO_BOX = re.compile(r"\b(senza|no|privo di)\s+(box|garage|posto auto)", re.I)
BALCONE = re.compile(r"\bbalcon", re.I)
TERRAZZO = re.compile(r"\bterrazz", re.I)
ASCENSORE = re.compile(r"\bascensore\b", re.I)
NO_ASCENSORE = re.compile(r"\b(no|senza)\s+ascensore\b", re.I)
RISTRUTTURARE = re.compile(r"da ristrutturare|da rimodernare|da ammodernare|da riattare|rudere", re.I)
ASTA = re.compile(r"\basta\b|\baste\b|giudiziari|offerta minima|prezzo base|tribunale|esecuzion", re.I)
OCCUPATO = re.compile(r"\boccupat[oa]\b|con inquilin|locat[oa] a terzi", re.I)
NON_VISITABILE = re.compile(r"non visitabile|visita non (?:consentita|possibile)|non è possibile visitare", re.I)
# tipologie che non sono una casa: valgono solo all'inizio del titolo
NON_CASA = re.compile(r"^\W*(box|garage|posto auto|magazzino|negozio|locale commerciale|ufficio|capannone|"
                      r"terreno|cantina|laboratorio|deposito|stanza|camera singola|camera doppia|"
                      r"posto letto)\b", re.I)
INDIPENDENTE = re.compile(r"\b(villa|villetta|villino|villette|casa indipendente|soluzione indipendente|"
                          r"terratetto|terra-tetto|casa singola|casa unifamiliare|bifamiliare|a schiera)\b", re.I)
NUOVA = re.compile(r"nuova costruzione|in costruzione|nuovo\s*/\s*in costruzione|di nuova realizzazione|"
                   r"nuovo cantiere|appena costruit|consegna (?:prevista|202\d)", re.I)
AFFITTO_PAROLE = re.compile(r"\baffitt|\blocazione|/mese|al mese|mensil", re.I)


def numero(txt: str) -> float | None:
    txt = txt.replace(".", "").replace(" ", "")
    if "," in txt:
        txt = txt.replace(",", ".")
    try:
        return float(txt)
    except ValueError:
        return None


def prezzo(testo: str) -> float | None:
    for m in PREZZO.finditer(testo):
        v = numero(m.group(1) or m.group(2))
        if v and v >= 100:
            return v
    return None


def leggi(testo: str) -> dict:
    """Estrae tutto quello che riesce. I campi non trovati restano None."""
    t = re.sub(r"\s+", " ", testo or "")
    t = re.sub(r"€\s*\|\s*", "€ ", t)          # Casa.it: "€ | 149.000"
    low = t.lower()
    d: dict = {"prezzo": prezzo(t)}
    m = MQ.search(t)
    d["mq"] = int(m.group(1)) if m else None
    m = LOCALI.search(t)
    d["locali"] = int(m.group(1)) if m else next((n for k, n in NOMI_LOCALI.items() if k in low), None)
    m = CAMERE.search(t)
    d["camere"] = int(m.group(1)) if m else None
    m = BAGNI.search(t)
    d["bagni"] = int(m.group(1)) if m else None
    m = PIANO.search(t)
    if m:
        n = m.group(2) or m.group(3) or m.group(4)
        d["piano"] = f"{n}°" if n else m.group(1).lower()
    else:
        d["piano"] = None
    d["box"] = False if NO_BOX.search(t) else (True if BOX.search(t) else None)
    d["balcone"] = True if BALCONE.search(t) else None
    d["terrazzo"] = True if TERRAZZO.search(t) else None
    d["ascensore"] = False if NO_ASCENSORE.search(t) else (True if ASCENSORE.search(t) else None)
    d["ristrutturare"] = bool(RISTRUTTURARE.search(t))
    d["asta"] = bool(ASTA.search(t))
    d["occupato"] = bool(OCCUPATO.search(t))
    d["non_visitabile"] = bool(NON_VISITABILE.search(t))
    # la tipologia sta nel titolo (prima riga): "Box auto in vendita..." non "...con box auto"
    titolo = (testo or "").split(" | ")[0]
    d["non_casa"] = bool(NON_CASA.search(titolo)) or bool(re.search(r"nuda propriet|quota di|% di propriet|posto letto", low))
    d["indipendente"] = bool(INDIPENDENTE.search(t))
    d["nuova"] = bool(NUOVA.search(t))
    p = d["prezzo"]
    d["affitto"] = bool(p and p < config.SOGLIA_AFFITTO) or (bool(AFFITTO_PAROLE.search(t)) and bool(p and p < 10_000))
    return d
