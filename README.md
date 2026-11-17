# 🏠 Radar case Bari

È il fratello del radar del Bari e del radar carte Pokémon. Legge gli **avvisi email**
delle ricerche salvate su Immobiliare.it, Idealista, Casa.it e Subito (e sui siti di aste).
Per ogni annuncio calcola il **prezzo al m²** e lo confronta con la **media della zona**.
Se conviene, lo manda nel **gruppo Telegram** vostro, con i bottoni ❤️ 📞 🗓 ❌.

## Perché gli avvisi email e non la lettura diretta dei siti

Immobiliare, Idealista, Casa.it e Subito bloccano i programmi che leggono le loro pagine,
e aggirare il blocco non è permesso. Gli avvisi email sono il canale ufficiale: arrivano
appena esce un annuncio e funzionano anche a PC spento.
Le agenzie che vi interessano (Tecnocasa, Tempocasa, Iconacasa, Studio Vitulli,
Professionecasa, RE/MAX, Masi, Casa di Bari, Rafaschieri, Vistocasa) pubblicano tutte
su questi portali. Anche le aste ci finiscono (Aste Florio, Centro Aste, Aste Agency...).

## Come decide

- **Zona**: la riconosce dal titolo (es. "Trilocale via X, **Poggiofranco**, Bari").
  Le zone, le parole e i prezzi medi sono in `dati/zone.csv` (Immobiliare.it, ottobre 2026).
  - **Escluse sempre**: San Paolo, CEP, San Pio/Enziteto.
  - **Solo con box o posto auto**: Murat e Umbertino.
  - "Umbertina - Madonnella" (la zona di Immobiliare.it) conta come Madonnella: controlla la via.
- **Comuni vicini** (dal 17/11/2026): arrivano solo **ville, villette, case indipendenti** e case di
  **nuova costruzione**; gli appartamenti normali fuori Bari vengono scartati. Per le nuove costruzioni
  la media della zona sale del 25% (il nuovo costa di più). Si annulla in `radar/config.py`:
  `COMUNI_SOLO_VILLE_E_NUOVE = False`.
- **Budget**: vendita fino a 200.000 € (per le aste vale il prezzo base), affitto fino a 1.000 €/mese.
  Si cambia in `radar/config.py` (`MAX_VENDITA`, `MAX_AFFITTO`).
- **Affare** = prezzo al m² rispetto alla media della zona:
  - 🚨 **Super affare**: almeno il 25% sotto la media (suona);
  - 💡 **Buon affare**: almeno il 12% sotto (silenzioso);
  - 🏠 nella media, **ma con box o posto auto**: arriva lo stesso;
  - i prezzi nella media senza box e quelli cari non arrivano (li vedete con /migliori).
- **Da ristrutturare**: al prezzo aggiunge 500 €/m² di lavori prima di confrontarlo.
- **Aste**: avvisa che la base d'asta si può ribassare del 25% (offerta minima) e segnala
  se l'immobile è occupato. Scarta le aste "non visitabili".
- ⚠️ **Prezzo troppo basso** (affitto sotto il 45% della media, vendita sotto il 35%):
  di solito è una stanza, una nuda proprietà, una quota o un errore. Arriva con l'avviso.
- **Stesso appartamento su più portali** (stessa zona, prezzo e m²): arriva una volta sola.
- Un annuncio torna solo se **il prezzo scende**.

## Nel gruppo Telegram

Sotto ogni annuncio ci sono quattro bottoni: ❤️ Mi piace · 📞 Chiamato · 🗓 Visita · ❌ Scarta.
Nel messaggio compare chi ha premuto cosa ("❤️ Mi piace: Davide"). Un secondo tocco annulla.
Comandi: **/migliori** (i 15 più convenienti), **/preferiti**, **/stato**.
Il radar legge i bottoni a ogni giro, quindi il nome compare entro 15 minuti.

## Prima configurazione (circa 20 minuti)

### 1. Il bot nuovo e il gruppo
1. Su Telegram apri **@BotFather**, scrivi `/newbot` e scegli un nome (es. "Radar Case Bari").
   BotFather ti dà il **token**.
2. Crea un **gruppo** con la tua fidanzata e aggiungi il bot. Scrivi "ciao" nel gruppo.
3. Copia `.env.esempio` in `.env` e incolla il token dopo `TELEGRAM_BOT_TOKEN=`.
4. Doppio clic su `trova-chat-id.bat`: scrive l'id del gruppo nel `.env` e manda un messaggio di prova.

### 2. Le ricerche salvate (avvisi email)
Usate **la stessa email** su tutti i portali (meglio un Gmail). Su ogni portale fate le
ricerche con i filtri qui sotto e attivate l'avviso email **immediato**, non il riepilogo giornaliero.

| Ricerca | Filtri |
|---|---|
| Bari vendita | max 200.000 €, zone: Libertà, Marconi-San Cataldo, San Girolamo-Fesca, Stanic, Palese, Santo Spirito, Carrassi, San Pasquale, Picone, Mungivacca, Poggiofranco, Madonnella, Bari Vecchia, Japigia, San Giorgio, Torre a Mare, Sant'Anna, Carbonara, Ceglie, Loseto |
| Bari affitto | max 1.000 €/mese, stesse zone |
| Centro con box | Murat + Umbertino, vendita e affitto, filtro "box/posto auto" |
| Comuni vendita | max 200.000 €: Modugno, Triggiano, Capurso, Valenzano, Bitritto, Noicattaro, Adelfia, Mola di Bari, Bitonto, Giovinazzo |
| Comuni affitto | max 1.000 €/mese, stessi comuni |
| Aste | su Immobiliare.it filtro "Aste" per Bari e comuni; su astegiudiziarie.it avviso per il Tribunale di Bari |

Disegnare le zone sulla mappa (Immobiliare e Idealista lo permettono) è il modo più preciso.

### 3. La password per le app di Gmail
Account Google → Sicurezza → Verifica in due passaggi (deve essere attiva) → **Password per le app**.
Creane una chiamata "radar case" e mettila nel `.env` dopo `EMAIL_APP_PASSWORD=`, con l'indirizzo
dopo `EMAIL_ADDRESS=`. Il radar **legge soltanto** la posta: non sposta, non cancella e non segna come letto nulla.

### 4. Prova sul PC
```
pip install -r requirements.txt
python -m radar.main --dry-run
```
Stampa a video quello che manderebbe. Senza `--dry-run` scrive nel gruppo.
Si può anche provare un'email salvata: `python -m radar.main --dry-run --file avviso.eml`.

### 5. Online 24 ore su 24 (GitHub, gratis)
Crea un repository su GitHub e carica questa cartella (senza il file `.env`).
In **Settings → Secrets and variables → Actions** aggiungi: `TELEGRAM_BOT_TOKEN`,
`TELEGRAM_CHAT_ID`, `EMAIL_ADDRESS`, `EMAIL_APP_PASSWORD`.
Il radar parte da solo ogni 30 minuti (`.github/workflows/radar.yml`).
Con un repository **privato** GitHub dà 2.000 minuti al mese: in quel caso metti
`*/30` al posto di `*/15` nel file del workflow.

## Se un portale cambia il formato delle email
Inoltratemi un avviso (o salvatelo come `.eml`): basta adattare `radar/email_avvisi.py`.
Le prove sono in `tests/` (`python -m unittest`).
