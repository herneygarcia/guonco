"""Per-user auth (PIN or Google sign-in): HMAC-signed session cookies, rw/ro roles.

Enabled when APP_PINS and/or GOOGLE_USERS is set (see src.config). Formats:
  APP_PINS=name:pin[,name:pin[:ro]]       # ":ro" suffix = read-only
  GOOGLE_USERS=email[,email[:ro]]         # needs GOOGLE_CLIENT_ID too
Google logins send a GIS ID token, verified here; the username is the email.
Sessions are stateless tokens: base64url(username|expiry|hmac(secret)).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import time

SESSION_TTL_S = 12 * 60 * 60
COOKIE_NAME = "guonco_session"


def _sign(secret: str, payload: str) -> str:
    return hmac.new(
        secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256
    ).hexdigest()


def create_token(username: str, secret: str, ttl_s: int = SESSION_TTL_S) -> str:
    expiry = str(int(time.time()) + ttl_s)
    payload = f"{username}|{expiry}"
    signed = f"{payload}|{_sign(secret, payload)}".encode()
    return base64.urlsafe_b64encode(signed).decode()


def verify_token(token: str, secret: str) -> tuple[str, str] | None:
    """Return (username, role) if valid, unexpired, and still in APP_PINS."""
    try:
        decoded = base64.urlsafe_b64decode(token.encode()).decode()
        username, expiry, sig = decoded.split("|")
        if not hmac.compare_digest(sig, _sign(secret, f"{username}|{expiry}")):
            return None
        if int(expiry) < time.time():
            return None
    except Exception:
        return None
    role = role_of(username)
    if role is None:
        # Removed from APP_PINS: existing sessions are revoked immediately.
        return None
    return username, role


def authenticate(code: str) -> tuple[str, str] | None:
    """Match a login code against APP_PINS -> (username, role) or None."""
    from src.config import app_pins

    code = (code or "").strip()
    if not code:
        return None
    for name, spec in app_pins().items():
        if hmac.compare_digest(spec["pin"], code):
            return name, spec["role"]
    return None


def authenticate_google(credential: str) -> tuple[str, str] | None:
    """Verify a Google ID token and match its email against GOOGLE_USERS."""
    from google.auth.exceptions import GoogleAuthError
    from google.auth.transport import requests as google_requests
    from google.oauth2 import id_token

    from src.config import google_client_id, google_users

    client_id = google_client_id()
    if not client_id or not credential:
        return None
    try:
        claims = id_token.verify_oauth2_token(
            credential, google_requests.Request(), client_id
        )
    except (ValueError, GoogleAuthError):  # bad/expired token, cert fetch failure
        return None
    if not claims.get("email_verified"):
        return None
    email = str(claims.get("email", "")).lower()
    spec = google_users().get(email)
    return (email, spec["role"]) if spec else None


def role_of(username: str) -> str | None:
    from src.config import app_pins, google_users

    spec = app_pins().get(username) or google_users().get(username)
    return spec["role"] if spec else None


def can_write(username: str) -> bool:
    return role_of(username) == "rw"
