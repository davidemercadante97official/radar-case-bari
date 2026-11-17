"""Prove del radar: python -m unittest -v"""
import unittest
from email.message import EmailMessage

from radar import email_avvisi
from radar.annunci import leggi
from radar.main import prepara
from radar.valuta import da_notificare

EMAIL_HTML = """
<html><head><style>.x{color:red}</style></head><body>
<p>Ciao, ci sono 3 nuovi annunci per la tua ricerca</p>
<table>
<tr><td><a href="https://click.immobiliare.it/r?u=https%3A%2F%2Fwww.immobiliare.it%2Fannunci%2F128941026%2F">
<img src="https://pwm.im-cdn.it/image/1/m-c.jpg" width="300"></a></td></tr>
<tr><td><a href="https://click.immobiliare.it/r?u=https%3A%2F%2Fwww.immobiliare.it%2Fannunci%2F128941026%2F">
Quadrilocale via Carlo Borsani, Poggiofranco, Bari</a></td></tr>
<tr><td>€ 150.000</td></tr><tr><td>4 locali · 119 m² · 1 bagno · 3° piano · Balcone · Box auto</td></tr>
<tr><td><a href="https://www.immobiliare.it/annunci/131628890/">Bilocale via Castromediano, San Pasquale, Bari</a></td></tr>
<tr><td>€ 280.000 · 2 locali · 74 m²</td></tr>
<tr><td><a href="https://www.immobiliare.it/annunci/999000111/">Trilocale viale Japigia, San Paolo, Bari</a></td></tr>
<tr><td>€ 90.000 · 3 locali · 80 m²</td></tr>
<tr><td><a href="https://www.idealista.it/immobile/34567890/">Appartamento in affitto via Ravanas, Libertà, Bari</a></td></tr>
<tr><td>800 €/mese · 100 m² · 4 locali · 1° piano</td></tr>
</table>
<p><a href="https://www.immobiliare.it/unsubscribe?x=1">Disiscriviti</a></p>
</body></html>
"""


def msg():
    m = EmailMessage()
    m["Subject"] = "Nuovi annunci"
    m["From"] = "avvisi@immobiliare.it"
    m.set_content("versione testo")
    m.add_alternative(EMAIL_HTML, subtype="html")
    return m


class TestRadar(unittest.TestCase):
    def setUp(self):
        self.cards = email_avvisi.annunci_da_email(msg())
        self.ann = {c["key"]: prepara(c) for c in self.cards}

    def test_schede(self):
        self.assertEqual([c["key"] for c in self.cards],
                         ["immobiliare:128941026", "immobiliare:131628890",
                          "immobiliare:999000111", "idealista:34567890"])

    def test_campi(self):
        a = self.ann["immobiliare:128941026"]
        self.assertEqual((a["prezzo"], a["mq"], a["locali"], a["bagni"], a["piano"]), (150000, 119, 4, 1, "3°"))
        self.assertTrue(a["box"] and a["balcone"])
        self.assertEqual(a["zona"], "Poggiofranco")
        self.assertEqual(a["livello"], "super")       # 1.261 €/m² contro 2.531
        self.assertTrue(da_notificare(a))
        self.assertTrue(a["img"])

    def test_budget_e_zone_escluse(self):
        self.assertEqual(self.ann["immobiliare:131628890"]["scarta"], "vendita sopra il budget")
        self.assertIn("esclusa", self.ann["immobiliare:999000111"]["scarta"])

    def test_affitto_super(self):
        a = self.ann["idealista:34567890"]
        self.assertTrue(a["affitto"])
        self.assertEqual(a["zona"], "Libertà")
        self.assertEqual(a["livello"], "super")      # 8 €/m² contro 12,20 €/m²

    def test_solo_con_box(self):
        base = {"key": "x:1", "fonte": "T", "url": "u", "img": None}
        no = prepara({**base, "testo": "Trilocale via Cairoli, Murat, Bari | € 190.000 | 90 m²"})
        si = prepara({**base, "testo": "Trilocale via Cairoli, Murat, Bari | € 190.000 | 90 m² | posto auto"})
        self.assertIn("box", no["scarta"])
        self.assertIsNone(si["scarta"])

    def test_asta_e_ristrutturare(self):
        a = leggi("Asta giudiziaria appartamento occupato, prezzo base € 60.000, 80 mq, da ristrutturare")
        self.assertTrue(a["asta"] and a["occupato"] and a["ristrutturare"])
        self.assertEqual(a["prezzo"], 60000)
        b = prepara({"key": "x:2", "fonte": "T", "url": "u", "img": None,
                     "testo": "Asta Ceglie del Campo non visitabile € 30.000 70 mq"})
        self.assertEqual(b["scarta"], "asta non visitabile")


    def test_comuni_solo_ville_e_nuove(self):
        base = {"fonte": "T", "url": "u", "img": None}
        app = prepara({**base, "key": "x:10", "testo": "Appartamento in vendita in Via Roma | Triggiano (BA) | € 90.000 | 100 mq"})
        villa = prepara({**base, "key": "x:11", "testo": "Villa in vendita in Via Roma | Capurso (BA) | € 190.000 | 160 mq"})
        nuova = prepara({**base, "key": "x:12", "testo": "Trilocale nuova costruzione | Modugno (BA) | € 170.000 | 90 mq"})
        bari = prepara({**base, "key": "x:13", "testo": "Trilocale via Roma, Japigia, Bari | € 150.000 | 100 mq"})
        stanic = prepara({**base, "key": "x:14", "testo": "Trilocale Villaggio del Lavoratore, Stanic, Bari | € 120.000 | 90 mq"})
        self.assertIn("solo ville", app["scarta"])
        self.assertIsNone(villa["scarta"])
        self.assertTrue(da_notificare(villa))           # 1.188 €/m² contro 1.430: -17%
        self.assertIsNone(nuova["scarta"])
        self.assertEqual(nuova["media_mq"], round(1783 * 1.25))
        self.assertIsNone(bari["scarta"])
        self.assertFalse(stanic.get("indipendente"))   # "Villaggio" non è una villa

    def test_siti_schede(self):
        import re
        from bs4 import BeautifulSoup
        from radar import siti
        html = """<div class="lista">
          <div class="card"><a href="/annuncio/111"><img src="/f1.jpg"></a>
            <h3>Trilocale in vendita</h3><p>Bari, Via Giovanni Modugno - Poggiofranco</p>
            <p>€ 180.000</p><p>71 Mq · 3 locali</p><a href="/annuncio/111">Dettagli</a></div>
          <div class="card"><a href="/annuncio/222">Negozio in via dei Mille, Bari</a><p>€ 90.000</p></div>
        </div>"""
        s = siti.schede(BeautifulSoup(html, "html.parser"), "https://agenzia.it/", re.compile(r"/annuncio/\d+"))
        self.assertEqual(len(s), 2)
        c = s["https://agenzia.it/annuncio/111"]
        self.assertNotIn("Negozio", c["testo"])            # il riquadro non sconfina nell'annuncio dopo
        a = prepara({"key": "t:111", "fonte": "T", "url": "https://agenzia.it/annuncio/111",
                     "testo": c["testo"], "titolo": siti._titolo(c["testo"]), "img": c["img"]})
        self.assertEqual((a["prezzo"], a["mq"], a["locali"], a["zona"]), (180000, 71, 3, "Poggiofranco"))
        self.assertTrue(a["img"].endswith("/f1.jpg"))


if __name__ == "__main__":
    unittest.main()
