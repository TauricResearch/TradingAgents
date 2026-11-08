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
