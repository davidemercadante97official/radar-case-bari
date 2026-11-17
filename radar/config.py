"""Impostazioni del radar case. Cambia i numeri qui."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# --- Budget ------------------------------------------------------------------
MAX_VENDITA = 200_000          # € prezzo massimo in vendita (le aste: prezzo base)
MAX_AFFITTO = 1_000            # € al mese
SOGLIA_AFFITTO = 5_000         # sotto questa cifra un prezzo è un affitto mensile

# --- Quando è un affare (prezzo al m² diviso media della zona) -----------------
SUPER = 0.75                   # 🚨 almeno il 25% sotto la media
BUONO = 0.88                   # 💡 almeno il 12% sotto la media
CARO = 1.10                    # 🔺 oltre il 10% sopra la media
SOSPETTO_AFFITTO = 0.45        # affitto sotto il 45% della media: stanze, studenti o errore
SOSPETTO_VENDITA = 0.35
# affitto sotto il 35% della media e scheda non leggibile: si scarta (è una stanza)
STANZA_AFFITTO = 0.35        # vendita sotto il 35%: nuda proprietà, quota, rudere o errore

# Una casa da ristrutturare si confronta aggiungendo il costo stimato dei lavori.
LAVORI_MQ = 500                # € al m² (ristrutturazione media completa a Bari)

# Mq minimi per considerare un annuncio una casa (sotto: box, cantine, monolocali minuscoli)
MQ_MIN = 35

# --- Comuni vicini (modifica del 17/11/2026) ----------------------------------
# Fuori Bari arrivano solo ville/villette/case indipendenti e case di nuova costruzione.
# Per tornare a prima (tutte le case dei comuni) metti False.
COMUNI_SOLO_VILLE_E_NUOVE = True
# Il nuovo costa di più dell'usato: la media della zona si alza del 25% per confrontarlo
NUOVO_COEFF = 1.25

# --- Notifiche -----------------------------------------------------------------
# Livelli che arrivano su Telegram: "super", "buono", "media", "caro"
NOTIFICA = {"super", "buono"}
# Le case con box/posto auto in zona buona arrivano anche se "nella media"
NOTIFICA_MEDIA_CON_BOX = True
MAX_MESSAGGI_PER_GIRO = 25
SILENZIOSI = True              # solo i super affari suonano

# --- Siti delle agenzie ---------------------------------------------------------
# Lettura diretta dei siti (radar/siti.py). Con il repository privato i minuti gratis di
# GitHub sono 2.000 al mese: i siti si leggono ogni 4 ore, le email ogni 30 minuti.
SITI_ATTIVI = True
SITI_OGNI_ORE = 4

# --- Email ---------------------------------------------------------------------
# Mittenti degli avvisi delle ricerche salvate
MITTENTI = ["immobiliare.it", "idealista.it", "idealista.com", "casa.it", "subito.it",
            "wikicasa.it", "astegiudiziarie.it", "pvp.giustizia.it"]
# Dove cercare: posta in arrivo ed etichetta "Case" (filtro di Gmail)
CARTELLE_EMAIL = ["INBOX", "Case"]
GIORNI_EMAIL = 4               # quanti giorni indietro leggere a ogni giro
MAX_SALVATI = 5000
