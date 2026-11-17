"""Zone di Bari e comuni vicini: riconoscimento dal testo e prezzi medi al m²."""
from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from functools import lru_cache

from .config import ROOT

FILE = ROOT / "dati" / "zone.csv"


@dataclass
class Zona:
    nome: str
    gruppo: str
    parole: list[str]
    vendita_mq: float
    affitto_mq: float
    regola: str            # "", "escludi", "solo_con_box", "generica"

    def media(self, affitto: bool) -> float:
        return self.affitto_mq if affitto else self.vendita_mq


# Nomi di strade da togliere prima di cercare la zona: "Via Giovanni Modugno - Poggiofranco"
# è a Poggiofranco, "via San Paolo 17, Noicattaro" è a Noicattaro. Il nome della strada
# finisce alla prima virgola, trattino, barra o parola come "in", "a", "zona".
STRADA = re.compile(
    r"\b(?:via|viale|corso|piazza|piazzetta|strada|largo|vico|contrada|traversa|lungomare)\s+"
    r"[^,|\-–(\n]{2,45}?(?=\s*[,|\-–(\n]|\s+(?:in|a|zona|quartiere)\s|$)")


def _pattern(p: str) -> re.Pattern:
    return re.compile(r"(?<![\w'])" + re.escape(p.lower()) + r"(?![\w])")


@lru_cache(maxsize=1)
def zone() -> list[Zona]:
    with open(FILE, encoding="utf-8") as f:
        out = []
        for r in csv.DictReader(f, delimiter=";"):
            out.append(Zona(r["zona"], r["gruppo"], [w.strip() for w in r["parole"].split("|") if w.strip()],
                            float(r["vendita_mq"] or 0), float(r["affitto_mq"] or 0), (r["regola"] or "").strip()))
        return out


@lru_cache(maxsize=1)
def _compiled():
    return [(z, [_pattern(w) for w in z.parole]) for z in zone()]


def trova(testo: str) -> Zona | None:
    """La zona citata nel testo. Le zone escluse vincono su tutto, poi l'ordine del CSV.
    Se c'è solo "Bari" senza quartiere: la zona generica (media di Bari città)."""
    t = STRADA.sub(" ", (testo or "").lower())
    hits = [z for z, pats in _compiled() if any(p.search(t) for p in pats)]
    generiche = [z for z in hits if z.regola == "generica"]
    hits = [z for z in hits if z.regola != "generica"]
    if not hits:
        return generiche[0] if generiche else None
    for z in hits:
        if z.regola == "escludi":
            return z
    # un comune vicino citato (non come nome di strada) vince sul quartiere
    comuni = [z for z in hits if z.gruppo != "Bari"]
    return comuni[0] if comuni else hits[0]
