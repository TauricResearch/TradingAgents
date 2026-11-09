# TradingAgents — Token Optimization & Verified Analyst Context

## OBIETTIVO PRINCIPALE
Ridurre il costo di ogni run TradingAgents sostituendo il dato grezzo che gli
agenti ricevono con metriche già calcolate e verificate dal Financial Math
Engine, senza cambiare il comportamento corretto del sistema.

**Principio architetturale non negoziabile:**

- I provider forniscono dati.
- Il codice normalizza e valida i dati.
- Il Financial Math Engine esegue i calcoli.
- Gli agenti AI interpretano risultati già verificati.
- Il Portfolio Manager propone decisioni.
- L'Execution Gate controlla e autorizza gli eventuali ordini simulati.

L'obiettivo è vietare che un analista ricostruisca o interpreti direttamente
uno statement grezzo, una serie storica o un insieme di notizie: il modello
deve vedere il dato nella forma più compatta e verificata possibile.

## 1. AUDIT INIZIALE DEL REPOSITORY
Prima di scrivere codice:

1. Leggi `AGENTS.md` e i documenti tecnici esistenti.
2. Individua dove gli statement finanziari (bilanci, conto economico, cash
   flow) diventano parte del prompt degli analisti.
3. Individua dove gli input di notizie, prezzi storici e post social vengono
   passati ai rispettivi analisti.
4. Mappa quanti token ogni singolo agente ingerisce per run e per turno.
5. Identifica dove i report prodotti da un agente vengono concatenati nel
   prompt del successivo (Research Manager, debaters, Portfolio Manager).
6. Reutilizza i componenti esistenti (Financial Math Engine, validatori,
   dataflows) invece di crearne di nuovi.

Produci una mappa delle responsabilità, distinguendo:

- Dato grezzo restituito dai vendor.
- Dato che entra nel prompt oggi.
- Metrica computabile da quel dato.
- Report prodotto dall'agente.
- Contesto che il report successivo davvero usa.

Per ogni singola area individua il punto di trasformazione corretto.

## 2. ARCHITETTURA DEL LAYER "VERIFIED CONTEXT"
Implementa un layer di normalizzazione che intercetti l'uscita dei tool prima
che raggiunga il prompt LLM.

### A. Financial Statement Summarizer
Per ogni statement (bilancio, conto economico, cash flow):

- Calcola le metriche pertinenti con il Financial Math Engine
  (`math/valuation.py`, `math/precision.py`).
- Passa al modello solo il `MetricRecord.summary()` delle metriche verificate.
- Scarta il testo grezzo una volta calcolate le metriche: non deve sopravvivere
  nel contesto della conversazione.
- Quando una metrica è non computabile, il summary lo dice esplicitamente
  (`NOT_COMPUTABLE`), non un valore fittizio.

### B. Prices & Technical Summarizer
Per OHLCV e indicatori:

- Calcola SMA, EMA, VWMA, RSI, MACD, ATR, Bollinger nel Technical Math Engine.
- Passa al modello solo i valori recenti e i livelli rilevanti, non la serie
  completa, a meno che il task non richieda esplicitamente una struttura
  temporale estesa.
- Distingui chiaramente i punti dato (close, high, low) dalle metriche derivate.

### C. News & Social Summarizer
Per articoli e post:

- Riduci ciascun item a: titolo, data, fonte, rilevanza, entità/ticker
  estratti, sentiment se già dispo­nibile, e un numero contenuto di parole chiave.
- Non passare più di N item per messaggio (soglia configurabile), ordinati per
  rilevanza decrescente.
- Le notizie scartate per irrilevanza non devono apparire nel contesto di
  nessun turno successivo.

### D. Report-to-Report Compression
Nel passaggio tra agenti:

- L'output di un analista deve poter essere sintetizzato prima di entrare nel
  prompt del manager sinergico, mantenendo solo decisioni, livelli e metriche.
- Debate history non deve superare un cap: riassumi i round precedenti in un
  blocco compatto, preservando solo le conclusioni e i livelli concordati.
- Regole per il riassunto deterministico e non LLM quando il contenuto è
  strutturato; altrimenti un passaggio di consolidamento LLM, una sola volta.

## 3. TIPI DI DATO E CONFINE
Non è una compressione qualsiasi: è una traduzione da un formato grezzo a uno
verificato.

Requisiti:

- Ogni metrica passata a un LLM deve portare il suo `MetricRecord`: formula,
  operandi, periodo, status (VERIFIED / REFUSED / NOT_COMPUTABLE).
- Gli agenti non devono poter distinguere un contesto sintetico da uno grezzo
  in modo silenzioso: il prompt indica solo che i numeri sono già verificati.
- Il testo grezzo non viene buttato solo quando una compressione verificata non
  esiste ancora: in quel caso il testo passa invariato, ma il layer annota
  l'obiettivo futuro, non lo inventa.
- Non ridurre mai il contesto sotto il minimo necessario a preservare la
  correttezza: sicurezza prima di risparmio.

## 4. TOKEN BUDGET ENFORCEMENT
Introduci limiti espliciti osservabili:

- Ogni analista ha un budget massimo di token in input per run, stabile e
  configurabile.
- Il sistema misura e registra per ogni agente: token in, token out, run_id,
  componente (fundamentals/news/technical/debate/manager).
- Se un messaggio supera il budget, il summarizer taglia ulteriormente, non
  lascia passare il testo: fail-safe, non warning.
- Le misure sono scritte in un log strutturato analizzabile offline.

## 5. CONFIGURAZIONE DEI TIERS E DEI ROUND
Estendi `default_config.py` in modo esplicito:

- `deep_think_llm` e `quick_think_llm` sono già presenti: assegnali per agente,
  non globali. Gli analisti di estrazione (fundamentals, market, social) non
  usano il tier deep di default.
- `max_risk_discuss_rounds`, `max_debate_rounds`: applica il minimo sensato,
  e documenta come ogni round aggiuntivo cambia il costo totale della run.
- Cap esplicito `max_output_tokens` per ciascun agente, diverso per tier.

## 6. METRICHE E VERIFICA
Per dimostrare l'effetto:

- Salva prima/dopo i token in/out di una run identica sullo stesso ticker e
  stessa data, e calcola la riduzione percentuale.
- Assicura che la correttazza resti: il Financial Math Engine continua a
  rifiutare un P/B errato e uno stop sbagliato anche coi prompt sintetici.
- Verifica che un agente non possa più accedere al testo grezzo originale una
  volta introdotto il summarizer (anche in error handling: non "fallisce" e
  poi passa il grezzo).

## 7. TEST AUTOMATICI OBBLIGATORI
Crea test `pytest` che verifichino:

1. Uno statement completo viene sostituito dal summary, e il summary contiene
   solo metriche verificate.
2. La metrica calcolata dallo statement riepilogato coincide con quella
   calcolata direttamente dal dato originale (nessuna perdita di significato).
3. Il riassunto di notizie mantiene titolo, data e rilevanza e scarta il corpo.
4. Il superamento del budget produce troncamento, non passaggio invariato.
5. Un report sintetizzato contiene ancora tutte le decisioni numeriche del
   report originale.
6. L'Execution Gate e il Financial Math Engine si comportano identicamente
   prima e dopo l'introduzione del layer.
7. Un fallback che non produce il summary non propaga silenziosamente il testo
   grezzo: fallisce apertamente o è marcato NON_VERIFIED.

## 8. INTEGRAZIONE CON IL FINANCIAL MATH ENGINE
Riusa direttamente, non reimplementare:

- `tradingagents/dataflows/math/precision.py` per unità e conversioni.
- `tradingagents/dataflows/math/valuation.py` per le metriche di valutazione.
- `tradingagents/dataflows/math/technical.py` per gli indicatori.
- `tradingagents/dataflows/math/metric_record.py` e `registry.py` per
  trasportare il contesto verificato.

La traduzione da statement a metriche vive nel dataflows, non in prompt.

## 9. GIT E WORKFLOW AUTONOMO
Lavora sul repository esistente.

- Base: `origin/custom`.
- Crea feature branch `feature/analyst-context-summarizer`.
- Non modificare direttamente `custom`.
- Non effettuare merge automatici.
- Non sovrascrivere modifiche utente.
- Scrivi test che riproducano prima lo stato attuale.
- Implementa il layer.
- Esegui l'intera suite di test pertinente.
- Aggiungi i regression test alla GitHub Actions CI.
- Aggiorna `CHANGELOG.md` e documentazione.
- Crea commit logici.
- Esegui push e apri una PR verso `custom` quando i permessi lo consentono.
- Mantieni esclusivamente il paper trading.
Procedi autonomamente sulle normali operazioni consentite senza interrompere
il lavoro per conferme non necessarie.

## 10. DEFINITION OF DONE
Il lavoro è completato soltanto se:

- Nessun agente riceve uno statement finanziario grezzo se le metriche
  pertinenti sono state calcolate.
- I report che passano da un agente a un altro sono sintetizzati secondo le
  regole, non concatenati per intero.
- I token consumati per run sono misurabili e ridotti rispetto alla baseline
  precedente, e la documentazione riporta il delta.
- La correttezza è invariata: i test del Financial Math Engine e del gate
  passano tutti.
- I token budget per agente sono configurabili e osservabili in un log
  strutturato.
- Le storie delle dispute non crescono libere: ogni dialogo ha un cap.
- Tutti i test di regressione passano.
- La CI esegue la suite token-optimization.
- Il Financial Math Engine continua a rifiutare il P/B errato e lo stop
  sbagliato, sempre.

## 11. REPORT FINALE RICHIESTO
Alla fine restituisci:

1. Moduli realizzati e punti di trasformazione introdotti.
2. Mappa del prima/dopo per ogni analista (token, contenuto).
3. Formule e regole usate per la normalizzazione di statement, prezzi e
   notizie.
4. Configurazioni aggiunte e dove.
5. Test PASS/FAIL con relativi comandi.
6. Prova che la correttezza è preservata (P/B e stop ancora rifiutati).
7. Misura del token budget e dove è osservabile.
8. Eventuali limitazioni residue.
9. Commit SHA.
10. Link alla Pull Request verso `custom`.
Non fermarti alla progettazione: implementa, testa, e misura il risparmio reale.

**Regola finale: il modello deve interpretare risultati già verificati, non
ricostruire pure forme grezze. Meno contesto, più verità, zero numeri
inventati.**
