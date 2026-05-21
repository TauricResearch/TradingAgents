#!/usr/bin/env bash
# TradingAgents 启动脚本
# 用法：
#   ./start.sh            — 启动 Streamlit 仪表盘（默认）
#   ./start.sh dashboard  — 启动 Streamlit 仪表盘
#   ./start.sh cli        — 交互式 CLI 分析
#   ./start.sh bot        — 自动交易机器人（定时模式）
#   ./start.sh bot-once [TICKER] [DATE]  — 单次运行机器人
#   ./start.sh bot-once AAPL 2024-05-10 --approval  — 附带人工审批

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PYTHON="$SCRIPT_DIR/.venv/bin/python"
MODE="${1:-dashboard}"

# 加载 .env
if [ -f "$SCRIPT_DIR/.env" ]; then
  set -a
  # shellcheck disable=SC1090
  source "$SCRIPT_DIR/.env"
  set +a
fi

# 检查虚拟环境
if [ ! -x "$VENV_PYTHON" ]; then
  echo "[ERROR] 虚拟环境不存在：$VENV_PYTHON"
  echo "       请先运行：uv sync"
  exit 1
fi

case "$MODE" in
  dashboard)
    echo "[INFO] 启动 Streamlit 仪表盘 → http://localhost:8501"
    STREAMLIT_EMAIL="" exec "$VENV_PYTHON" -m streamlit run \
      "$SCRIPT_DIR/tradingbot/dashboard/app.py" \
      --server.headless true \
      --theme.base dark \
      --server.port 8501
    ;;

  cli)
    echo "[INFO] 启动交互式 CLI 分析"
    exec "$VENV_PYTHON" -m cli.main "${@:2}"
    ;;

  bot)
    echo "[INFO] 启动自动交易机器人（定时模式）— Ctrl-C 退出"
    exec "$VENV_PYTHON" "$SCRIPT_DIR/run_bot.py" "${@:2}"
    ;;

  bot-once)
    TICKER="${2:-}"
    DATE="${3:-}"
    EXTRA_ARGS="${@:4}"
    CMD=("$VENV_PYTHON" "$SCRIPT_DIR/run_bot.py" --once)
    [ -n "$TICKER" ] && CMD+=(--ticker "$TICKER")
    [ -n "$DATE"   ] && CMD+=(--date   "$DATE")
    # shellcheck disable=SC2206
    [ -n "$EXTRA_ARGS" ] && CMD+=($EXTRA_ARGS)
    echo "[INFO] 单次运行机器人：${CMD[*]}"
    exec "${CMD[@]}"
    ;;

  *)
    echo "未知模式：$MODE"
    echo "可选：dashboard | cli | bot | bot-once"
    exit 1
    ;;
esac
