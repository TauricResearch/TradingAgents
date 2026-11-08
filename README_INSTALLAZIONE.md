# TradingAgents — pacchetto di governance AI e affidabilità

Questo archivio contiene file Markdown **già pronti** da copiare nel tuo repository TradingAgents.

## Contenuto

- `AGENTS.md`: regole per Copilot/Codex/Claude e workflow Git.
- `.github/copilot-instructions.md`: istruzioni per GitHub Copilot.
- `docs/specs/TRADINGAGENTS_RELIABILITY_CONTRACT.md`: contratto tecnico con validazioni, rischio, execution gate e test.
- `CHANGELOG.md`: registro delle modifiche effettivamente implementate.
- `SETUP_TRADINGAGENTS_AI.md`: configurazione iniziale passo-passo.
- `docs/architecture.md`: scheletro per descrivere l'architettura reale.
- `docs/decisions/README.md`: guida per registrare decisioni architetturali.

**Branch protetto di integrazione: `custom` (non `main`).** Tutti i nuovi branch devono partire da `custom`; tutte le Pull Request devono puntare a `custom`.

## Installazione

1. Estrai l'archivio **fuori** dal repository e controlla i file.
2. Copia il *contenuto* della cartella `TradingAgents_AI_Kit/` nella root del tuo repository, rispettando la struttura.
3. **Non sovrascrivere** `AGENTS.md`, `CHANGELOG.md` o altri file già esistenti senza confrontare e integrare le modifiche.
4. Apri VS Code nella root del repository e avvia GitHub Copilot in modalità Agent.
5. Fai leggere all'agente `AGENTS.md` e il contratto. Parti dalla **Fase 0 — Baseline** su branch dedicato.
6. Configura GitHub Actions e protezione di `custom` in base ai test e ai permessi effettivi del repository; assicurati che eventuali trigger `pull_request` usino `branches: [custom]`.

## Prompt rapido

> Leggi `AGENTS.md` e `docs/specs/TRADINGAGENTS_RELIABILITY_CONTRACT.md`. Ispeziona il repository reale. Parti da `custom` e implementa solo la Fase 0 (baseline e regressioni) su un branch dedicato; crea e verifica i test, aggiorna `CHANGELOG.md`, prepara commit e PR senza fare merge su `custom`. Mantieni esclusivamente il paper trading. Riporta i limiti degli strumenti e gli eventuali test non eseguiti.

## Nota

Il contratto è una **specifica di evoluzione**, non una dichiarazione che le funzionalità siano già state implementate. Non è inclusa una pipeline CI eseguibile perché linguaggio, dipendenze e comandi reali del repository non sono stati ispezionati.
