# Architettura TradingAgents — stato da verificare

> **Stato:** documento iniziale. Questa descrizione deve essere completata dopo l'ispezione del repository reale. Non costituisce una descrizione certificata dell'implementazione attuale.

## 1. Obiettivo

Descrivere l'architettura **effettiva** dell'applicazione esistente e i punti di integrazione delle evoluzioni di affidabilità specificate in [`specs/TRADINGAGENTS_RELIABILITY_CONTRACT.md`](specs/TRADINGAGENTS_RELIABILITY_CONTRACT.md).

## 2. Inventario dell'applicazione

Compilare sulla base del codice, senza ipotesi non confermate:

| Area | Percorso/modulo reale | Responsabilità | Test esistenti | Note |
|---|---|---|---|---|
| Entrypoint | Da verificare | Avvio e orchestrazione | Da verificare | |
| Agenti e modelli LLM | Da verificare | Analisi, proposta e dibattito | Da verificare | |
| Provider dati | Da verificare | Quotazioni, bilanci e news | Da verificare | |
| Portfolio/ordini | Da verificare | Simulazione e stato ordini | Da verificare | Solo paper trading |
| UI e report | Da verificare | Visualizzazione di analisi e decisioni | Da verificare | |
| Persistenza | Da verificare | Storico, audit e configurazioni | Da verificare | |
| Test/CI | Da verificare | Validazione e regressioni | Da verificare | |

## 3. Flusso logico target (non ancora implementato)

```text
Dati di mercato / financials / news
          |
   Provenance + DataValidator
          |
  Analisti LLM + FactChecker
          |
  Research / Debate / Portfolio Proposal
          |
   Decision schema validation
          |
    RiskEngine deterministico
          |
     ExecutionGate
          |
 Solo PaperTradingAdapter / WAIT / BLOCK
          |
 Audit Trail + Report + Dashboard
```

Le decisioni `BUY` e `OVERWEIGHT` degli agenti non autorizzano l'esecuzione di ordini. Qualsiasi ordine simulato richiede il passaggio esplicito da RiskEngine ed ExecutionGate.
## 3.1 Instrument Profiler (implementato)

`tradingagents/dataflows/instrument_profiler.py` classifica qualsiasi strumento **dai dati del vendor**, senza tabelle per-ticker, così che Data Validator, Fact Checker, Risk Engine ed Execution Gate si comportino in modo uniforme su qualunque mercato:

- **Tipo strumento** (`quoteType` del vendor, con fallback strutturali: suffisso `=X` → forex, prefisso `^` → indice, base crypto nota → crypto). Tipo non riconosciuto → `UNKNOWN`, mai un'ipotesi.
- **Valute**: valuta di quotazione (`currency`) e di rendicontazione (`financialCurrency`). Quotazioni in unità minori (GBp a Londra) ricevono un fattore di conversione verso l'unità principale (GBP).
- **Classi azionarie**: rilevate **strutturalmente** dal suffisso del ticker (`BRK-B` → root `BRK`, classe `B`); solo un separatore esplicito conta — una lettera finale nuda non è un suffisso (`NVDA` è NVIDIA, non `NVD` classe `A`). I fratelli di classe sono candidati strutturali, da validare contro il vendor prima d'essere trattati come reali.
- **Qualità dei dati**: `COMPLETE` / `PARTIAL` / `UNKNOWN` — il segnale fail-closed per i chiamanti.

Integrazioni: `validator.check_ticker_identity` accetta un profilo (la classe-sorella servita dal vendor è un errore; senza profilo, una differenza di stringa resta un warning di normalizzazione); `validator.validate_currency_consistency` usa il profilo per risolvere le unità minori. Casi di test: BRK-B (dual-class USA), AAPL e NVDA (single-class USA), ENI.MI (Milano, EUR), più GBp, crypto e indici — tutte le aspettative vengono dal payload vendor simulato, non da regole per-ticker.
## 4. Invarianti di sicurezza

1. Istruzioni e configurazioni esistenti non vengono sovrascritte arbitrariamente.
2. Nessuna connessione o ordine su conto reale.
3. In caso di dati invalidi o non aggiornati, il percorso di esecuzione fallisce in modo sicuro (`WAIT`/`BLOCK`).
4. Nessun ordine duplicato a seguito di retry.
5. Ogni decisione è riconducibile a snapshot, fonti, validazioni e configurazione.

## 5. Lavori di documentazione da eseguire nella fase 0

- [ ] Identificare le directory e i package realmente presenti.
- [ ] Descrivere i diagrammi di componenti e di sequenza a partire dal codice.
- [ ] Elencare ingressi, uscite, schemi dati e confini di fiducia.
- [ ] Documentare i punti di integrazione del contratto e i rischi di regressione.
- [ ] Aggiornare le tabelle "Da verificare" con riscontri dai file effettivi.
