# TradingAgents v0.7.0 — Análise de Arquitetura

> Análise estática, somente leitura, do código em `main` (commit `e8f5503`). Nada foi executado: nem testes, nem CLI, nem chamadas de rede. As referências `arquivo:linha` apontam para a versão lida.

---

## 1. Mapa de módulos

### Visão geral

```
main.py / cli/            → pontos de entrada
tradingagents/
├── default_config.py     → config padrão + overrides TRADINGAGENTS_* do ambiente
├── graph/                → orquestração LangGraph (montagem, roteamento, checkpoint)
├── agents/               → nós LLM (analistas, pesquisadores, trader, risco, PM) + tools
├── dataflows/            → acesso a dados point-in-time, roteamento de vendors, cache
├── llm_clients/          → fábrica de clientes por provedor + tabela de capacidades
├── memory/               → log de decisões, liquidação (settlement) e reflexão
├── backtest.py           → varredura ticker × data e placar por rating
├── portfolio.py          → carteira opcional do usuário (posições e caixa)
└── reporting.py / report_html.py → relatórios em markdown e HTML
```

### `tradingagents/agents/` — os nós do grafo

| Arquivo | Responsabilidade |
|---|---|
| `state.py` | `AgentState` (estende `MessagesState`), `InvestDebateState`, `RiskDebateState`: o contrato de estado compartilhado entre os nós. |
| `tools.py` | As 11 ferramentas `@tool` que os analistas chamam. Cada uma recebe `trade_date` via `InjectedState` e limita a data pedida pelo modelo com `as_of`/`as_of_window` antes de chamar `route_to_vendor`. |
| `analysts/market_analyst.py` | Análise técnica: `get_stock_data`, `get_indicators`, `get_verified_market_snapshot`. |
| `analysts/news_analyst.py` | Notícias da empresa e macro: `get_news`, `get_global_news`, `get_macro_indicators` (FRED), `get_prediction_markets` (Polymarket). |
| `analysts/fundamentals_analyst.py` | Fundamentos: perfil, balanço, DRE, fluxo de caixa e insiders. |
| `analysts/sentiment_analyst.py` | **Não usa tools**: busca antes Yahoo News, StockTwits e Reddit, injeta tudo no prompt e devolve um `SentimentReport` estruturado. |
| `analysts/turn.py` | `take_turn`: um turno do analista com tools; depois de `max_tool_rounds`, `WRAP_UP` força o relatório sem tools. |
| `researchers/bull_researcher.py`, `bear_researcher.py` | Debate bull × bear sobre os 4 relatórios. |
| `managers/research_manager.py` | Julga o debate e produz um `ResearchPlan` (rating de 5 níveis + plano). Usa o LLM *deep*. |
| `trader/trader.py` | Transforma o plano em `TraderProposal` (Buy/Hold/Sell, entrada, stop e tamanho), ancorado no relatório técnico. |
| `risk_mgmt/*_debator.py` | Debate de risco entre os perfis agressivo, conservador e neutro. |
| `managers/portfolio_manager.py` | Decisão final (`PortfolioDecision`) e único consumidor de `past_context` (as lições da memória). Usa o LLM *deep*. |
| `schemas.py` | Schemas Pydantic (`ResearchPlan`, `TraderProposal`, `PortfolioDecision`, `SentimentReport`) e os renderizadores para markdown. |
| `structured.py` | `bind_structured` / `invoke_structured_or_freetext`: saída estruturada, com fallback para texto livre. |
| `rating.py` | Vocabulário de 5 níveis, parser determinístico `extract_rating` e sentinela `REVIEW`. |
| `context.py` | Identidade do instrumento (`resolve_instrument_identity`, `build_instrument_context`), instrução de idioma, marcadores de relatório ausente e de carteira. |
| `post_screen.py` | Triagem opcional dos posts sociais via API TypeSafe/Jev (só quando `TYPESAFE_API_KEY` está definida). |

### `tradingagents/graph/` — orquestração

| Arquivo | Responsabilidade |
|---|---|
| `trading_graph.py` | `TradingAgentsGraph`: fachada pública. Cria os LLMs, a memória e o grafo. Expõe `propagate`, `stream_run`, `record_decision`, `settle_pending(_all)`, checkpoint, `save_reports` e `run_settings`. |
| `setup.py` | `GraphSetup.setup_graph`: monta o `StateGraph`. Cada analista é um subgrafo próprio (`_analyst_graph`), e analistas e Memory Log rodam em paralelo. |
| `analyst_execution.py` | `ANALYST_NODE_SPECS`: chave → nome do nó, chave do relatório e tools. |
| `conditional_logic.py` | Roteadores dos debates (`should_continue_debate`, `should_continue_risk_analysis`), controlados por contador. |
| `propagation.py` | `Propagator.create_initial_state` (estado zero) e `get_graph_args` (`recursion_limit`, callbacks). |
| `checkpointer.py` | Um SQLite por ticker (`SqliteSaver`). `thread_id` = sha256(ticker:data:assinatura). |

### `tradingagents/dataflows/` — dados

| Arquivo | Responsabilidade |
|---|---|
| `date_window.py` | **Regras point-in-time**: `as_of`, `as_of_window`, `in_window`, `coverage_gap`, `is_historical` e `withhold_*`. |
| `router.py` | `route_to_vendor`: cadeia explícita de vendors por categoria ou tool, com fallback dirigido por exceções tipadas e sentinelas `DATA_UNAVAILABLE` / `NO_DATA_AVAILABLE`. |
| `errors.py` | Taxonomia `VendorError` → `NoMarketDataError`, `VendorUnavailableError`, `VendorNotConfiguredError`. |
| `config.py` | Config global mais um `ContextVar` com a config da execução (`run_config`, `run_config_context`, `get_config`). |
| `files.py` | `replace_file` (escrita atômica) e `locked` (lock entre processos, POSIX e Windows). |
| `net.py` | `get_scrubbed`: tira a API key das mensagens de erro HTTP. `vendor_reachable`. |
| `symbols.py` | `normalize_symbol` (XAUUSD→GC=F, BTCUSD→BTC-USD…) e `safe_ticker_component` (contra path traversal). |
| `vendors/yahoo/` | `ohlcv.py` (cache OHLCV, filtro anti look-ahead, guarda contra dado velho), `market.py` (OHLCV online, indicadores stockstats, `get_closes`), `snapshot.py` (snapshot determinístico), `news.py`, `fundamentals.py`, `common.py` (`yf_retry`). |
| `vendors/alpha_vantage/` | Preços ajustados, indicadores, notícias (`time_from`/`time_to`), fundamentos. |
| `vendors/sec_edgar.py` | Demonstrativos **como arquivados** (vintage por data de `filed`). |
| `vendors/fred.py` | Séries macro com vintage fixado (`realtime_start = realtime_end = as_of`). |
| `vendors/polymarket.py` | Odds ao vivo, retidas em execuções históricas. |
| `vendors/stocktwits.py`, `reddit.py` | Feeds sociais recentes, recortados para a janela da análise. |

### `tradingagents/llm_clients/` — provedores

| Arquivo | Responsabilidade |
|---|---|
| `factory.py` | `create_llm_client` (import lazy por provedor), `create_tier_client` (tiers *quick* e *deep*, cada um com provedor e endpoint próprios), `build_llm_kwargs` (temperature, retries, max_tokens, effort/thinking). |
| `openai_client.py` | Registro declarativo `OPENAI_COMPATIBLE_PROVIDERS` (`ProviderSpec`): OpenAI, xAI, DeepSeek, Qwen, GLM, MiniMax, OpenRouter, Ollama, ChatGPT-plan e endpoint genérico. |
| `anthropic_client.py`, `google_client.py`, `azure_client.py`, `bedrock_client.py` | Clientes nativos. |
| `capabilities.py` | Tabela por modelo: tool_choice, json_mode, json_schema, método de saída estruturada preferido e particularidades (ex.: DeepSeek exige devolver `reasoning_content`). |
| `base_client.py` | `BaseLLMClient` e `normalize_content` (junta os blocos de texto das respostas multi-bloco). |
| `model_catalog.py`, `validators.py`, `api_key_env.py` | Catálogo de modelos para a CLI, validação de nomes e variável de ambiente da key de cada provedor. |
| `chatgpt_auth.py` | OAuth/PKCE para usar o plano ChatGPT; tokens em `~/.tradingagents/chatgpt-auth.json`. |

### `tradingagents/memory/` — memória de decisões

| Arquivo | Responsabilidade |
|---|---|
| `log.py` | `TradingMemoryLog`: log markdown append-only, com entradas `pending` → resolvidas, locks e escrita atômica. |
| `settlement.py` | Mede retorno e alpha depois da janela de holding e dispara a reflexão. |
| `reflection.py` | `Reflector`: lição de 2 a 4 frases gerada pelo LLM *quick*. |

### `cli/` — interface de terminal (Typer + Rich)

| Arquivo | Responsabilidade |
|---|---|
| `main.py` | App Typer (`tradingagents` = `cli.main:app`). O callback `analyze` é o comando padrão; há também `backtest`, `login` e `logout`. |
| `run.py` | `run_analysis`: monta a config, faz streaming do grafo para a UI ao vivo, registra a decisão e salva relatórios. |
| `selections.py`, `prompts.py` | Perguntas interativas (ticker, data, analistas, profundidade, provedor e modelos), validação e key de API. |
| `display.py` | Layout ao vivo: log de mensagens, status dos agentes, painéis e tempos. |
| `stats_handler.py` | Callback LangChain que conta chamadas de LLM e de tools e tokens. |
| `prefs.py` | Guarda as respostas estáveis da última execução para usar como default. |
| `updates.py` | Checagem diária de nova versão em thread de fundo; desligável com `TRADINGAGENTS_NO_UPDATE_CHECK=1`. |

---

## 2. Fluxo de ponta a ponta (ticker → decisão)

### 2.1 Entrada

- **Programática**: `main.py` → `TradingAgentsGraph(debug=True, config=DEFAULT_CONFIG.copy())` → `ta.propagate("NVDA", "2026-09-01")`.
- **CLI**: `cli/main.py:analyze` → `cli/run.py:run_analysis` → `get_user_selections` → `_build_run_config` → `TradingAgentsGraph(...)` → `create_run_state` → `begin_checkpoint` → `stream_run` → `record_decision` → `clear_checkpoint_on_success` → `_offer_reports`/`save_reports`.

Os dois caminhos usam o mesmo `create_run_state`, `stream_run`/`invoke` e `record_decision`.

### 2.2 Construção (`trading_graph.py:TradingAgentsGraph.__init__`)

1. `set_config(config)` em `dataflows/config.py`.
2. `create_tier_client(config, "deep"|"quick").get_llm()` em `llm_clients/factory.py`. O *deep* atende Research Manager e Portfolio Manager. O *quick* atende analistas, pesquisadores, trader, debatedores de risco e o `Reflector`.
3. `TradingMemoryLog(config)`, `ConditionalLogic(max_debate_rounds, max_risk_discuss_rounds)` e a validação `2*max_tool_rounds+2 < max_recur_limit`.
4. `GraphSetup.setup_graph(selected_analysts, memory_node=self._memory_step)` em `graph/setup.py:109`, compilado em `self.graph`.

### 2.3 `propagate` (`trading_graph.py:167`)

1. `_validate_trade_date` (`:30`): exige `YYYY-MM-DD` canônico e **data ≤ hoje**.
2. `with run_config(self.config)`: põe a config da execução num `ContextVar`, que o LangGraph propaga para as chamadas de tool.
3. `checkpoint_scope`, que chama `begin_checkpoint`: se `checkpoint_enabled`, recompila com `SqliteSaver` e usa um `thread_id` derivado de `_run_signature` (analistas, profundidade, ativo, fingerprint da carteira e hash da config).
4. `_run_graph` (`:372`):
   - `create_run_state` (`:293`) → `resolve_instrument_context` → `agents/context.py:resolve_instrument_identity` (Yahoo `Ticker.info`, com `lru_cache`) → `build_instrument_context` (em data histórica injeta **só o nome**, sem setor nem indústria) → `Propagator.create_initial_state` (`propagation.py:13`).
   - `graph.invoke(...)`, ou `stream_run(...)` em modo debug.

### 2.4 Topologia do grafo (`graph/setup.py:157-185`)

```
            ┌─ Market Analyst (subgrafo: agent ⇄ tools → wrap_up) ─┐
            ├─ Sentiment Analyst (sem tools)                       ┤
START ──────┼─ News Analyst (subgrafo)                             ┼──► Bull Researcher ⇄ Bear Researcher
            ├─ Fundamentals Analyst (subgrafo)                     ┤          │ count ≥ 2·max_debate_rounds
            └─ Memory Log (_memory_step)                           ┘          ▼
                                                                     Research Manager (deep)
                                                                              ▼
                                                                           Trader
                                                                              ▼
                                         Aggressive → Conservative → Neutral → … (count ≥ 3·max_risk_rounds)
                                                                              ▼
                                                                  Portfolio Manager (deep) ──► END
```

- **Analistas** (`setup.py:_analyst_graph`, `:53`): cada um é um `StateGraph` com `output_schema={report_key: str}`. O histórico de mensagens fica privado e só o relatório volta ao estado pai, por isso os analistas rodam em paralelo sem conflito de escrita. O loop vai de `agent` (`take_turn` em `agents/analysts/turn.py:13`) para o `ToolNode` (`agents/tools.py`) e repete até `max_tool_rounds`; depois disso entra `wrap_up`, que invoca o modelo sem tools e com o histórico convertido em texto (`_as_text`).
- **Tools**: em `agents/tools.py`, cada tool aplica `as_of(curr_date, trade_date)` ou `as_of_window(...)` e chama `dataflows/router.py:route_to_vendor` (`:200`), que percorre a cadeia configurada (`default_config.py` → `data_vendors`/`tool_vendors`) até a implementação do vendor.
- **Sentiment** (`sentiment_analyst.py:47`): busca antes `get_news.func`, `fetch_stocktwits_messages` e `fetch_reddit_posts` na janela [T−7, T], com `jev_screen` opcional, e gera o relatório com `invoke_structured_or_freetext(SentimentReport)`.
- **Memory Log** (`trading_graph.py:_memory_step`, `:308`): roda junto com os analistas. Executa `settle_all_pending(wait=False)` e depois `memory_log.get_past_context(ticker, as_of=_memory_as_of(trade_date))`. Retorna `past_context` e `memory_note`, e uma falha aqui não derruba a execução.
- **Debate de pesquisa**: `bull_researcher.py:9` e `bear_researcher.py` acrescentam texto a `investment_debate_state` e incrementam `count`. `conditional_logic.py:should_continue_debate` (`:12`) alterna entre os dois pelo prefixo "Bull" e para em `count ≥ 2·rounds`.
- **Research Manager** (`research_manager.py:14`): `ResearchPlan` estruturado, com fallback para texto, vira `investment_plan`.
- **Trader** (`trader.py:20`): recebe `investment_plan`, o `market_report` (para ancorar entrada e stop) e `portfolio_context`, e produz `TraderProposal` em `trader_investment_plan`.
- **Debate de risco**: os três debatedores e `should_continue_risk_analysis` (`:23`) rodam até `count ≥ 3·rounds`.
- **Portfolio Manager** (`portfolio_manager.py`): prompt com o plano, a proposta, `past_context` e o histórico de risco → `invoke_structured(PortfolioDecision)`. `final_rating = decision.rating.value`. No fallback de texto, usa `parse_rating(texto)`, que devolve `REVIEW` se não houver rating legível.

### 2.5 Encerramento

- `record_decision` (`trading_graph.py:358`) faz duas coisas:
  - `_log_state` grava o JSON em `results_dir/<ticker>/TradingAgentsStrategy_logs/full_states_log_<data>.json`, junto com `run_settings` (allowlist, sem segredos).
  - `memory_log.store_decision(...)` acrescenta uma entrada **pending**.
- `clear_checkpoint_on_success` apaga o checkpoint.
- O retorno é `(final_state, run_rating(final_state))`, com o sinal em {Buy, Overweight, Hold, Underweight, Sell, REVIEW}.

---

## 3. Riscos de look-ahead / dados não point-in-time

### 3.1 Proteções já existentes (bem feitas)

| Mecanismo | Onde | O que garante |
|---|---|---|
| Clamp de data das tools | `agents/tools.py` + `date_window.py:as_of` (`:78`), `as_of_window` (`:91`) | O LLM não consegue pedir uma data depois de `trade_date`; se a janela inteira é futura, ela é deslocada mantendo o tamanho. |
| Filtro OHLCV | `vendors/yahoo/ohlcv.py:load_ohlcv`: `data[data["Date"] <= as_of_dt]` | O cache guarda 5 anos até hoje e serve só as linhas ≤ T. Datas são normalizadas por elemento (fuso e horário de verão). |
| Guarda contra dado velho | `ohlcv.py:_assert_ohlcv_not_stale` (`MAX_OHLCV_STALE_DAYS=10`) | Recusa frames cujo último candle está mais de 10 dias antes de T. |
| Candle parcial | `ohlcv.py:_cache_is_fresh` (TTL 900s) | Execução do dia atual rebaixa os dados depois de 15 min. Barras sem close no fim são descartadas. |
| Janela de itens datados | `date_window.py:in_window` (`:23`) | Intervalo semiaberto em UTC `[start, end+1d)`. Item **sem data** só entra se a janela chega ao presente. |
| "Indisponível" ≠ "ausente" | `date_window.py:coverage_gap` (`:44`) | Feeds que só servem itens recentes (Yahoo news, StockTwits, Reddit) retornam um placeholder em vez de "nenhuma notícia". |
| Perfil ao vivo retido | `withhold_live_profile` (`:108`), usado em `yahoo/fundamentals.py:get_fundamentals` e `alpha_vantage/fundamentals.py` | `Ticker.info`/`OVERVIEW` (market cap, múltiplos, TTM, setor) não aparecem em execução histórica. |
| Demonstrativos sem data de arquivamento | `withhold_undated_statements` (`:153`) | Yahoo e AV são retidos no histórico. Só a SEC EDGAR serve demonstrativos históricos. |
| Insiders sem data de disclosure | `withhold_undisclosed_trades` (`:134`) | Yahoo e AV retidos no histórico (o Form 4 sai até 2 dias úteis depois). |
| SEC as-filed | `vendors/sec_edgar.py:_as_of` (`:153`) | Usa `fact["filed"] <= as_of_date` e, por período, o arquivamento mais recente até T. Restatements contam a partir da data em que foram arquivados. Não soma tags nem deriva Q4. |
| FRED vintage | `vendors/fred.py:get_macro_data` (`:203`) | `realtime_start = realtime_end = min(as_of, hoje FRED)`, ou seja, o valor como era conhecido em T e não a revisão atual. |
| Polymarket | `vendors/polymarket.py:86` | Retido em execução histórica. |
| Alpha Vantage preços | `alpha_vantage/common.py:_filter_csv_by_date_range` | Recorte obrigatório e sem `try`: falha de parse levanta erro em vez de servir a série inteira. |
| Identidade do instrumento | `agents/context.py:build_instrument_context` (`:107`) | No histórico, só o nome atual, com aviso; setor, indústria e bolsa são omitidos. |
| Entrada na liquidação | `memory/settlement.py:fetch_returns` (`:52`) | Entrada no **primeiro fechamento depois de T**, porque a análise de T vê o close de T e as notícias até o fim do dia T (#1518). |
| Lições point-in-time | `memory/log.py:get_past_context(as_of)` (`:93`) + `trading_graph.py:_memory_as_of` | No histórico, só entram lições com `resolved ≤ T`. Entradas legadas sem `resolved` ficam de fora. |

### 3.2 Riscos residuais (em ordem de severidade)

1. **Memória paramétrica do LLM (alto)**. Nada no código impede que o modelo "saiba" o que aconteceu depois de T quando T é anterior ao knowledge cutoff dele. O prompt diz *"Today's date is {current_date}"* (ex.: `market_analyst.py`), mas isso é só instrução. É o maior viés de qualquer backtest com este sistema. O próprio `backtest.py:BacktestSummary.render` admite que os números são "indicativos". **Mitigação**: avaliar só datas posteriores ao cutoff do modelo ou fazer forward-testing.

2. **Reflexões escritas "agora" (médio)**. `settlement.py:settle_pending` chama `Reflector.reflect_on_final_decision` no momento da liquidação, em tempo real. O texto da lição é gerado por um LLM que pode conhecer eventos posteriores a `resolution_date`. O filtro `resolved ≤ T` controla *quais* lições entram, mas não *o que* o texto delas carrega.

3. **Preços ajustados retroativamente (médio-baixo)**. `ohlcv.py:load_ohlcv` usa `history(..., auto_adjust=True)`. `market.py:get_YFin_data_online` e `get_closes` usam o default do yfinance, que também ajusta. O AV usa `TIME_SERIES_DAILY_ADJUSTED`. Em execução histórica, os *níveis* de preço (entrada, stop, suportes, médias) refletem splits e dividendos posteriores a T e não batem com o que estava cotado na época. Retornos relativos quase não mudam, mas o `TraderProposal` com preços absolutos fica incomparável com o passado.

4. **Viés de sobrevivência e universo (médio)**.
   - O usuário escolhe tickers hoje, e o Yahoo raramente tem os deslistados (`run_backtest` só registra a falha).
   - `sec_edgar.py:cik_for` (`:135`) usa o `company_tickers.json` **atual**: um ticker reutilizado ou renomeado pode apontar para outro CIK.
   - `load_ohlcv` baixa só **5 anos a partir de hoje**. Datas mais antigas falham na guarda de dado velho, e as primeiras datas dessa janela ficam com SMA-200 sem aquecimento.

5. **Feeds de texto não arquivados (médio, viés de conjunto de informação)**. Yahoo news (`yahoo/news.py:get_news_yfinance`, só os N artigos mais recentes), StockTwits e Reddit servem apenas itens recentes. No histórico, viram "unavailable", o que não é vazamento, mas faz o backtest rodar com **menos informação** que a execução ao vivo. O caso mais sutil é `get_global_news_yfinance` (`yf.Search`, ranqueado por relevância **hoje**): os artigos passam pelo filtro `in_window`, mas a escolha de *quais* artigos antigos aparecem é feita no presente, o que é um viés de seleção. O `summary` de um artigo também pode ter sido editado depois de `pubDate`.

6. **Granularidade de data, não de horário (baixo)**. SEC `filed` é uma data: um 10-Q aceito às 17h de T conta como conhecido em T. As notícias entram até 23:59 UTC de T, o que nos EUA equivale a ~19-20h ET e inclui o after-hours. As duas coisas são **consistentes** com a convenção "análise depois do fechamento de T, entrada no close de T+1" (`fetch_returns`). Quem mudar a convenção de entrada (ex.: abertura de T+1 ou close de T) quebra essa garantia.

7. **"Hoje" definido pelo relógio local (baixo)**. `date_window.py:get_current_date` usa `date.today()`. `is_historical`, `_validate_trade_date` e as decisões de reter dados dependem do fuso da máquina, não do fuso da bolsa. Rodando de madrugada em UTC−3, "ontem" pode ser tratado como hoje e vice-versa, o que afeta se perfil ao vivo, Polymarket e insiders são servidos ou não. O FRED tem clamp próprio (`_fred_today`).

8. **Memória: ordem e poluição (baixo)**.
   - `get_past_context` ordena por **ordem de append** (`reversed(entries)`), não por data. Uma análise histórica rodada fora do backtest entra no log *live* e depois aparece como "mais recente" em execuções ao vivo.
   - O `run_backtest` evita isso usando um log próprio (`results_dir/backtest/<run_id>/trading_memory.md`).

9. **Medidas do backtest (baixo, de interpretação)**.
   - O alpha é gravado arredondado a 0,1 p.p. (`log.py:_resolved_tag` → `_alpha` em `backtest.py:65`).
   - Há uma amostra por célula, com LLM não determinístico.
   - O benchmark é comparado em moedas diferentes (cada série na sua).
   - O hit rate mede o sinal do **alpha**, não do retorno bruto (`backtest.py:summarize`).
   - Não há custos nem tamanho de posição: o `backtest.py` declara explicitamente que não simula carteira.

### 3.3 Testes relacionados (lidos, não executados)

`tests/test_fundamentals_lookahead.py`, `test_news_lookahead.py`, `test_social_lookahead.py`, `test_memory_pointintime.py`, `test_statement_knowledge_time.py`, `test_tool_date_enforcement.py`, `test_undated_tools_as_of.py`, `test_date_boundaries.py`, `test_ohlcv_latest_bar.py`, `test_yfinance_stale_ohlcv_guard.py`, `test_fred.py`, `test_sec_edgar.py` e `test_backtest.py` são o lugar certo para validar qualquer mudança nessas garantias.

---

## 4. Log de decisões e reflexão

### 4.1 Formato (`memory/log.py`)

Arquivo markdown append-only (padrão `~/.tradingagents/memory/trading_memory.md`). As entradas são separadas por `<!-- ENTRY_END -->`, um comentário HTML que não aparece em prosa de LLM.

```
[2026-09-01 | NVDA | Overweight | pending]

DECISION:
<final_trade_decision renderizado>
<!-- ENTRY_END -->
```

Depois da liquidação, a mesma entrada fica assim:

```
[2026-09-01 | NVDA | Overweight | +3.2% | +1.1% | 5d | resolved:2026-09-09]

DECISION:
...

REFLECTION:
<2-4 frases>
```

### 4.2 Ciclo de vida

| Etapa | Função | Detalhes |
|---|---|---|
| **Gravar** | `TradingMemoryLog.store_decision` (`log.py:32`), chamado por `TradingAgentsGraph.record_decision` | Sem LLM. Usa lock (`locked(path)` → arquivo `.lock`). É **idempotente**: se já existe qualquer entrada `[data \| ticker \|`, pending ou resolvida, não grava de novo, para não contar a mesma decisão duas vezes. O rating vem do `final_rating` tipado do PM, ou de `parse_rating`. |
| **Liquidar** | `_memory_step` → `settlement.settle_all_pending(wait=False)` → `settle_pending(ticker)` (`settlement.py:114`) | Uma passada por vez por log (`memory_log.settling()` → lock em `.settle`). Com `wait=False`, se outra execução já estiver liquidando, esta segue sem esperar. Liquida **todos os tickers**, não só o atual (#1445). |
| **Medir** | `fetch_returns` (`settlement.py:52`) | Busca closes de T até cerca de T + (h+1)·7/5 + 7 dias corridos. `stock.index > T` define a entrada no 1º close depois de T. **Exige a janela completa** (`len > holding_days`), senão a entrada continua pending (#1169). O benchmark vem de `resolve_benchmark` (`benchmark_ticker` explícito ou `benchmark_map` por sufixo: `.SA`→`^BVSP`, `""`→`SPY`) e é avaliado com `asof(entry)` e `asof(exit)`, o que alinha calendários diferentes (cripto × índice). `alpha = raw − bench_ret` e `resolution_date = data do exit`. |
| **Refletir** | `Reflector.reflect_on_final_decision` (`reflection.py:36`) | LLM *quick*. O prompt de sistema (`_system_prompt`) pede 2 a 4 frases sem markdown: (1) o que o alpha de h dias diz sobre a direção, avisando se a janela é curta demais; (2) qual parte da tese a janela apoia ou contradiz; (3) uma lição concreta. A entrada do modelo é só a decisão, o retorno bruto e o alpha. |
| **Persistir** | `update_with_outcome` (`log.py:134`) | Com lock, reescreve o arquivo inteiro via `.tmp` + `replace()` (atômico). Troca a tag e acrescenta `REFLECTION:`. Retorna `False` se outra passada já liquidou a entrada. Cada entrada é gravada assim que fica pronta, então uma interrupção preserva o progresso. `batch_update_with_outcomes` existe, mas o settlement não o usa. |
| **Rotacionar** | `_apply_rotation` (`log.py:273`) | Se `memory_log_max_entries` estiver definido, descarta as resolvidas mais antigas. As pendentes nunca são descartadas. |
| **Ler** | `get_past_context(ticker, n_same=5, n_cross=3, as_of)` (`log.py:93`) | Só entradas resolvidas e, no histórico, só com `resolved ≤ T`. Entrega até 5 do mesmo ticker (decisão e reflexão completas) e até 3 de outros tickers (só a reflexão, ou os primeiros 300 caracteres da decisão). Vai para `state["past_context"]`, que **só o Portfolio Manager** lê. |

### 4.3 Falhas

- Preço indisponível → `Settlement.failed` com motivo "prices unavailable"; a entrada continua pending.
- Falha do LLM na reflexão → `failed` com motivo "reflection failed"; a entrada continua pending.
- Exceção no `_memory_step` → `memory_note` aparece no relatório, e a execução continua com as lições que já estavam no log.
- Backtest: depois da varredura, `run_backtest` chama `graph.settle_pending(ticker)` para cada ticker, porque a última célula de cada um ficaria pending.

---

## 5. Ideias reaproveitáveis para um sistema quant em Python

| # | Ideia | Arquivo de origem |
|---|---|---|
| 1 | **Clamp de datas pedidas** (`as_of`, `as_of_window`): toda leitura recebe o "relógio da simulação" e nunca passa dele, mesmo quando quem pede (usuário, LLM ou estratégia) erra a data. | `tradingagents/dataflows/date_window.py` |
| 2 | **Data da simulação injetada, não pedida**: o `trade_date` chega à função de dados pelo estado (`InjectedState`), não como argumento livre. Em um engine quant, isso equivale a um `Clock` injetado no data handler. | `tradingagents/agents/tools.py` |
| 3 | **Janela semiaberta em UTC + política para item sem data** (`in_window`): normaliza fuso e só aceita item sem timestamp se a janela chega ao presente. | `tradingagents/dataflows/date_window.py` |
| 4 | **Distinguir "fonte não observou" de "não aconteceu"** (`coverage_gap`): fundamental para dados alternativos com cobertura irregular. | `tradingagents/dataflows/date_window.py` |
| 5 | **Reter snapshots sem vintage em modo histórico** (`withhold_live_profile`, `withhold_undated_statements`, `withhold_undisclosed_trades`): uma regra única, aplicada por todos os vendors. | `tradingagents/dataflows/date_window.py` |
| 6 | **Fundamentos as-filed via XBRL da SEC**: escolhe por data de `filed`, pega o arquivamento mais recente por (período, duração), classifica a duração (trimestre 60-115 d, ano 300-400 d, YTD), não soma tags nem deriva Q4. | `tradingagents/dataflows/vendors/sec_edgar.py` (`_as_of`, `_statement`) |
| 7 | **Vintage do FRED/ALFRED** com `realtime_start = realtime_end = as_of`. | `tradingagents/dataflows/vendors/fred.py` |
| 8 | **Cache OHLCV com frescor diário + TTL para candle parcial + filtro ≤ as_of + guarda de dado velho.** | `tradingagents/dataflows/vendors/yahoo/ohlcv.py` (`load_ohlcv`, `_cache_is_fresh`, `_assert_ohlcv_not_stale`) |
| 9 | **Roteador de vendors com cadeia explícita** (sem fallback silencioso para fontes não escolhidas) e **taxonomia de erros por reação** (não-dados / indisponível / não configurado), separando categorias essenciais de opcionais. | `tradingagents/dataflows/router.py`, `tradingagents/dataflows/errors.py` |
| 10 | **Config por execução em `ContextVar`**: várias simulações no mesmo processo, cada uma com seus vendors e parâmetros, sem estado global compartilhado. | `tradingagents/dataflows/config.py` |
| 11 | **Overrides por variável de ambiente com coerção pelo tipo do default e falha explícita** (`treu` dá erro em vez de virar `False`). | `tradingagents/default_config.py` (`_ENV_OVERRIDES`, `_coerce`) |
| 12 | **Escrita atômica + lock entre processos** (POSIX `fcntl` / Windows `msvcrt`) para caches e ledgers compartilhados. | `tradingagents/dataflows/files.py` |
| 13 | **Ledger de sinais append-only com estados pending→resolved e `resolution_date`**: registra o sinal quando é gerado e o resultado quando é conhecido, e permite filtrar o que "já se sabia" em T. Idempotente por (data, ticker). | `tradingagents/memory/log.py` |
| 14 | **Liquidação de sinais**: entrada no 1º close depois do sinal, exigência de janela completa, benchmark regional por sufixo e alinhamento `asof` entre calendários diferentes. | `tradingagents/memory/settlement.py`, `benchmark_map` em `tradingagents/default_config.py` |
| 15 | **Avaliação de sinais por classe de rating**: hit rate direcional sobre o alpha, Hold sem direção, `REVIEW` fora do placar, grade resumível (pula células feitas) e log isolado por `run_id`. Separa explicitamente avaliação de sinal de simulação de carteira. | `tradingagents/backtest.py` |
| 16 | **Assinatura de execução** (hash da config relevante + fingerprint da carteira) para invalidar checkpoints e caches e garantir reprodutibilidade. | `tradingagents/graph/trading_graph.py` (`_run_signature`), `tradingagents/graph/checkpointer.py` |
| 17 | **Proveniência por allowlist** (`run_settings`): grava versão, modelos e vendors junto com cada resultado, sem vazar endpoints nem keys. | `tradingagents/graph/trading_graph.py` |
| 18 | **Sentinela de sinal ilegível** (`REVIEW`) em vez de assumir Hold, mais um parser determinístico e tolerante (NFKC, markdown) que exige concordância entre rótulos. | `tradingagents/agents/rating.py` |
| 19 | **Saída estruturada com fallback** (Pydantic → texto), útil para qualquer componente que consuma LLM. | `tradingagents/agents/structured.py`, `tradingagents/agents/schemas.py` |
| 20 | **Snapshot determinístico como "fonte da verdade"** para números (último candle ≤ T, indicadores fixos), separado da narrativa. | `tradingagents/dataflows/vendors/yahoo/snapshot.py` |
| 21 | **Sentinelas textuais instrutivas** (`DATA_UNAVAILABLE`, `NO_DATA_AVAILABLE`) para que o consumidor (humano ou LLM) não preencha lacunas com valores inventados. | `tradingagents/dataflows/router.py` |
| 22 | **Remoção da API key das exceções HTTP** (key em query string). | `tradingagents/dataflows/net.py` (`get_scrubbed`) |
| 23 | **Normalização de símbolos** (broker/MT5 → Yahoo) e **componente de path seguro** para tickers. | `tradingagents/dataflows/symbols.py` |
| 24 | **Retry com backoff exponencial** específico para rate limit de vendor. | `tradingagents/dataflows/vendors/yahoo/common.py` (`yf_retry`) |
| 25 | **Contexto de carteira com três estados** (sem informação / carteira zerada / com posição) e fingerprint. Evita tratar "não informado" como "zerado". | `tradingagents/portfolio.py` |
| 26 | **Tabela declarativa de capacidades por modelo/provedor**: as particularidades de cada provedor ficam em dados, não em cadeias de `if`. | `tradingagents/llm_clients/capabilities.py`, `ProviderSpec` em `tradingagents/llm_clients/openai_client.py` |
| 27 | **Execução paralela com estado isolado** (subgrafo por analista, com `output_schema` só do relatório) e orçamento de iterações (`max_tool_rounds` + `wrap_up`). | `tradingagents/graph/setup.py` |
