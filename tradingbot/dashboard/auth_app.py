"""
TradingAgents Auth Page — Streamlit login / register flow.

Two entry points:

1. Standalone:
       streamlit run tradingbot/dashboard/auth_app.py
       python run_auth.py
   Only the auth flow; no dashboard mounted.

2. As a gate in the main dashboard:
       from tradingbot.dashboard.auth_app import render_auth_flow, get_auth_service
       if not st.session_state.get("auth_user"):
           render_auth_flow(get_auth_service())
           return
   The dashboard's app.py uses this path.

Follows docs/ui-guidelines.md (t() for all strings, semantic colours,
KPI/empty/error patterns).

User store: standalone ~/.tradingagents/users.db (override via
TRADINGBOT_USERS_DB env var).
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

# Make sure the project root is on the path so all imports resolve.
_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import streamlit as st

from tradingbot.auth import AuthError, AuthService, UserDatabase
from tradingbot.auth.service import default_users_db_path
from tradingbot.dashboard.i18n import t, language_selector


# ── Page config (must be first Streamlit call) ────────────────────────────

st.set_page_config(
    page_title=t("auth.app.title"),
    page_icon="🔐",
    layout="centered",
    initial_sidebar_state="collapsed",
)


# ── Cached singletons ─────────────────────────────────────────────────────

@st.cache_resource
def _get_user_db() -> UserDatabase:
    return UserDatabase(default_users_db_path())


@st.cache_resource
def get_auth_service() -> AuthService:
    """Public — also imported by app.py to share the same singleton."""
    return AuthService(_get_user_db())


# ── Semantic colours (from docs/ui-guidelines.md) ─────────────────────────

_BRAND_BG = "#E3F2FD"
_BRAND_FG = "#0D47A1"
_SUCCESS_BG = "#E8F5E9"
_SUCCESS_FG = "#4CAF50"


# ── Error mapping ─────────────────────────────────────────────────────────

def _format_error(exc: AuthError) -> str:
    key = f"auth.err.{exc.code}"
    msg = t(key)
    if msg == key:  # fail-soft: unknown code
        return t("auth.err.unknown", detail=str(exc))
    return msg


# ── Header / sidebar ──────────────────────────────────────────────────────

def _render_header():
    st.markdown(
        f'<div style="background:{_BRAND_BG};border-left:6px solid {_BRAND_FG};'
        f'padding:18px 22px;border-radius:6px;margin-bottom:18px">'
        f'<div style="font-size:1.6em;font-weight:700;color:{_BRAND_FG}">'
        f'{t("auth.brand")}</div>'
        f'<div style="font-size:0.95em;color:#37474F;margin-top:4px">'
        f'{t("auth.tagline")}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )


def _render_sidebar_lang():
    language_selector()


# ── Login view ────────────────────────────────────────────────────────────

def _render_login(auth: AuthService):
    st.subheader(t("auth.login.subheader"))
    st.caption(t("auth.login.caption"))

    tab_pw, tab_sms = st.tabs([t("auth.tab.password"), t("auth.tab.sms")])

    with tab_pw:
        _render_login_password(auth)

    with tab_sms:
        _render_login_sms(auth)

    st.markdown("")
    if st.button(t("auth.login.to_register"), key="login_to_register"):
        st.session_state["auth_mode"] = "register"
        st.rerun()


def _render_login_password(auth: AuthService):
    identifier = st.text_input(t("auth.login.identifier"), key="login_pw_id").strip()
    password = st.text_input(
        t("auth.login.password"), type="password", key="login_pw_pwd"
    )
    submit = st.button(
        t("auth.login.submit"),
        type="primary",
        use_container_width=True,
        key="login_pw_submit",
    )

    if not submit:
        return

    try:
        user = auth.login_with_password(identifier, password)
    except AuthError as exc:
        st.error(_format_error(exc))
        return
    except Exception as exc:  # noqa: BLE001
        st.error(t("auth.err.unknown", detail=str(exc)))
        return

    st.session_state["auth_user"] = user.username
    st.success(t("auth.login.success", name=user.username))
    st.rerun()


def _render_login_sms(auth: AuthService):
    phone = st.text_input(t("auth.sms.phone"), key="login_sms_phone").strip()

    cooldown_until = st.session_state.get("sms_cooldown_until", 0.0)
    now = time.time()
    cooling = now < cooldown_until

    send_label = (
        t("auth.sms.resend", sec=int(cooldown_until - now))
        if cooling else t("auth.sms.send")
    )

    # Verification-code input and the "send code" button share one row.
    col_code, col_send = st.columns([2, 1])
    code = col_code.text_input(t("auth.sms.code"), key="login_sms_code").strip()
    # Spacer to vertically align the button with the input field below its label.
    col_send.markdown("<div style='height:1.85em'></div>", unsafe_allow_html=True)
    send_clicked = col_send.button(
        send_label,
        use_container_width=True,
        disabled=cooling,
        key="login_sms_send",
    )

    if send_clicked:
        try:
            dev_code = auth.send_sms_code(phone)
        except AuthError as exc:
            st.error(_format_error(exc))
        else:
            st.session_state["sms_cooldown_until"] = time.time() + 60
            st.success(t("auth.sms.sent"))
            # Dev convenience — no SMS provider configured yet.
            st.info(t("auth.sms.dev_hint", code=dev_code))

    submit = st.button(
        t("auth.sms.submit"),
        type="primary",
        use_container_width=True,
        key="login_sms_submit",
    )

    if not submit:
        return

    try:
        user = auth.login_with_code(phone, code)
    except AuthError as exc:
        st.error(_format_error(exc))
        return
    except Exception as exc:  # noqa: BLE001
        st.error(t("auth.err.unknown", detail=str(exc)))
        return

    st.session_state["auth_user"] = user.username
    st.success(t("auth.login.success", name=user.username))
    st.rerun()


# ── Register view ────────────────────────────────────────────────────────

def _render_register(auth: AuthService):
    st.subheader(t("auth.register.subheader"))
    st.caption(t("auth.register.caption"))

    username = st.text_input(t("auth.register.username"), key="reg_username").strip()
    st.caption(t("auth.register.username_hint"))

    phone = st.text_input(t("auth.register.phone"), key="reg_phone").strip()
    st.caption(t("auth.register.phone_hint"))

    email = st.text_input(t("auth.register.email"), key="reg_email").strip()

    password = st.text_input(
        t("auth.register.password"), type="password", key="reg_password"
    )
    st.caption(t("auth.register.password_hint"))

    confirm = st.text_input(
        t("auth.register.confirm"), type="password", key="reg_confirm"
    )

    submit = st.button(
        t("auth.register.submit"),
        type="primary",
        use_container_width=True,
        key="reg_submit",
    )

    if submit:
        try:
            auth.register(
                username=username,
                password=password,
                confirm_password=confirm,
                phone=phone,
                email=email or None,
            )
        except AuthError as exc:
            st.error(_format_error(exc))
        except Exception as exc:  # noqa: BLE001
            st.error(t("auth.err.unknown", detail=str(exc)))
        else:
            st.success(t("auth.register.success"))
            st.session_state["auth_mode"] = "login"
            st.rerun()

    st.markdown("")
    if st.button(t("auth.register.to_login"), key="reg_to_login"):
        st.session_state["auth_mode"] = "login"
        st.rerun()


# ── Public entry: reusable auth flow ──────────────────────────────────────

def render_auth_flow(auth: AuthService) -> None:
    """
    Render the login / register UI in the current Streamlit container.
    Mode is driven entirely by the inline "go to register" / "back to login"
    buttons inside each view — no top-level toggle.

    On success, sets st.session_state['auth_user'] = username and
    triggers a rerun so callers can re-check the gate.
    """
    _render_header()

    mode = st.session_state.get("auth_mode", "login")
    if mode == "login":
        _render_login(auth)
    else:
        _render_register(auth)


# ── Standalone main ───────────────────────────────────────────────────────

def main():
    _render_sidebar_lang()
    render_auth_flow(get_auth_service())


if __name__ == "__main__":
    main()
