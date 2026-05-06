"""Email-OTP login gate with HMAC-signed URL-token sessions.

Flow:
    1. On every page load, read the ``s`` query parameter from the URL.
       If valid (HMAC matches, not expired) → user is authed, gate is bypassed.
    2. Otherwise: show email form → send OTP via SMTP → verify code →
       issue a signed session token → write it to ``?s=...`` so refresh keeps
       the user logged in.
    3. Sign out clears the query param.

Session tokens are stateless (HMAC of email + expiry signed with
``SESSION_SECRET``). To revoke all sessions, rotate ``SESSION_SECRET``
in ``.env`` and restart the service. URL-token approach was chosen over the
``extra-streamlit-components`` CookieManager because the cookie component's
async set/get races with Streamlit reruns (cookies set during one rerun
weren't readable on the next refresh).

Configuration (read from environment / .env):
    ALLOWED_EMAILS    Comma-separated whitelist (case-insensitive).
    SMTP_HOST/PORT/USER/PASS/FROM   SMTP for sending OTP.
    AUTH_DEV_FALLBACK Set to "1" to write OTPs to /tmp/tradingagents_otp.log
                      instead of mailing.
    SESSION_SECRET    HMAC secret for signing session cookies.
    SESSION_TTL_DAYS  Cookie/session lifetime in days (default 7).
"""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import smtplib
import socket as _socket_module
import time
from contextlib import contextmanager
from email.mime.text import MIMEText
from pathlib import Path
from typing import Optional, Tuple

OTP_TTL_SEC = 600  # 10 minutes
MAX_ATTEMPTS = 5
URL_TOKEN_PARAM = "s"
SMTP_TIMEOUT_SEC = 90  # Gmail SMTP from this host is slow (~25–60s direct)


@contextmanager
def _socks_patched_socket():
    """If ALL_PROXY=socks5://host:port is set, route subsequent socket
    connections through it for the duration of this context.

    smtplib doesn't honour HTTP proxy env vars, but we can monkey-patch
    socket.socket so its TCP connect goes via SOCKS5. Direct TCP to Gmail SMTP
    is throttled on this host (~25–60s); routing through the local proxy is
    sub-second.
    """
    all_proxy = os.getenv("ALL_PROXY", "")
    if not all_proxy.startswith("socks5://"):
        yield
        return
    try:
        import socks  # PySocks
    except ImportError:
        yield
        return
    try:
        proxy_part = all_proxy[len("socks5://"):]
        phost, _, pport = proxy_part.partition(":")
        socks.set_default_proxy(socks.SOCKS5, phost, int(pport or "1080"))
        original = _socket_module.socket
        _socket_module.socket = socks.socksocket
        try:
            yield
        finally:
            _socket_module.socket = original
    except Exception:
        yield

# email -> (code, expires_at, attempts)
_OTP_STORE: dict[str, tuple[str, float, int]] = {}

_DEV_LOG = Path("/tmp/tradingagents_otp.log")


# ─── Whitelist + SMTP config ───
def _get_whitelist() -> set[str]:
    raw = os.getenv("ALLOWED_EMAILS", "")
    return {e.strip().lower() for e in raw.split(",") if e.strip()}


def _smtp_configured() -> bool:
    return bool(os.getenv("SMTP_HOST") and os.getenv("SMTP_USER") and os.getenv("SMTP_PASS"))


def _dev_fallback() -> bool:
    return os.getenv("AUTH_DEV_FALLBACK") == "1"


# ─── Session token (stateless HMAC) ───
def _session_secret() -> bytes:
    s = os.getenv("SESSION_SECRET", "")
    if not s:
        # Fail-closed: refuse to issue sessions without a configured secret.
        raise RuntimeError("SESSION_SECRET is not set in .env")
    return s.encode()


def _session_ttl_sec() -> int:
    days = int(os.getenv("SESSION_TTL_DAYS", "7"))
    return days * 24 * 3600


def issue_token(email: str) -> str:
    email = email.strip().lower()
    expires = int(time.time()) + _session_ttl_sec()
    payload = f"{email}|{expires}"
    sig = hmac.new(_session_secret(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}|{sig}"


def verify_token(token: str) -> Optional[str]:
    """Return the verified email or None."""
    if not token or token.count("|") != 2:
        return None
    try:
        email, expires_str, sig = token.split("|")
        payload = f"{email}|{expires_str}"
        expected = hmac.new(_session_secret(), payload.encode(),
                            hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected):
            return None
        if int(expires_str) < time.time():
            return None
        if email not in _get_whitelist():
            # Whitelist may have shrunk — invalidate.
            return None
        return email
    except (ValueError, RuntimeError):
        return None


# ─── OTP send / verify ───
def send_otp(email: str) -> Tuple[bool, str]:
    email = email.strip().lower()
    if email not in _get_whitelist():
        return False, "This email is not authorized."

    code = f"{secrets.randbelow(1_000_000):06d}"
    _OTP_STORE[email] = (code, time.time() + OTP_TTL_SEC, 0)

    if _dev_fallback() or not _smtp_configured():
        _DEV_LOG.write_text(f"{time.strftime('%F %T')} {email} {code}\n",
                            encoding="utf-8")
        return True, f"DEV mode — code written to {_DEV_LOG}"

    host = os.getenv("SMTP_HOST")
    port = int(os.getenv("SMTP_PORT", "587"))
    user = os.getenv("SMTP_USER")
    pw = os.getenv("SMTP_PASS")
    sender = os.getenv("SMTP_FROM", user)

    msg = MIMEText(
        f"Your TradingAgents verification code is:\n\n"
        f"    {code}\n\n"
        f"It expires in {OTP_TTL_SEC // 60} minutes.\n"
    )
    msg["Subject"] = "TradingAgents login code"
    msg["From"] = sender
    msg["To"] = email

    try:
        with _socks_patched_socket():
            with smtplib.SMTP(host, port, timeout=SMTP_TIMEOUT_SEC) as s:
                s.ehlo()
                s.starttls()
                s.ehlo()
                s.login(user, pw)
                s.send_message(msg)
        return True, "Verification code sent."
    except Exception as e:
        return False, f"Failed to send email: {e}"


def verify_otp(email: str, code: str) -> bool:
    email = email.strip().lower()
    rec = _OTP_STORE.get(email)
    if not rec:
        return False
    stored, expires, attempts = rec
    if time.time() > expires or attempts >= MAX_ATTEMPTS:
        _OTP_STORE.pop(email, None)
        return False
    if code.strip() == stored:
        _OTP_STORE.pop(email, None)
        return True
    _OTP_STORE[email] = (stored, expires, attempts + 1)
    return False


# ─── Streamlit gate ───
def gate(st_module, lang: str = "en") -> str:
    """Render login UI if not authenticated. Returns the authed email.

    Sequence on every rerun:
      1. If session_state already has authed_email → fast return.
      2. Otherwise read ``?s=`` token from URL; if valid → authenticate.
      3. Otherwise show email/OTP forms; on success, set both session_state
         and the URL ``?s=`` so refresh keeps the user logged in.
    """
    L = _LABELS[lang if lang in _LABELS else "en"]

    # 1. Already authed in this Streamlit session?
    if "authed_email" in st_module.session_state:
        # Make sure the URL still carries the token (so future refreshes work).
        if URL_TOKEN_PARAM not in st_module.query_params:
            st_module.query_params[URL_TOKEN_PARAM] = issue_token(
                st_module.session_state["authed_email"]
            )
        return st_module.session_state["authed_email"]

    # 2. URL-token session restore.
    token = st_module.query_params.get(URL_TOKEN_PARAM)
    if token:
        email = verify_token(token)
        if email:
            st_module.session_state["authed_email"] = email
            return email
        else:
            # Token invalid/expired — clear it from URL so login form shows.
            try:
                del st_module.query_params[URL_TOKEN_PARAM]
            except KeyError:
                pass

    # 3. Login UI.
    if not _get_whitelist():
        st_module.error(L["no_whitelist"])
        st_module.stop()

    st_module.title("🔒 TradingAgents")
    st_module.caption(L["caption"])

    if "otp_sent_to" not in st_module.session_state:
        with st_module.form("email_form"):
            email = st_module.text_input(L["email_label"])
            ok = st_module.form_submit_button(L["send_code"], type="primary")
            if ok:
                if not email:
                    st_module.error(L["email_required"])
                else:
                    sent, msg = send_otp(email)
                    if sent:
                        st_module.session_state["otp_sent_to"] = email.strip().lower()
                        st_module.session_state["otp_send_msg"] = msg
                        st_module.rerun()
                    else:
                        st_module.error(msg)
        st_module.stop()
    else:
        with st_module.form("otp_form"):
            st_module.info(
                L["code_sent"].format(st_module.session_state["otp_sent_to"])
            )
            if st_module.session_state.get("otp_send_msg", "").startswith("DEV"):
                st_module.warning("DEV mode: " + st_module.session_state["otp_send_msg"])
            code = st_module.text_input(L["code_label"], max_chars=6)
            c1, c2 = st_module.columns(2)
            verify = c1.form_submit_button(L["verify"], type="primary")
            again = c2.form_submit_button(L["use_other"])
            if again:
                st_module.session_state.pop("otp_sent_to", None)
                st_module.session_state.pop("otp_send_msg", None)
                st_module.rerun()
            if verify:
                target_email = st_module.session_state["otp_sent_to"]
                if verify_otp(target_email, code):
                    # Issue session token + write to URL so refresh persists.
                    token = issue_token(target_email)
                    st_module.query_params[URL_TOKEN_PARAM] = token
                    st_module.session_state["authed_email"] = target_email
                    st_module.session_state.pop("otp_sent_to", None)
                    st_module.session_state.pop("otp_send_msg", None)
                    st_module.rerun()
                else:
                    st_module.error(L["invalid_code"])
        st_module.stop()
    return ""  # unreachable


def sign_out(st_module) -> None:
    """Clear URL token + session state. Call from a sidebar button."""
    try:
        del st_module.query_params[URL_TOKEN_PARAM]
    except KeyError:
        pass
    st_module.session_state.pop("authed_email", None)


_LABELS = {
    "en": {
        "caption": "Restricted access. Enter your email to receive a one-time code.",
        "no_whitelist": "ALLOWED_EMAILS is not configured. Edit .env to add authorized emails.",
        "email_label": "Email address",
        "email_required": "Please enter an email.",
        "send_code": "Send code",
        "code_sent": "A 6-digit code was sent to **{}**. It expires in 10 minutes.",
        "code_label": "Verification code",
        "verify": "Verify",
        "use_other": "Use a different email",
        "invalid_code": "Invalid or expired code. Try again or request a new one.",
    },
    "zh": {
        "caption": "受限访问。请输入邮箱以接收一次性验证码。",
        "no_whitelist": "ALLOWED_EMAILS 尚未配置，请在 .env 中加入允许的邮箱。",
        "email_label": "邮箱地址",
        "email_required": "请输入邮箱。",
        "send_code": "发送验证码",
        "code_sent": "已向 **{}** 发送 6 位验证码，10 分钟内有效。",
        "code_label": "验证码",
        "verify": "验证",
        "use_other": "换个邮箱",
        "invalid_code": "验证码错误或已过期，请重试或重新发送。",
    },
}
