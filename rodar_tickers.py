#!/usr/bin/env python3
"""Roda a análise para uma lista de tickers e imprime uma saída consolidada.

Uso:
    export OPENAI_API_KEY=...            # ou ANTHROPIC_API_KEY / GOOGLE_API_KEY
    python rodar_tickers.py AMBP3.SA SIMH3.SA
    python rodar_tickers.py AMBP3.SA SIMH3.SA --data 2026-08-21

Para papel de B3 o sufixo `.SA` e obrigatorio (AMBP3 puro nao existe no Yahoo).
O script avisa e corrige automaticamente se voce esquecer.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import time
from datetime import date

# Papeis de B3 seguem <4 letras><1-2 digitos>: PETR4, AMBP3, SIMH3, TAEE11.
_B3_RE = re.compile(r"^[A-Z]{4}\d{1,2}$")


def normalizar(ticker: str) -> str:
    """Acrescenta o sufixo .SA quando o ticker tem cara de papel de B3."""
    t = ticker.strip().upper()
    if _B3_RE.match(t):
        print(f"  aviso: '{t}' parece papel de B3 sem sufixo — usando '{t}.SA'")
        return f"{t}.SA"
    return t


def campo(texto: str, rotulo: str) -> str | None:
    """Extrai '**Rotulo**: valor' do markdown que os agentes produzem."""
    m = re.search(rf"\*\*{re.escape(rotulo)}\*\*:\s*(.+)", texto or "")
    return m.group(1).strip() if m else None


def main() -> int:
    ap = argparse.ArgumentParser(description="Analise TradingAgents para varios tickers")
    ap.add_argument("tickers", nargs="+", help="ex.: AMBP3.SA SIMH3.SA")
    ap.add_argument("--data", default=str(date.today()), help="data da analise (AAAA-MM-DD)")
    ap.add_argument("--rapido", action="store_true",
                    help="so o analista de mercado — mais barato e mais rapido")
    ap.add_argument("--salvar", action="store_true", help="gravar a arvore de relatorios em disco")
    args = ap.parse_args()

    from tradingagents.default_config import DEFAULT_CONFIG
    from tradingagents.graph.trading_graph import TradingAgentsGraph

    config = DEFAULT_CONFIG.copy()
    analistas = ("market",) if args.rapido else ("market", "social", "news", "fundamentals")

    print(f"\nProvedor : {config['llm_provider']}")
    print(f"Modelos  : {config['deep_think_llm']} (denso) / {config['quick_think_llm']} (rapido)")
    print(f"Analistas: {', '.join(analistas)}")
    print(f"Data     : {args.data}\n")

    ta = TradingAgentsGraph(selected_analysts=analistas, debug=False, config=config)

    resultados = []
    for bruto in args.tickers:
        ticker = normalizar(bruto)
        print(f"{'=' * 70}\n{ticker} — analisando...\n{'=' * 70}")
        t0 = time.time()
        try:
            final_state, decision = ta.propagate(ticker, args.data)
        except Exception as exc:
            print(f"  FALHOU: {type(exc).__name__}: {exc}\n")
            resultados.append({"ticker": ticker, "erro": f"{type(exc).__name__}: {exc}"})
            continue

        decisao_md = final_state.get("final_trade_decision", "")
        segundos = time.time() - t0

        # Sinal de cobertura de dados: relatorio muito curto normalmente quer
        # dizer que o vendor devolveu pouca coisa para esse mercado.
        cobertura = {
            nome: len(final_state.get(chave, "") or "")
            for nome, chave in (
                ("mercado", "market_report"),
                ("sentimento", "sentiment_report"),
                ("noticias", "news_report"),
                ("fundamentos", "fundamentals_report"),
            )
        }

        resultados.append({
            "ticker": ticker,
            "rating": decision,
            "alvo": campo(decisao_md, "Price Target"),
            "horizonte": campo(decisao_md, "Time Horizon"),
            "resumo": campo(decisao_md, "Executive Summary"),
            "segundos": segundos,
            "cobertura": cobertura,
        })

        print(f"\n  RATING: {decision}   ({segundos:.0f}s)")
        print(f"\n{decisao_md}\n")
        print("  tamanho dos relatorios (caracteres):")
        for nome, n in cobertura.items():
            marca = " <-- suspeito de dado vazio" if n < 400 else ""
            print(f"    {nome:12} {n:>7}{marca}")
        print()

        if args.salvar:
            caminho = ta.save_reports(final_state, ticker)
            print(f"  relatorios salvos em: {caminho.parent}\n")

    print(f"\n{'=' * 70}\nRESUMO\n{'=' * 70}")
    for r in resultados:
        if "erro" in r:
            print(f"  {r['ticker']:12} ERRO — {r['erro']}")
        else:
            alvo = f"alvo {r['alvo']}" if r["alvo"] else "sem alvo"
            print(f"  {r['ticker']:12} {r['rating']:12} {alvo:18} {r['segundos']:.0f}s")
    print()
    return 0


if __name__ == "__main__":
    if not any(os.environ.get(k) for k in (
        "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY",
        "DEEPSEEK_API_KEY", "XAI_API_KEY", "OPENROUTER_API_KEY",
    )):
        print("ERRO: nenhuma chave de LLM encontrada no ambiente.\n"
              "      Defina uma antes de rodar, por exemplo:\n"
              "        export OPENAI_API_KEY=sk-...", file=sys.stderr)
        raise SystemExit(1)
    raise SystemExit(main())
