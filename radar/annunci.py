"""Dal testo di un annuncio (titolo, scheda, riga dell'email) ai dati: prezzo, m², vani, piano..."""
from __future__ import annotations

import re

from . import config

PREZZO = re.compile(r"(?:€\s*([\d.]{2,}(?:,\d{1,2})?)|([\d.]{2,}(?:,\d{1,2})?)\s*(?:€|euro\b))", re.I)
MQ = re.compile(r"(\d{2,4})(?:[.,]\d+)?\s*(?:m²|m2|mq|metri quadr|sqm)", re.I)
LOCALI = re.compile(r"(\d)\s*\+?\s*\|?\s*(?:locali|locale|vani|vano|loc\.)", re.I)
LOCALI_DOPO = re.compile(r"\b(?:locali|vani)\s*\|?\s*:?\s*(\d)\b", re.I)
BAGNI_DOPO = re.compile(r"\bbagni\s*\|?\s*:?\s*(\d)\b", re.I)
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
# Stanze, posti letto e case per studenti: "STANZA SINGOLA IN APPARTAMENTO CONDIVISO",
# "rivolto a lavoratori o studenti", "posto letto in doppia", "solo studentesse"...
# ("camera da letto" non conta: è una normale stanza della casa)
STUDENTI = re.compile(
    r"\bstanz[ae]\s+(?:singol|doppi|matrimonial|in affitto|in appartamento|in condivisione|arredat|libera)|"
    r"\bcamer[ae]\s+(?:singol|doppi)[ae]?\b(?!\s+da letto)|"
    r"\bposti? letto\b|appartamento condiviso|\bin condivisione\b|\bcondivis[oa] con\b|"
    r"\bcoinquilin|\baffittasi\s+stanz|\bstudent[ie]|\bstudentess|\buniversitar[io]|\bfuori\s?sede\b|"
    r"\buso foresteria\b|\bdomicilio universitario", re.I)   # "vicino al campus" non conta
TRANSITORIO = re.compile(r"\btransitori[oa]\b|\bnatura transitoria|\bfino al? \d{1,2}/\d{2,4}\b|"
                         r"\bmax(?:imo)? \d{1,2} mesi\b|\b(?:6|12|18) mesi\b|\bstagional|\bbreve periodo\b", re.I)
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
    t = re.sub(r"(\d)\s*\|\s*(m²|mq|m2)\b", r"\1 \2", t)          # Gabetti: "76 | m²"
    t = re.sub(r"(\d+)\s*\|\s*m\s*\|\s*2\b", r"\1 m²", t)        # Vistocasa: "90 | m | 2"
    t = re.sub(r"(\d+)\s*Mq\b", r"\1 mq", t)                        # Tecnocasa: "71 Mq"
    low = t.lower()
    d: dict = {"prezzo": prezzo(t)}
    m = MQ.search(t)
    d["mq"] = int(m.group(1)) if m else None
    m = LOCALI.search(t) or LOCALI_DOPO.search(t)
    d["locali"] = int(m.group(1)) if m else next((n for k, n in NOMI_LOCALI.items() if k in low), None)
    m = CAMERE.search(t)
    d["camere"] = int(m.group(1)) if m else None
    m = BAGNI.search(t) or BAGNI_DOPO.search(t)
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
    # la tipologia sta nelle prime righe (titolo): "Negozio in via...", "Stanza singola..."
    titolo = " | ".join((testo or "").split(" | ")[:6])
    # prima riga, oppure una riga-titolo successiva ("Negozio in via dei Mille, Bari");
    # una riga corta come "posto auto" è una dotazione, non la tipologia
    righe = titolo.split(" | ")
    d["non_casa"] = bool(NON_CASA.search(righe[0])) or any(
        NON_CASA.search(x) and len(x) > 15 for x in righe[1:]) or bool(re.search(r"nuda propriet|quota di|% di propriet|posto letto", low))
    d["studenti"] = bool(STUDENTI.search(t))
    d["transitorio"] = bool(TRANSITORIO.search(t))
    d["indipendente"] = bool(INDIPENDENTE.search(t))
    d["nuova"] = bool(NUOVA.search(t))
    p = d["prezzo"]
    d["affitto"] = bool(p and p < config.SOGLIA_AFFITTO) or (bool(AFFITTO_PAROLE.search(t)) and bool(p and p < 10_000))
    return d
