"""Lettura diretta dei siti delle agenzie (quelli che non bloccano i programmi).

Per ogni sito: le pagine con l'elenco degli annunci e lo schema dei link alle schede.
Il lettore trova i link agli annunci, prende il riquadro che contiene solo quell'annuncio
e ne usa il testo (prezzo, m², vani...). Se nell'elenco manca il prezzo, apre la scheda
dell'annuncio (al massimo MAX_DETTAGLI per sito a ogni giro, solo annunci nuovi).
"""
from __future__ import annotations

import hashlib
import json
import random
import re
import time
from urllib.parse import urljoin, urlparse

import requests

from .annunci import PREZZO, prezzo as _prezzo
from .config import SOGLIA_AFFITTO
from .zone import trova

try:
    from bs4 import BeautifulSoup
except ImportError:          # senza bs4 i siti vengono saltati (le email funzionano lo stesso)
    BeautifulSoup = None

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0 Safari/537.36")
MAX_DETTAGLI = 30
SERVIZIO = re.compile(r"^(previous slide|next slide|condividi|novit|evidenza|in evidenza|scegli|video|"
                      r"\d+ / \d+|vendita|affitto|locazione|in locazione|dettagli)$", re.I)
TIPI = re.compile(r"appartament|villa|villett|attico|locali|vani|casa|bilocale|trilocale|quadrilocale|"
                  r"monolocale|pentalocale|loft|mansarda|terratetto|indipendente", re.I)

# nome, pagine elenco, schema dei link agli annunci, [opzioni]
SITI = [
    {"nome": "Tecnocasa", "tipo": "tecnocasa",
     "pagine": ["https://www.tecnocasa.it/annunci/immobili/puglia/bari/bari.html",
                "https://www.tecnocasa.it/annunci/immobili/puglia/bari/bari.html/pag-2",
                "https://www.tecnocasa.it/annunci/immobili/puglia/bari/bari.html/pag-3"]},
    {"nome": "RE/MAX",
     "pagine": ["https://www.remax.it/vendita-case/bari", "https://www.remax.it/affitto-case/bari"],
     "link": r"\.remax\.it/(?:vendita|affitto)-[\w-]+/bari/[\w-]+-\d+-\d+"},
    {"nome": "Tempocasa",
     "pagine": ["https://tempocasa.it/it/vendita/bari", "https://tempocasa.it/it/affitto/bari"],
     "link": r"tempocasa\.it/it/(?:vendita|affitto)/bari/[\w-]+/[\w-]+/[\w-]+"},
    {"nome": "Toscano",
     "pagine": ["https://www.toscano.it/vendita/immobili-residenziali/comune-bari",
                "https://www.toscano.it/affitto/immobili-residenziali/comune-bari"],
     "link": r"toscano\.it/comune-[\w-]+/\d+-[\w-]+"},
    {"nome": "Vistocasa",
     "pagine": ["https://www.vistocasa.com/it/ricerca.aspx?comune=bari"],
     "link": r"vistocasa\.com/it/immobile\.aspx\?ArticoliId=\d+"},
    {"nome": "Professionecasa",
     "pagine": ["https://www.professionecasa.it/vendita/case/bari", "https://www.professionecasa.it/affitto/case/bari"],
     "link": r"professionecasa\.it/[\w-]+/(?:vendita|affitto)/[\w-]+/\d+"},
    {"nome": "Studio Vitulli",
     "pagine": ["https://www.studiovitulli.it/status/vendita/", "https://www.studiovitulli.it/"],
     "link": r"studiovitulli\.it/immobile/[\w-]+"},
    {"nome": "Gabetti",
     "pagine": ["https://www.gabetti.it/vendita/bari", "https://www.gabetti.it/affitto/bari"],
     "link": r"gabetti\.it/(?:vendita|affitto)/bari/[\w-]+/\d+"},
    {"nome": "Rafaschieri",
     "pagine": ["https://www.rafaschierimmobiliare.it/immobili.php?c=ven",
                "https://www.rafaschierimmobiliare.it/immobili.php?c=aff"],
     "link": r"rafaschierimmobiliare\.it/dettagli\.php\?a=\d+", "dettaglio": True},
    {"nome": "Altomare",
     "pagine": ["https://www.altomareimmobiliare.it/immobili"],
     "link": r"altomareimmobiliare\.it/immobili/[\w-]{8,}"},
    {"nome": "Executive",
     "pagine": ["https://www.executiveimmobiliare.it/"],      # le pagine di ricerca sono lentissime
     "link": r"executiveimmobiliare\.it/listings/[\w-]+"},
    {"nome": "Castelletti",
     "pagine": ["https://www.castellettire.it/web/immobili.asp?tipo_contratto=V&language=ita",
                "https://www.castellettire.it/web/immobili.asp?tipo_contratto=A&language=ita"],
     "link": r"castellettire\.it/web/immobile_dettaglio\.asp\?cod_annuncio=\d+", "dettaglio": True},
    {"nome": "Homedreams",
     "pagine": ["https://homedreams.it/it/Vendite/", "https://homedreams.it/it/Affitti/"],
     "link": r"homedreams\.it/it/(?:Vendite|Affitti)/[\w-]+/[\w-]+/\w+/\d+"},
    {"nome": "Paccione",
     "pagine": ["https://www.paccioneimmobiliare.com/immobili"],
     "link": r"paccioneimmobiliare\.com/immobili/[\w-]{6,}"},
    {"nome": "Zarra",
     "pagine": ["https://www.zarraimmobiliare.com/annunci/"],
     "link": r"zarraimmobiliare\.com/annuncio/[\w-]+"},
]


class Sessione:
    def __init__(self):
        self.s = requests.Session()
        self.s.headers.update({"User-Agent": UA, "Accept-Language": "it-IT,it;q=0.9"})

    def get(self, url):
        r = self.s.get(url, timeout=45)
        r.raise_for_status()
        time.sleep(random.uniform(1.0, 2.0))      # con calma: un sito alla volta, una pagina alla volta
        try:
            testo = r.content.decode("utf-8")
        except UnicodeDecodeError:
            testo = r.content.decode(r.apparent_encoding or "latin-1", errors="replace")
        return BeautifulSoup(testo, "html.parser"), r.url


def _norm(url: str) -> str:
    return url.split("#")[0].rstrip("/")


def _chiave(nome: str, url: str) -> str:
    m = re.search(r"(\d{4,})(?!.*\d{4,})", url)
    ident = m.group(1) if m else hashlib.sha1(url.encode()).hexdigest()[:12]
    if nome == "RE/MAX":                       # .../zona-21260132-226: id + progressivo
        m = re.search(r"-(\d+-\d+)$", url)
        ident = m.group(1) if m else ident
    return f"{re.sub(r'\W', '', nome.lower())}:{ident}"


def _testo(el) -> str:
    return re.sub(r"(\s*\|\s*)+", " | ", el.get_text(" | ", strip=True))


def _titolo(t: str) -> str:
    parti = [p for p in t.split(" | ") if len(p) > 6 and not SERVIZIO.search(p)]
    if not parti:
        return ""
    i = next((k for k, p in enumerate(parti) if TIPI.search(p) and not PREZZO.search(p)), 0)
    titolo = parti[i]
    # "Trilocale in vendita" + "Bari, Via X - Poggiofranco": tipo e indirizzo insieme
    if i + 1 < len(parti) and len(parti[i + 1]) < 70 and not PREZZO.search(parti[i + 1]) \
            and not re.search(r"\d+\s*(?:m²|mq|locali|vani)|rif\.", parti[i + 1], re.I):
        titolo += " · " + parti[i + 1]
    return titolo[:160]


def _img(el, base):
    for im in el.find_all("img"):
        src = im.get("data-src") or im.get("src") or ""
        if src and not src.startswith("data:") and not re.search(r"logo|icon|sprite|\.svg", src, re.I):
            return urljoin(base, src)
    return None


def schede(soup, base: str, link_rx: re.Pattern) -> dict[str, dict]:
    """url annuncio -> {testo, img}: il riquadro più grande che contiene solo quell'annuncio."""
    out: dict[str, dict] = {}
    for a in soup.find_all("a", href=True):
        url = _norm(urljoin(base, a["href"]))
        if not link_rx.search(url) or urlparse(url).netloc.endswith(("facebook.com", "twitter.com", "pinterest.com")):
            continue
        el = a
        while el.parent is not None and el.parent.name not in ("body", "html", "[document]"):
            altri = {_norm(urljoin(base, x["href"])) for x in el.parent.find_all("a", href=True)}
            if len({u for u in altri if link_rx.search(u)}) > 1 or len(el.parent.get_text()) > 2500:
                break
            el = el.parent
        t = _testo(el)
        if url not in out or (PREZZO.search(t) and not PREZZO.search(out[url]["testo"])) or len(t) > len(out[url]["testo"]):
            out[url] = {"testo": t[:900], "img": _img(el, base)}
    return out


def _tecnocasa(soup) -> dict[str, dict]:
    out = {}
    el = soup.find(attrs={":estates": True})
    for e in json.loads(el[":estates"]) if el else []:
        parti = [e.get("title"), e.get("subtitle"), e.get("price"), e.get("surface"), e.get("rooms"), e.get("bathrooms")]
        img = ((e.get("images") or [{}])[0].get("url") or {}).get("card")
        out[e["detail_url"]] = {"testo": " | ".join(str(p) for p in parti if p), "img": img}
    return out


def _dettaglio(ses, url) -> str:
    soup, _ = ses.get(url)
    # via menu, filtri di ricerca e colonne laterali: contengono parole come "box" o "villa"
    for x in soup(["script", "style", "nav", "header", "footer", "noscript", "form", "select", "aside"]):
        x.decompose()
    h1 = soup.find("h1")
    testo = _testo(soup.body or soup)
    if h1:
        t1 = h1.get_text(" ", strip=True)
        i = testo.find(t1)
        testo = testo[i:] if i >= 0 else t1 + " | " + testo
    return testo[:1500]


def leggi_siti(conosciuti: set[str], stato_siti: dict) -> list[dict]:
    """Annunci di tutti i siti. stato_siti viene aggiornato con esito e numero di annunci per sito."""
    if BeautifulSoup is None:
        print("[siti] manca beautifulsoup4: pip install beautifulsoup4")
        return []
    ses = Sessione()
    cards = []
    for sito in SITI:
        nome = sito["nome"]
        trovati, errori = {}, []
        rx = re.compile(sito.get("link", r"$^"))
        for pagina in sito["pagine"]:
            try:
                soup, base = ses.get(pagina)
                trovati.update(_tecnocasa(soup) if sito.get("tipo") == "tecnocasa" else schede(soup, base, rx))
            except Exception as e:
                errori.append(f"{pagina}: {type(e).__name__} {str(e)[:80]}")
        dettagli = 0
        for url, c in trovati.items():
            key = _chiave(nome, url)
            riquadro = c["testo"]
            z = trova(riquadro)
            p = _prezzo(riquadro)
            # si apre la scheda quando l'elenco non basta: manca il prezzo, è un affitto
            # (stanze e case per studenti si capiscono solo dalla descrizione) o manca il quartiere
            apri = (sito.get("dettaglio") or not p or p < SOGLIA_AFFITTO
                    or z is None or z.regola == "generica")
            scheda = ""
            # "conosciuti" contiene gli id salvati in memoria (sha1 della chiave, 16 caratteri)
            gia_visto = key in conosciuti or hashlib.sha1(key.encode()).hexdigest()[:16] in conosciuti
            if apri and not gia_visto:
                if dettagli >= MAX_DETTAGLI:
                    continue                      # lo leggo al prossimo giro
                try:
                    scheda = _dettaglio(ses, url)
                    dettagli += 1
                except Exception as e:
                    errori.append(f"{url}: {type(e).__name__}")
                    continue
            testo = (riquadro + " | " + scheda) if scheda else riquadro
            specifica = z is not None and z.regola != "generica"
            cards.append({"key": key, "fonte": nome, "url": url, "testo": testo,
                          "testo_zona": riquadro if specifica else testo,
                          "scheda_letta": bool(scheda),
                          "titolo": _titolo(riquadro if PREZZO.search(riquadro) else testo),
                          "img": c.get("img")})
        stato_siti[nome] = {"annunci": len(trovati), "errori": errori[:3],
                            "ok": bool(trovati) and not errori}
        print(f"   {nome}: {len(trovati)} annunci" + (f", {len(errori)} errori" if errori else ""))
    return cards
