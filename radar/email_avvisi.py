"""Legge gli avvisi email delle ricerche salvate (Immobiliare, Idealista, Casa.it, Subito, aste)
e ne estrae gli annunci. La casella viene solo letta: nessun messaggio viene spostato o segnato."""
from __future__ import annotations

import email
import hashlib
import html
import imaplib
import os
import re
from datetime import datetime, timedelta
from email.header import decode_header, make_header
from html.parser import HTMLParser
from urllib.parse import unquote

from . import config

# id dell'annuncio dentro l'URL (anche dentro un link di tracciamento)
ID_URL = [
    ("immobiliare", re.compile(r"immobiliare\.it/(?:\w+/)?annunci/(\d{6,})")),
    ("idealista", re.compile(r"idealista\.(?:it|com)/(?:\w+/)?immobile/(\d{6,})")),
    ("casa.it", re.compile(r"casa\.it/immobili/(\d{6,})")),
    ("subito", re.compile(r"subito\.it/[\w/-]+?-(\d{6,})\.htm")),
    ("wikicasa", re.compile(r"wikicasa\.it/[\w/-]+?/(\d{5,})")),
    ("astegiudiziarie", re.compile(r"astegiudiziarie\.it/[\w/-]*?(\d{5,})")),
    ("pvp", re.compile(r"pvp\.giustizia\.it/.*?idInserzione=(\d+)")),
]
FONTE = {"immobiliare": "Immobiliare.it", "idealista": "Idealista", "casa.it": "Casa.it",
         "subito": "Subito", "wikicasa": "Wikicasa", "astegiudiziarie": "Aste Giudiziarie",
         "pvp": "Portale Vendite Pubbliche"}
SALTA_LINK = re.compile(r"unsubscribe|disiscriv|cancella|preferenz|privacy|app\.|play\.google|"
                        r"apps\.apple|facebook|instagram|twitter|linkedin|youtube|mailto:", re.I)
FINE_SCHEDA = re.compile(r"Vedi \d+ foto|Scarica l'app|Questa email ti è stata|Non vuoi più ricevere|"
                         r"Modifica (?:la )?ricerca|Gestisci (?:i tuoi )?avvisi", re.I)
BLOCCHI = {"p", "div", "tr", "td", "li", "br", "table", "h1", "h2", "h3", "h4", "span"}


def id_da_url(url: str) -> tuple[str, str] | None:
    u = url
    for _ in range(3):           # i link di tracciamento contengono l'URL vero, codificato
        for fonte, rx in ID_URL:
            m = rx.search(u)
            if m:
                return fonte, m.group(1)
        u = unquote(u)
    return None


class _Cards(HTMLParser):
    """Divide l'email in schede: il testo dopo un link a un annuncio appartiene a
    quell'annuncio finché non compare il link di un annuncio diverso."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.cards: list[dict] = []
        self.cur: dict | None = None
        self.prima = ""          # testo prima del primo link (a volte c'è il prezzo)
        self.skip = 0
        self.img = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ("style", "script", "head"):
            self.skip += 1
        if tag == "img" and a.get("src", "").startswith("http") and not self.img:
            w = a.get("width", "")
            if not w.isdigit() or int(w) >= 100:
                if self.cur and not self.cur["img"]:
                    self.cur["img"] = a["src"]     # foto dentro il link dell'annuncio
                else:
                    self.img = a["src"]            # foto prima del link: va alla scheda dopo
        if tag == "a" and a.get("href"):
            href = html.unescape(a["href"])
            if SALTA_LINK.search(href):
                return
            found = id_da_url(href)
            key = f"{found[0]}:{found[1]}" if found else None
            if key and (not self.cur or self.cur["key"] != key):
                same = next((c for c in self.cards if c["key"] == key), None)
                if same:
                    self.cur = same
                else:
                    self.cur = {"key": key, "fonte": FONTE[found[0]], "url": href, "testo": "",
                                "img": self.img}
                    self.cards.append(self.cur)
            self.img = None
        if tag in BLOCCHI and self.cur:
            self.cur["testo"] += " | "

    def handle_endtag(self, tag):
        if tag in ("style", "script", "head") and self.skip:
            self.skip -= 1

    def handle_data(self, data):
        if self.skip or not data.strip():
            return
        if self.cur:
            self.cur["testo"] += " " + data.strip()
        else:
            self.prima += " " + data.strip()


def annunci_da_html(body: str) -> list[dict]:
    p = _Cards()
    p.feed(body)
    out = []
    for c in p.cards:
        t = re.sub(r"(\s*\|\s*)+", " | ", c["testo"]).strip(" |")
        t = FINE_SCHEDA.split(t)[0].strip(" |")   # via il piè di pagina dell'email
        if len(t) > 900:          # l'ultima scheda si porta dietro il piè di pagina
            t = t[:900]
        c["testo"] = t
        out.append(c)
    return out


def annunci_da_testo(body: str) -> list[dict]:
    """Email solo testo: ogni URL di annuncio con le righe che lo precedono."""
    out, buf = [], []
    for line in body.splitlines():
        for url in re.findall(r"https?://\S+", line):
            found = id_da_url(url)
            if found:
                out.append({"key": f"{found[0]}:{found[1]}", "fonte": FONTE[found[0]], "url": url,
                            "testo": " | ".join(buf[-6:]), "img": None})
                buf = []
                line = line.replace(url, "")
        if line.strip():
            buf.append(line.strip())
    return out


def _dec(v) -> str:
    try:
        return str(make_header(decode_header(v or "")))
    except Exception:
        return v or ""


def _corpi(msg) -> tuple[str, str]:
    h, t = "", ""
    for part in msg.walk():
        ct = part.get_content_type()
        if ct not in ("text/html", "text/plain") or part.get_filename():
            continue
        raw = part.get_payload(decode=True) or b""
        txt = raw.decode(part.get_content_charset() or "utf-8", errors="replace")
        if ct == "text/html":
            h += txt
        else:
            t += txt
    return h, t


def annunci_da_email(msg) -> list[dict]:
    h, t = _corpi(msg)
    cards = annunci_da_html(h) if h else []
    if not cards and t:
        cards = annunci_da_testo(t)
    subj = _dec(msg.get("Subject"))
    for c in cards:
        c["oggetto"] = subj
    return cards


def configurato() -> bool:
    return bool(os.getenv("EMAIL_ADDRESS") and os.getenv("EMAIL_APP_PASSWORD"))


def leggi_casella(visti: set[str]) -> tuple[list[dict], list[str]]:
    """Ritorna (annunci, id dei messaggi letti). Salta i messaggi già letti nei giri prima."""
    server = os.getenv("EMAIL_IMAP_SERVER") or "imap.gmail.com"
    M = imaplib.IMAP4_SSL(server)
    M.login(os.environ["EMAIL_ADDRESS"], os.environ["EMAIL_APP_PASSWORD"].replace(" ", ""))
    try:
        annunci, letti = [], []
        for cartella in config.CARTELLE_EMAIL:
            if M.select(f'"{cartella}"', readonly=True)[0] != "OK":
                continue          # etichetta non ancora creata
            _leggi_cartella(M, visti, annunci, letti)
        return annunci, letti
    finally:
        try:
            M.logout()
        except Exception:
            pass


def _leggi_cartella(M, visti, annunci, letti):
    since = (datetime.now() - timedelta(days=config.GIORNI_EMAIL)).strftime("%d-%b-%Y")
    uids = set()
    for dom in config.MITTENTI:
        typ, data = M.uid("search", None, "SINCE", since, "FROM", f'"{dom}"')
        if typ == "OK" and data and data[0]:
            uids.update(data[0].split())
    for uid in sorted(uids, key=int):
        typ, data = M.uid("fetch", uid, "(BODY.PEEK[])")   # PEEK: non segna come letto
        if typ != "OK" or not data or not data[0]:
            continue
        msg = email.message_from_bytes(data[0][1])
        mid = (msg.get("Message-ID") or "").strip() or hashlib.sha1(data[0][1][:4000]).hexdigest()
        if mid in visti:
            continue
        letti.append(mid)
        annunci.extend(annunci_da_email(msg))
