# Configuration

Settings and data live in `~/.tauric/tradingagents/`, the configuration directory:

| Where                | What                                                                          |
| -------------------- | ----------------------------------------------------------------------------- |
| `config.json`        | the model, reasoning, provider settings, limits and sync                      |
| `credentials.json`   | stored keys, readable only by you                                             |
| `chatgpt-auth.json`  | a ChatGPT sign-in, readable only by you                                       |
| `history.jsonl`      | the last questions asked in the terminal                                      |
| `agents/`, `skills/` | your own agents and skills (see [usage](usage.md#your-own-agents-and-skills)) |
| `sessions/`          | sessions                                                                      |
| `memory/`            | notes and recorded decisions                                                  |

The update check's state is kept there too. `TRADINGAGENTS_HOME`, an absolute path, moves the whole directory. Skills shared between agent clients, in `~/.agents/skills/`, are read from there wherever the directory is.

A complete `config.json`:

```json
{
  "model": "anthropic/claude-sonnet-5-5",
  "reasoning": "high",
  "providers": {
    "openai-compatible": {
      "baseURL": "https://your-server/v1",
      "contextWindow": 131072
    }
  },
  "limits": { "question": { "time": "20m" } },
  "sync": "on"
}
```

| Environment variable                                                                              | Sets                                                                               |
| ------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------- |
| `TRADINGAGENTS_MODEL`                                                                             | the model, as `provider/id` (or the server's model, with `TRADINGAGENTS_BASE_URL`) |
| `TRADINGAGENTS_BASE_URL`                                                                          | an OpenAI-compatible server's address                                              |
| `TRADINGAGENTS_MODEL_API_KEY`                                                                     | that server's key                                                                  |
| `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, `DEEPSEEK_API_KEY`, `OPENROUTER_API_KEY`, `LLMTR_API_KEY` | a provider's key (see [models](models.md))                                         |
| `TAURIC_API_KEY`                                                                                  | the Tauric API key                                                                 |
| `TRADINGAGENTS_SYNC`                                                                              | `on` or `off`, over the setting in `config.json`                                   |
| `TRADINGAGENTS_HOME`                                                                              | one directory for configuration and data                                           |
| `TRADINGAGENTS_NO_UPDATE_CHECK`                                                                   | any non-empty value turns off the check for a newer release                        |

Settings come from the command line first, then the environment, then `config.json`.
