# TradingAgents — Guida rapida per evolvere il progetto con Git e AI

## Obiettivo

L'applicazione esistente rimane su GitHub. GitHub Copilot Agent, Codex o Claude Code sviluppano le evoluzioni in branch dedicati, eseguono test e preparano Pull Request. L'utente decide quando integrare il codice in `custom`.

> **Branch di integrazione del repository: `custom`.** Tutti i branch di lavoro partono da `custom` e tutte le Pull Request devono puntare a `custom`. Non cambiare automaticamente il branch predefinito di GitHub.

## 1. Preparare la struttura (senza perdere file esistenti)

```text
TradingAgents/
├── AGENTS.md
├── README.md
├── CHANGELOG.md                 # Registro delle modifiche, da aggiornare in ogni PR
├── .env.example
├── .gitignore
├── .github/
│   ├── copilot-instructions.md     # Facoltativo: rimanda ad AGENTS.md
│   └── workflows/
│       └── ci.yml               # Da adattare al progetto effettivo
├── docs/
│   ├── architecture.md           # Facoltativo all'inizio
│   ├── decisions/
│   └── specs/
│       └── TRADINGAGENTS_RELIABILITY_CONTRACT.md
├── src/                           # O le directory esistenti
└── tests/                         # O il percorso già usato dal progetto
```

Non creare o rinominare directory applicative senza prima ispezionare il repository. Se `AGENTS.md` esiste già, integra le nuove regole anziché sostituirlo.

## 2. Cosa fanno i due documenti

- `AGENTS.md`: stabilisce **come deve operare l'AI**: workflow Git, branch automatici, controlli, test, autorizzazioni, sicurezza e ordine delle fasi.
- `docs/specs/TRADINGAGENTS_RELIABILITY_CONTRACT.md`: stabilisce **che cosa deve realizzare l'AI**: Data Validator, Fact Checker, Risk Engine, Execution Gate, decisioni strutturate, audit e test di regressione.

In VS Code con GitHub Copilot puoi aggiungere facoltativamente `.github/copilot-instructions.md` con un semplice richiamo a `AGENTS.md` e al contratto, senza duplicare tutte le regole.

Il contratto è una specifica completa, **non un ordine di realizzare tutte le funzioni in una sola sessione o commit**.

## 3. Preparare Git una sola volta

Prima dei nuovi lavori:

```bash
git status
git branch -vv
git remote -v
```

Verificare che non esistano modifiche locali da salvare. Solo con working tree pulito:

```bash
git switch custom
git pull --ff-only
# Se la versione corrente è verificata e funzionante:
git tag -a pre-reliability-2026-11-08 -m "Baseline before reliability improvements"
git push origin pre-reliability-2026-11-08
```

Non ripetere la creazione del tag se esiste già; non etichettare come "funzionante" una versione non testata. Il branch scelto per questo progetto è `custom`: se non esiste, interrompi e verifica, senza ripiegare automaticamente su altri branch.

## 4. Abilitare controlli GitHub

In GitHub creare regole di protezione specifiche per il branch `custom`, richiedere che le modifiche passino da Pull Request e che i test automatici siano verdi prima del merge. Creare un workflow GitHub Actions coerente con il linguaggio e il sistema di test reali del repository. Mantenere il merge manuale.

## 5. Ordine dei lavori

1. **Fase 0 — Baseline:** test ripetibili e report BRK-B come fixture.
2. **Fase 1 — Data Validation:** fonte, disponibilità, timestamp e riconciliazione dati.
3. **Fase 2 — Risk Engine:** stop, sizing, slippage/gap, budget di rischio.
4. **Fase 3 — Execution Gate:** blocco degli ordini non validi e idempotenza.
5. **Fase 4 — Portfolio Decision:** separare `OVERWEIGHT`/`BUY` dal comando `WAIT`/`EXECUTE`.
6. **Fase 5 — Fact Checker e Debate:** verifica delle tesi e riduzione delle ripetizioni.
7. **Fasi successive:** audit, interfaccia, monitoraggio e backtesting out-of-sample.

Per ciascuna: partire da `custom` → nuovo branch → implementazione → test → aggiornamento di `CHANGELOG.md` con le sole modifiche realizzate → commit → push/PR → revisione → merge → aggiornamento `custom` → fase successiva.

## 6. Prompt iniziale pronto per GitHub Copilot Agent

> Leggi `AGENTS.md` e `docs/specs/TRADINGAGENTS_RELIABILITY_CONTRACT.md`.
>
> Ispeziona prima di tutto il repository e verifica lo stato Git. Implementa **soltanto la Fase 0: baseline e regressioni**, creando automaticamente il branch `test/reliability-baseline` se l'ambiente lo consente.
>
> Raccogli i test attuali, aggiungi fixture deterministicamente riproducibili per le criticità del report BRK-B dell'8 novembre 2026, esegui i test e documenta i risultati.
>
> Procedi autonomamente per le operazioni ordinarie e non chiedere conferme ripetitive. Non toccare `custom` direttamente, non eseguire operazioni distruttive, non abilitare trading reale e non accorpare tutte le fasi in un solo intervento.
>
> Quando possibile, crea commit, pubblica il branch e apri una Pull Request con **base `custom`**, senza fare merge. Verifica la destinazione prima di pubblicare. Se mancano autorizzazioni, indica cosa resta da fare manualmente.

## 7. Come proseguire

Dopo il merge della Fase 0, chiedere all'agente: «Implementa soltanto la Fase 1 del contratto seguendo `AGENTS.md`, creando un nuovo branch e una PR; conserva i test e le funzionalità precedenti».

Ripetere per ogni fase. Non serve scrivere un nuovo prompt lungo ogni volta: `AGENTS.md` resta permanente, il contratto resta la specifica e il prompt nomina solo la fase.

## 8. Cosa non automatizzare completamente

- Merge su `custom` e rilascio di versioni pubbliche.
- Modifiche a credenziali, permessi, branch protection o segreti.
- Qualsiasi attivazione del trading reale.
- Comandi Git distruttivi (`reset --hard`, `push --force`, cancellazione di branch condivisi).

L'autonomia dell'AI dipende dagli strumenti e dai permessi realmente disponibili in VS Code/GitHub; scrivere istruzioni in `AGENTS.md` non concede di per sé alcun privilegio.
