// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
// Generated from CHANGELOG.md; do not edit.
import type { VersionNotes } from "./whats-new.js";

export const CHANGELOG: readonly VersionNotes[] = [
  {
    "version": "Unreleased",
    "sections": [
      {
        "items": [
          "Models: LLMTR, an OpenAI-compatible gateway at `https://llmtr.com/v1`, reached with `LLMTR_API_KEY`."
        ]
      }
    ]
  },
  {
    "version": "1.0.1",
    "sections": [
      {
        "items": [
          "A plan's report asks the question the planning started from; replies added while planning follow it in the PDF.",
          "A report opens with the answer, without the progress notes written along the way.",
          "Price history reads two, three and five years.",
          "A year of price history that spans February 29 is no longer refused.",
          "Storing a key names the provider's API key (for example, \"Stored the Tauric API key\").",
          "A correlation of returns needs at least three returns (four shared dates); over three dates it reported a perfect +1 or -1."
        ]
      }
    ]
  },
  {
    "version": "1.0.0",
    "sections": [
      {
        "items": [
          "TradingAgents: Towards Agentic Finance Research."
        ]
      },
      {
        "heading": "Research",
        "items": [
          "Agents: Equity Research, Macro Strategy, Quant Research and Risk Analysis research in parallel and report back.",
          "Skills: sixteen built-in research methods, from an earnings review to a DCF valuation.",
          "Your own agents and skills, as Markdown files.",
          "Plan mode: review and revise a research plan before it runs.",
          "Sources: every figure is cited to the data it came from."
        ]
      },
      {
        "heading": "Data and models",
        "items": [
          "Data: with a Tauric API key, market data, fundamentals, filings, news, economic series and prediction-market odds.",
          "Compute: statistics, risk, technical indicators, valuation and portfolio construction over the data read.",
          "Models: Tauric AI, OpenAI, Anthropic, Google, DeepSeek, OpenRouter, AI subscriptions (ChatGPT), or self-hosted models."
        ]
      },
      {
        "heading": "Sessions and output",
        "items": [
          "Sessions: resume any session, and sync sessions to your Tauric account.",
          "Export: a PDF report or Markdown; `/copy` copies the answer.",
          "Scripting: `tradingagents -p` answers one question; `--json` streams events; `--limit` caps time, tokens and steps."
        ]
      },
      {
        "heading": "Install",
        "items": [
          "`curl -fsSL https://tauric.ai/tradingagents/install.sh | sh` or `npm i -g @tauric/tradingagents`; updates are offered at start."
        ]
      }
    ]
  }
];
