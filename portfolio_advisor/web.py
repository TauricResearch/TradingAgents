from __future__ import annotations

import json
import logging
import os
import threading
from typing import Callable

from flask import Flask, jsonify, render_template, request

from .broker import (
    check_connection,
    load_settings,
    reauth_robinhood,
    save_portfolio_json,
    save_settings,
)
from .config import Aggressiveness, Config

logger = logging.getLogger(__name__)


def create_app(cfg: Config, run_now_fn: Callable) -> Flask:
    app = Flask(__name__, template_folder="templates")
    _running = threading.Event()

    def _read_state() -> dict:
        try:
            with open(cfg.state_file, encoding="utf-8") as fh:
                return json.load(fh)
        except (FileNotFoundError, json.JSONDecodeError):
            return {
                "last_intraday_run": None,
                "last_eod_run": None,
                "portfolio_source": "unknown",
                "portfolio_positions": [],
                "cash": 0,
                "actions": [],
                "aggressiveness": cfg.aggressiveness.value,
                "running": False,
            }

    def _patch_state(patch: dict) -> None:
        state = _read_state()
        state.update(patch)
        os.makedirs(os.path.dirname(cfg.state_file), exist_ok=True)
        with open(cfg.state_file, "w", encoding="utf-8") as fh:
            json.dump(state, fh, indent=2, default=str)

    @app.route("/")
    def index():
        return render_template("index.html", state=_read_state())

    @app.route("/api/state")
    def api_state():
        return jsonify(_read_state())

    # ── Aggressiveness ────────────────────────────────────────────────────────

    @app.route("/api/aggressiveness", methods=["POST"])
    def set_aggressiveness():
        value = (request.json or {}).get("aggressiveness", "conservative")
        try:
            cfg.aggressiveness = Aggressiveness(value)
        except ValueError:
            return jsonify({"ok": False, "reason": f"Unknown value: {value}"}), 400
        _patch_state({"aggressiveness": value})
        return jsonify({"ok": True})

    # ── Run ───────────────────────────────────────────────────────────────────

    @app.route("/api/run", methods=["POST"])
    def trigger_run():
        if _running.is_set():
            return jsonify({"ok": False, "reason": "run already in progress"}), 409

        def _run() -> None:
            _running.set()
            _patch_state({"running": True})
            try:
                run_now_fn()
            except Exception as exc:
                logger.error("On-demand run failed: %s", exc)
            finally:
                _running.clear()
                _patch_state({"running": False})

        threading.Thread(target=_run, daemon=True).start()
        return jsonify({"ok": True})

    # ── Portfolio (fallback JSON editor) ──────────────────────────────────────

    @app.route("/api/portfolio", methods=["POST"])
    def save_portfolio():
        data = request.json or {}
        try:
            save_portfolio_json(
                cfg.data_dir,
                data.get("positions", []),
                float(data.get("cash", 0)),
            )
        except Exception as exc:
            return jsonify({"ok": False, "reason": str(exc)}), 400
        return jsonify({"ok": True})

    # ── Settings ──────────────────────────────────────────────────────────────

    @app.route("/api/settings", methods=["GET"])
    def get_settings():
        """Return current settings (password masked)."""
        s = load_settings(cfg.data_dir)
        return jsonify({
            "robinhood_username": s.get("robinhood_username", ""),
            "robinhood_password_set": bool(s.get("robinhood_password")),
        })

    @app.route("/api/settings", methods=["POST"])
    def post_settings():
        """Save settings to data_dir/settings.json. Empty password = keep current."""
        data = request.json or {}
        patch: dict = {}
        if "robinhood_username" in data:
            patch["robinhood_username"] = str(data["robinhood_username"]).strip()
        if data.get("robinhood_password"):
            patch["robinhood_password"] = data["robinhood_password"]
        if not patch:
            return jsonify({"ok": False, "reason": "No settings provided"}), 400
        try:
            save_settings(cfg.data_dir, patch)
            return jsonify({"ok": True})
        except Exception as exc:
            logger.error("save_settings failed: %s", exc)
            return jsonify({"ok": False, "reason": str(exc)}), 500

    # ── Broker connection check ───────────────────────────────────────────────

    @app.route("/api/broker/check", methods=["POST"])
    def check_broker():
        """Lightweight connection check: login + profile only, no full portfolio build."""
        try:
            result = check_connection(cfg.data_dir)
            return jsonify(result)
        except Exception as exc:
            logger.error("check_connection raised unexpectedly: %s", exc)
            return jsonify({"ok": False, "error": str(exc)}), 500

    # ── Broker re-authentication ──────────────────────────────────────────────

    @app.route("/api/broker/reauth", methods=["POST"])
    def reauth_broker_route():
        """Re-authenticate with Robinhood.

        First call: POST {} — attempts login with stored credentials.
            Returns {"ok": false, "requires_mfa": true} if MFA is needed.
        Second call: POST {"mfa_code": "123456"} — completes MFA login.
        """
        data = request.json or {}
        mfa_code = data.get("mfa_code") or None
        try:
            status, message = reauth_robinhood(cfg.data_dir, mfa_code)
        except Exception as exc:
            logger.error("reauth_robinhood raised unexpectedly: %s", exc)
            return jsonify({"ok": False, "error": str(exc)}), 500

        if status == "ok":
            return jsonify({"ok": True})
        if status == "mfa_required":
            return jsonify({"ok": False, "requires_mfa": True})
        return jsonify({"ok": False, "error": message}), 400

    return app
