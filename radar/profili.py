"""Profili del radar: chi riceve cosa.

Le fonti (email e siti) si leggono una volta sola; ogni profilo valuta gli annunci con le
sue regole, ha il suo bot, il suo gruppo, la sua memoria e la sua dashboard.
Un profilo senza token o senza id del gruppo viene saltato (tranne "noi", il principale).
"""
from __future__ import annotations

import os
from contextlib import contextmanager
from dataclasses import dataclass

from . import config


@dataclass
class Profilo:
    nome: str
    titolo: str
    token_env: str            # variabile con il token del bot
    chat_env: str             # variabile con l'id del gruppo
    cartella: str             # "" = data/ e docs/ (profilo principale), altrimenti una sottocartella
    max_vendita: int
    max_affitto: int
    affitti: bool             # vuole anche gli affitti?
    aste: bool                # vuole anche le aste?

    @property
    def stato(self):
        return config.ROOT / "data" / self.cartella / "stato.json" if self.cartella else config.ROOT / "data" / "stato.json"

    @property
    def dash(self):
        return config.ROOT / "docs" / self.cartella / "data" if self.cartella else config.ROOT / "docs" / "data"

    @property
    def url(self):
        return config.DASHBOARD + (self.cartella + "/" if self.cartella else "")

    def attivo(self) -> bool:
        return self.cartella == "" or bool(os.getenv(self.token_env) and os.getenv(self.chat_env))


PROFILI = [
    # Davide e la sua fidanzata
    Profilo("noi", "Radar Case Bari", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "",
            max_vendita=config.MAX_VENDITA, max_affitto=config.MAX_AFFITTO, affitti=True, aste=True),
    # due amici: stesse zone e regole, solo vendita (niente affitti né aste), fino a 300.000 €
    Profilo("amici", "Radar Case Bari · Amici", "TELEGRAM_BOT_TOKEN_2", "TELEGRAM_CHAT_ID_2", "amici",
            max_vendita=300_000, max_affitto=0, affitti=False, aste=False),
]


@contextmanager
def usa(p: Profilo):
    """Durante il blocco: bot, gruppo, budget e regole del profilo p."""
    salva_env = {k: os.environ.get(k) for k in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID")}
    salva_cfg = {k: getattr(config, k) for k in ("MAX_VENDITA", "MAX_AFFITTO", "AFFITTI_OK", "ASTE_OK", "DASHBOARD")}
    try:
        for k, src in (("TELEGRAM_BOT_TOKEN", p.token_env), ("TELEGRAM_CHAT_ID", p.chat_env)):
            v = os.environ.get(src) if src != k else salva_env[k]
            if v:
                os.environ[k] = v
            else:
                os.environ.pop(k, None)
        config.MAX_VENDITA, config.MAX_AFFITTO = p.max_vendita, p.max_affitto
        config.AFFITTI_OK, config.ASTE_OK = p.affitti, p.aste
        config.DASHBOARD = p.url
        yield p
    finally:
        for k, v in salva_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        for k, v in salva_cfg.items():
            setattr(config, k, v)
