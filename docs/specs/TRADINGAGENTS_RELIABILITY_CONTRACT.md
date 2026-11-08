# TRADINGAGENTS_RELIABILITY_CONTRACT.md

> **Tipo documento:** contratto di implementazione per agente AI di sviluppo software (Codex / Claude Code / GitHub Copilot)
> **Progetto di riferimento:** applicazione di analisi multi-agente e simulazione di trading con TradingAgents 0.7.1
> **Caso di regressione iniziale:** `BRK-B`, report generato il 2026-11-08 alle 08:31:52 (fuso del sistema da verificare)
> **Priorità:** P0 sicurezza/correttezza → P1 qualità analitica → P2 misurazione e miglioramento
> **Obiettivo:** trasformare report persuasivi in decisioni verificabili, coerenti temporalmente, riproducibili e non eseguibili se il rischio non è validato.

## 0. Istruzioni vincolanti per l'agente di sviluppo

**Devi lavorare sul repository esistente, non limitarti a descrivere una soluzione.** Prima ispeziona struttura, linguaggi, entrypoint, test, modelli dati, provider, scheduler, dashboard, motore ordini e configurazioni. Poi implementa le modifiche compatibili con l'architettura rilevata, aggiungendo test e documentazione. Procedi autonomamente nelle operazioni locali e nei test; non fermarti per approvazioni ripetitive. Chiedi autorizzazione solo per operazioni esterne, distruttive, credenziali mancanti o attivazione del trading reale. Non fingere che codice o test inesistenti siano stati eseguiti.

**Vincoli di non regressione:**

1. Conserva l'integrazione esistente con `openai_compatible`, `llmfactory:local:GLM-5.3`, `llmfactory:local:DeepSeek-V4.1-Flash` e la selezione configurabile dei modelli; non sostituire provider o credenziali.
2. Conserva e adatta le interfacce già disponibili per `yfinance`, `sec_edgar`, `fred` e `polymarket`, con nuove verifiche di provenienza. Non assumere che un provider esponga campi non documentati.
3. Non riscrivere da zero l'applicazione senza necessità verificata. Evita cambiamenti fuori scope e mantieni compatibilità con lo storico dei report.
4. Non introdurre né abilitare ordini su conti reali. **Default e test solo `paper/simulation`**. Ogni possibilità di live trading, se già presente, deve restare disabilitata salvo autorizzazione esplicita e configurazione separata. Non modificare fondi, portafogli o ordini reali.
5. Non memorizzare segreti nei report, nei log, nei test o nel repository. Rispetta `.env`, `.gitignore` e permessi minimi.
6. Per ogni modifica fornisci prova: test, schema, log di test sintetico, file modificati, limitazioni residue. Se un'integrazione non è disponibile, implementa un adapter/mock e dichiara il blocco anziché inventare risultati.

## 1. Problemi osservati da correggere (BRK-B, 8 novembre 2026)

| ID | Riscontro | Rischio | Correzione richiesta |
|---|---|---|---|
| DEF-001 | Il report attribuisce alla chiusura di venerdì 6/11 una reazione al Q3 pubblicato sabato 7/11 | **Look-ahead / causalità temporale falsa** | Verifica dell'orario di pubblicazione e della prima quotazione successiva all'evento |
| DEF-002 | Il Fundamentals Analyst dichiara ultimo trimestre disponibile Q2, mentre News e dibattito impiegano Q3 | **Stato dati non coerente** | Snapshot condiviso, fonti primarie, stato esplicito dei documenti disponibili |
| DEF-003 | `HOLD`, `BUY` e `Overweight` vengono trattati come azioni equivalenti, anche se il piano impone zero acquisti a 570,89 | **Rischio di ordine non autorizzato** | Separare valutazione strategica da decisione eseguibile |
| DEF-004 | Terza tranche a 543,70 e stop a 543,50 con ATR 9,41 | **Stop quasi coincidente con entry** | Validazione deterministica del buffer rispetto alla volatilità |
| DEF-005 | Target 125% senza esposizione, capitale e budget di rischio del portafoglio | **Sizing non giustificato** | Bloccare nuova esposizione finché il contesto non è disponibile |
| DEF-006 | Metriche vendor incongruenti: P/B A/B, FCF, revenue TTM, forward EPS | **Valuation contaminata** | Riconciliazione unità/classi azionarie e quarantena dei dati non validi |
| DEF-007 | Molti round ripetono l'affermazione iniziale senza nuove prove indipendenti | **Amplificazione di errori** | Fact Checker, controverifica e limite alla ridondanza |
| DEF-008 | Quote Polymarket presentate come distribuzione di probabilità senza verificare struttura degli esiti | **Probabilità non interpretabili** | Verificare mutua esclusività, esaustività e timestamp del mercato |
| DEF-009 | Prezzi storici, indicatori e tesi vengono riusati come se fossero validi anche al trigger futuro | **Ordini su segnali scaduti** | Ricalcolo degli indicatori e dei vincoli al momento della decisione |
| DEF-010 | Il report tratta buyback storici, cassa e beta come garanzie di floor/protezione | **Sovrastima della confidenza** | Etichettare le inferenze come ipotesi, non fatti o limiti di perdita |

**Non hardcodare le regole per BRK-B:** ogni correzione deve essere applicabile a qualsiasi ticker, data, evento e asset supportato. Il caso BRK-B serve esclusivamente come fixture di regressione.

## 2. Architettura target minima

Implementare o integrare il seguente flusso logico nella struttura già esistente:

```text
Data Vendors / Market Data / Filings / News / Prediction Markets
                |
                v
        Source Normalization
        + Provenance Registry
                |
                v
     Shared As-Of Data Snapshot
                |
                v
     Deterministic Data Validator  <----> Fact Checker
                |
                v
 Analysts (market / sentiment / news / fundamentals)
                |
                v
 Research Debate --> Research Manager
                |
                v
 Trader: proposed thesis + candidate plan
                |
                v
 Risk Debate --> Portfolio Manager (strategic opinion)
                |
                v
   DETERMINISTIC POLICY / RISK ENGINE
                |
                v
          EXECUTION GATE
            /       \
           v         v
       WAIT/BLOCK  PAPER ORDER (only when validated)
                |
                v
          Audit Trail + Report
```

**Regola fondante:** gli LLM formulano ipotesi e proposte, ma **non possono bypassare controlli deterministici** su disponibilità dei dati, causalità, budget, ordini, stop e condizioni di attivazione. Il loro voto non modifica da solo `execution_action`.

## 3. P0 — Provenienza, aggiornamento dati e causalità temporale

### 3.1 Snapshot comune

Ogni run deve avere un `analysis_as_of` assoluto in UTC e un `market_calendar` esplicito (es. `XNYS`, timezone `America/New_York`). Registrare l'ora effettiva di generazione separatamente da quella dell'ultimo dato di mercato. Tutti gli agenti devono leggere lo **stesso snapshot versionato**: non devono assemblare versioni incompatibili senza segnalarlo.

Ogni fatto numerico deve conservare almeno:

```json
{
  "fact_id": "berkshire_q3_operating_earnings",
  "value": 12705,
  "unit": "USD_million",
  "period": "2026-Q3",
  "period_end": "2026-09-30",
  "source_type": "company_release",
  "source_uri": "<URI verificato dal provider>",
  "published_at": "<ISO-8601 con offset reale>",
  "retrieved_at": "<ISO-8601 UTC>",
  "verification_status": "verified",
  "snapshot_id": "<ID stabile>"
}
```

Non inventare date di pubblicazione, URL, periodi fiscali o valori. Se l'origine non espone l'informazione, impostare `unknown` e applicare la regola di blocco pertinente. Il `published_at` è distinto da `period_end` e `retrieved_at`.

### 3.2 Event-to-price causal guard

Una frase del tipo **«il titolo ha assorbito la trimestrale con un movimento del X%»** è ammissibile solo se la finestra di prezzo utilizzata è successiva alla vera pubblicazione dell'evento e corrisponde alla sessione corretta (pre-market, regular, after-hours, non-trading day). Distinguere:

- `NOT_YET_OBSERVABLE`: non esiste ancora una sessione/prezzo successivo all'evento.
- `OBSERVABLE`: esistono prezzi post-evento validati, con finestra e fonte esplicite.
- `INSUFFICIENT_DATA`: non sono disponibili prezzi o timestamp attendibili.

Una chiusura precedente alla pubblicazione **non** può essere trattata come reazione successiva. La sola disponibilità della notizia in un articolo non ne dimostra l'impatto sul titolo.

Per notizie di bilancio, distinguere `company_release_available`, `sec_filing_available`, `filing_pending` e `unverified`. Non ignorare un comunicato ufficiale disponibile soltanto perché un adapter SEC non ha ancora restituito il 10-Q. Non fingere che il 10-Q sia pubblicato se non lo è.

### 3.3 Data validator e riconciliazione

- Verificare identità del titolo, valuta, unità (USD vs milioni/miliardi), periodo, standard contabile e classe azionaria prima di dividere metriche.
- Per BRK-A e BRK-B usare il rapporto di conversione pertinente e **azioni equivalenti coerenti**; mai dividere un prezzo B per un book value A senza conversione.
- Non ricavare `investimenti azionari netti` dal solo cash flow investing aggregato: usare le voci di acquisto/vendita azioni.
- Non usare automaticamente net income, EPS forward o P/E headline come proxy degli **operating earnings** di Berkshire.
- Separare cash, cash equivalents, Treasury bills, importi in regolamento, disponibilità vincolata e float; non assumere che ogni dollaro sia investibile.
- Per market cap / per-share ratios, verificare share count, unità e data di riferimento.
- Calcolare `reported_value`, `derived_value`, `reconciliation_delta`, `materiality`, `status`.
- Valori contestati diventano `QUARANTINED` o `UNVERIFIED`, **non** alimentano rating, target o ordini fino a risoluzione o esplicita degradazione di confidenza.
- Controllare coerenza OHLC (`low <= min(open,close) <= max(open,close) <= high`), volumi non negativi, adjustment/split, calendario e dati mancanti.

### 3.4 Prediction markets

I mercati predittivi sono fonti ausiliarie, non oracoli. Registrare ID mercato, condizioni di settlement, timestamp, liquidità, volume, bid/ask e fonte. Validare somme delle probabilità **solo per esiti della stessa partizione mutuamente esclusiva ed esaustiva**, tenendo conto di bid-ask/commissioni. **Non** sommare mercati indipendenti o bucket sovrapposti come se fossero un'unica distribuzione. Se la struttura degli esiti non è chiara, segnare `NOT_COMPARABLE` e non usarla nella tesi quantitativa.

## 4. P0 — Contratto della decisione e Execution Gate

Separare obbligatoriamente tre livelli:

1. **Strategic rating**: `UNDERWEIGHT | NEUTRAL | OVERWEIGHT` (orizzonte dichiarato).
2. **Investment intent**: `AVOID | MONITOR | ACCUMULATE_CONDITIONALLY | MAINTAIN | REDUCE`.
3. **Execution action**: `WAIT | BLOCK | PROPOSE_PAPER_ORDER | SUBMIT_PAPER_ORDER`.

`OVERWEIGHT` non implica `BUY NOW`; `BUY` nel testo narrativo non autorizza un market order. I vecchi report possono mantenere i rating legacy, ma una funzione di mapping deve produrre in modo **esplicito** l'azione e l'eventuale `legacy_label`.

**Regole dure di blocco:**

- Fatti essenziali senza timestamp/provenienza adeguati, look-ahead rilevato o snapshot incoerente non risolto.
- Evento materiale pubblicato fuori mercato senza prezzi post-evento, quando la strategia si basa sulla presunta reazione a quell'evento.
- Prezzo/indicatore/volumi del trigger non aggiornati alla sessione prevista.
- Esposizione attuale, liquidità, commissioni, lotto minimo, valuta, rischio residuo o budget di perdita sconosciuti e necessari al dimensionamento.
- Stop invalido, buffer insufficiente senza deroga documentata, rischio oltre limite, ordini incoerenti o condizione di entrata non ancora verificata.
- Fallimento di dati di mercato, broker, clock o riconciliazione degli ordini; impedire retry che duplicano ordini.

Il Gate deve distinguere `WAIT` (nessun trigger ancora scattato) da `BLOCK` (piano invalido o mancano dati obbligatori). Nessuno dei due crea ordini, nemmeno ordini condizionali pendenti, senza un esplicito percorso autorizzato e tracciato. Ogni submit paper richiede controllo finale immediatamente prima dell'invio: sessione, prezzo, order idempotency key, exposure e condizioni aggiornate.

## 5. P0 — Risk Engine deterministico

Implementare calcoli in codice testabile, non in prosa generata dall'LLM:

- `entry_weighted_avg` calcolato sulle quantità o sui pesi realmente eseguiti, non sulle tranche solo proposte.
- `risk_per_share = entry_price - effective_exit_price` per posizioni long; logica separata per short se supportato.
- `planned_risk_currency`, `planned_risk_pct_equity`, `portfolio_exposure_pct`, concentrazione settoriale/ticker e correlazioni.
- `effective_exit_price` stressato per gap, slippage, spread e commissioni; stop su close e stop-market hanno semantiche differenti.
- `qty = floor(risk_budget_currency / stressed_risk_per_share)` con vincoli addizionali su cash, lotto, margin, exposure e limiti broker; mai usare una size negativa/infinita.
- Rifiutare automaticamente aumenti di size quando il rischio residuo o la qualità dei dati peggiorano, salvo policy approvata e misurabile.
- Revalidare tutti i limiti **dopo ogni fill** e prima di ogni nuova tranche.

**Buffer volatilità:** configurare un minimo tra entry e stop in ATR (esempio iniziale `min_entry_stop_atr = 0.5`, soglia parametrica, non legge universale). Sotto soglia il piano è `BLOCK` o richiede un'eccezione esplicita motivata e approvata; un LLM non può auto-approvarsi la deroga.

**Caso di regressione:** terza tranche BRK-B 543,70, stop 543,50, ATR 9,408: distanza 0,20, ovvero ~0,021 ATR. Il piano originario **deve fallire** la validazione. Può essere riformulato come ingresso condizionato *solo con nuova validazione integrale di stop, size e trigger*; non basta cambiare una parola nella descrizione.

Il `max_portfolio_loss_fraction` resta `null` / non eseguibile se il portafoglio non è noto. Una perdita del «2,28% dell'allocazione standard» **non equivale** al 2,28% dell'intero patrimonio; non convertirla senza base e capitale reali.

**Importante:** uno stop loss non garantisce la perdita massima. Nei report usare «perdita teorica/stressata» e mostrare scenari con gap; non dichiarare rischi garantiti né profitti attesi senza stima probabilistica verificata.

## 6. P1 — Fact Checker indipendente e dibattito efficiente

Introdurre uno step obbligatorio tra analisi e sintesi che produca una lista strutturata di claim:

```json
{
  "claim_id": "C-001",
  "statement": "Il mercato ha già assorbito il Q3",
  "classification": "causal_inference",
  "supporting_fact_ids": [],
  "status": "REFUTED",
  "reason_code": "EVENT_AFTER_LAST_MARKET_SESSION",
  "blocking": true
}
```

Categorie minime: `FACT`, `DERIVED_CALCULATION`, `HYPOTHESIS`, `FORECAST`, `UNSUPPORTED`, `REFUTED`. Il Fact Checker deve poter contraddire un analista o il Portfolio Manager e imporre un `BLOCK` per violazioni P0. Non deve introdurre dati di fantasia: calcoli, documenti e timestamp devono essere auditabili.

Per il debate:

- Rendere configurabili round e limite token; usare inizialmente max 3 round di ricerca e max 3 di rischio, salvo evidenza che round aggiuntivi migliorino i risultati.
- A ogni round richiedere **nuova evidenza, una confutazione verificabile o una modifica concreta al piano**. Se manca, interrompere per convergenza/ridondanza.
- Distinguere disaccordo sul rating da disaccordo sul trigger di esecuzione.
- Evitare «il Bull ha vinto quindi Overweight» senza analisi di confidenza, base rate, alternative e rischio.
- Non elevare un obiettivo isolato di StockTwits (es. 633 USD) a fair value ufficiale.
- Etichettare espressioni come «buyback floor», «opzione gratuita», «rifugio assoluto» come ipotesi, non proprietà garantite.

## 7. P1 — Snapshot tecnico fresco e scenari operativi

Per ogni segnale di ingresso registrare `indicator_as_of`, finestra temporale, formula e parametri. Medie mobili, ATR, RSI, MACD e Bollinger devono essere ricalcolati al trigger. I valori storici nel report sono livelli **di riferimento**, non limiti eterni.

Ogni scenario deve contenere:

- condizioni di attivazione misurabili (su tick, candela chiusa, volume rispetto a quale media e timeframe);
- condizioni di invalidazione distinte da normali livelli di supporto;
- azione in caso di salto del trigger, dati mancanti, gap, slippage e ordine parzialmente eseguito;
- scadenza (`valid_until`) del piano e frequenza di ricalcolo;
- risultato `WAIT` se le condizioni non sono soddisfatte.

Non attribuire una probabilità maggiore a uno scenario senza modello calibrato o evidenza storica. Un rapporto target/stop 1:1 non prova, da solo, un rendimento atteso nullo: occorre considerare probabilità, costi e slippage. Distinguerne la **geometria del payoff** dall'**expected value**.

## 8. Schema minimo di output machine-readable

Adattare ai modelli dati esistenti, ma mantenere equivalenti questi campi:

```json
{
  "schema_version": "1.0",
  "ticker": "BRK-B",
  "analysis_as_of": "2026-11-08T07:31:52Z",
  "market_snapshot": {
    "session_date": "2026-11-06",
    "calendar": "XNYS",
    "close": 570.89,
    "currency": "USD"
  },
  "events": [{
    "type": "earnings_release",
    "period": "2026-Q3",
    "publication_date": "2026-11-07",
    "published_at": null,
    "post_event_price_status": "NOT_YET_OBSERVABLE"
  }],
  "strategy": {
    "rating": "OVERWEIGHT",
    "intent": "ACCUMULATE_CONDITIONALLY",
    "horizon_months": [12, 18]
  },
  "execution": {
    "action": "WAIT",
    "market_order_allowed": false,
    "paper_order_allowed_now": false,
    "entry_triggers_satisfied": false,
    "portfolio_context_complete": false,
    "reason_codes": [
      "POST_EARNINGS_REACTION_UNOBSERVABLE",
      "ENTRY_TRIGGER_NOT_MET",
      "PORTFOLIO_RISK_BUDGET_MISSING"
    ]
  },
  "risk": {
    "stop_model": "UNVALIDATED",
    "max_portfolio_loss_fraction": null,
    "gap_stress_test_passed": false
  },
  "data_quality": {
    "status": "REQUIRES_RECONCILIATION",
    "blocking_claims": ["C-001"]
  },
  "audit": {
    "snapshot_id": "<generare realmente>",
    "policy_version": "<generare realmente>",
    "model_versions": {},
    "run_id": "<generare realmente>"
  }
}
```

Lo schema è un **esempio di regressione, non un ordine**. Il `published_at` è nullo finché non acquisito/verificato; non inventarlo. Se l'orario di generazione non è noto in UTC, convertirlo solo dopo aver verificato il timezone sorgente: il valore ISO sopra è illustrativo, **non un fatto verificato sul run originale**.

Accanto al report umano produrre sempre un JSON validato e un audit machine-readable. Se il JSON non passa validazione o il Gate blocca, il testo può comunque essere generato come ricerca, ma va marcato **NON ESEGUIBILE**.

## 9. Test obbligatori (unit, integration, regression)

Usare fixtures stabili e clock congelato; evitare che l'esito dei test dipenda dai prezzi live o dai testi non deterministici degli LLM.

1. **Temporal leakage BRK-B**: last market session venerdì 2026-11-06, earnings pubblicati sabato 2026-11-07, run domenica 2026-11-08 → `post_event_price_status=NOT_YET_OBSERVABLE`; vietata una claim «venerdì il mercato ha assorbito il Q3».
2. **Data availability**: release Q3 disponibile ma filing SEC Q3 non disponibile nella fixture → usare release come fonte per i valori supportati; stato filing `PENDING/UNAVAILABLE`; non dichiarare Q2 ultimo risultato complessivamente disponibile.
3. **Mismatch fondamentali**: Report Analyst Q2 / News Q3 → segnalare il conflitto e impedire sintesi non qualificata.
4. **Ticker/class mismatch**: prezzo BRK-B e BVPS BRK-A → calcolo diretto vietato; verifica conversioni/share count.
5. **Quarantena metriche**: FCF vendor inconciliabile e ricavi non omogenei → blocco uso nel rating finché non riconciliati.
6. **Risk buffer**: entry 543,70, stop 543,50, ATR 9,408 → `BLOCK`, senza deroga autonoma.
7. **Order intention**: rating `OVERWEIGHT`, piano condizionato e close 570,89 fuori trigger → `WAIT`, zero ordini.
8. **Portfolio missing**: target 125% senza equity/esposizione/risk budget → non calcolare quantità né inviare ordini.
9. **Gap/slippage**: simulare uscita un ATR oltre lo stop e mostrare rischio stressato; verificare che non venga presentato come perdita massima certa.
10. **Prediction markets**: mercati indipendenti non sommati; esiti esclusivi esaustivi con somma incompatibile → `UNVERIFIED`.
11. **Staleness**: ordine proposto su indicatore vecchio → ricalcolo obbligatorio o `WAIT/BLOCK`.
12. **Idempotenza**: retry di ordine paper con stessa key → nessun doppio ordine.
13. **Fail closed**: timeout provider, fonte senza timestamp, risposta LLM non parsabile → nessun ordine; log e codice causa.
14. **Non regression**: report storico ancora leggibile, provider e dashboard funzionanti, nessuna chiamata live broker nei test.
15. **Claim lineage**: ogni conclusione materiale include fact IDs e fonte; una claim `REFUTED` bloccante non può essere riportata come fatto dal Portfolio Manager.
16. **Price return sanity**: da 572,33 a 570,89 la variazione è circa -0,25%, non -0,01%; impedire uso del movimento come reazione al comunicato del sabato.

Testare anche timezone e cambio ora legale, weekend, festività NYSE, dati after-hours, asset con split, fill parziali, cancellazioni, invalidazione tra ordine e fill.

## 10. Osservabilità e report finale

Per ogni esecuzione salvare, in modo strutturato e senza segreti:

- `run_id`, `ticker`, versione modello/provider e commit del software;
- snapshot e hash/versione di ogni dataset; timestamp di pubblicazione e acquisizione;
- claim confutati, metriche in quarantena e conflitti irrisolti;
- rating, intent, azione operativa, trigger valutati, ragioni di WAIT/BLOCK;
- capitale/posizione (solo se disponibile), quantità proposte, limiti, scenari di gap/slippage;
- ordini paper effettivamente inoltrati, order ID, fill/cancel, retries e idempotency key;
- controlli Gate eseguiti e versione policy.

Dashboard/report: sezioni separate **Tesi**, **Dati e fonti**, **Qualità dati**, **Piano condizionale**, **Stato esecuzione**, **Rischio**, **Audit**. Il lettore deve capire in pochi secondi se il risultato è un'opinione, un piano o un ordine eseguito. Segnalare chiaramente «mercato chiuso» e «risultati pubblicati dopo l'ultima sessione» quando applicabile.

## 11. Rollout raccomandato

- **Fase A (P0)**: introdurre schema, snapshot, Data Validator, causal guard, Risk Engine, Execution Gate e test; esecuzione obbligatoriamente paper/disabilitata finché non passa la suite.
- **Fase B (P1)**: Fact Checker, debate stopping, ricalcolo trigger, report strutturato e UI di audit.
- **Fase C (P2)**: valutazione out-of-sample e walk-forward senza leakage, ablation test (con/senza debate), confronto con baseline deterministiche e monitoraggio falsi positivi, drawdown, stop slippage, costi, latenza e coverage delle fonti.

Non dichiarare il sistema «pronto» sulla base di una singola analisi BRK-B o di un singolo backtest. Serve misurazione su più titoli, regimi e sessioni.

## 12. Definition of Done — il lavoro è completo soltanto se

- [ ] Le componenti P0 sono implementate e collegate al flusso di trading esistente.
- [ ] In mancanza di trigger, budget o dati validi il sistema restituisce `WAIT/BLOCK` e non crea ordini.
- [ ] Il report BRK-B di regressione non contiene una falsa reazione del 6 novembre alla trimestrale del 7 novembre.
- [ ] I dati Q3 disponibili vengono riconosciuti con fonte e status, senza nascondere eventuale 10-Q assente.
- [ ] Il piano 543,70/543,50 con ATR 9,408 non passa il Risk Engine.
- [ ] Le metriche incongruenti sono riconciliate o escluse dalle decisioni.
- [ ] Il rating `OVERWEIGHT` non abilita automaticamente l'azione `BUY`.
- [ ] Ogni ordine paper ha una validazione finale, un budget autorizzato, log auditabile e idempotenza.
- [ ] I test automatici P0 passano; eventuali test impossibili sono riportati onestamente.
- [ ] Le funzionalità precedenti e i provider LLM/dati rimangono operativi.
- [ ] Sono aggiornati README/documentazione API, configurazioni di esempio e schema dati.
- [ ] È disponibile un riepilogo delle modifiche e delle limitazioni residue.

## 13. Formato della consegna da parte dell'agente di sviluppo

Al termine produci esattamente queste sezioni:

1. **Architettura rilevata e file coinvolti** (prima/dopo, senza inventare file).
2. **Implementazioni completate** per P0/P1/P2, con riferimenti a file e funzioni.
3. **Test eseguiti ed esito**: comandi, pass/fail, limitazioni ambientali.
4. **Esempio BRK-B corretto**: strategia vs azione, verifiche dati, Gate e rischio, senza ordini reali.
5. **Compatibilità e migrazioni**: schema, dashboard, storage, provider.
6. **Rischi residui e prossimi interventi**, ordinati per gravità.

### Comando operativo finale per l'agente

**Ispeziona il repository, traccia le dipendenze reali, implementa prima i controlli P0 con test deterministici, integra i moduli nella pipeline esistente e dimostra sul caso BRK-B che un giudizio `OVERWEIGHT` con trigger non soddisfatti produce `WAIT` e zero ordini. Poi affronta P1 senza compromettere provider, report e simulazione. Non sostituire la verifica con altro testo persuasivo generato da LLM.**
