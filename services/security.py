"""Runtime security helpers: env config and HTTP Basic Auth for Dash/Flask."""
from __future__ import annotations

import os
import secrets
from pathlib import Path

from flask import Response, request

_ROOT = Path(__file__).resolve().parents[1]


def load_dotenv(path: Path | None = None) -> None:
    """Load KEY=VALUE lines from .env into os.environ (does not override)."""
    env_path = path or (_ROOT / ".env")
    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if key and key not in os.environ:
            os.environ[key] = value


load_dotenv()


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def debug_enabled() -> bool:
    return _env_bool("FM_DEBUG", False)


def bind_host() -> str:
    return (os.environ.get("FM_HOST") or "127.0.0.1").strip() or "127.0.0.1"


def bind_port() -> int:
    # Render sets PORT; prefer it, then FM_PORT, then local default.
    raw = (os.environ.get("PORT") or os.environ.get("FM_PORT") or "8050").strip()
    try:
        return int(raw)
    except ValueError:
        return 8050


def secret_key() -> str:
    key = (os.environ.get("FM_SECRET_KEY") or "").strip()
    if key:
        return key
    # Ephemeral key is fine for local loopback; set FM_SECRET_KEY in deploy.
    return secrets.token_hex(32)


def auth_disabled() -> bool:
    return _env_bool("FM_AUTH_DISABLED", False)


def auth_credentials() -> tuple[str, str] | None:
    user = (os.environ.get("FM_AUTH_USER") or "").strip()
    password = os.environ.get("FM_AUTH_PASSWORD") or ""
    if not user or password == "":
        return None
    return user, password


def assert_auth_config(*, host: str) -> None:
    """Refuse insecure public binds without auth credentials."""
    if auth_disabled():
        if host not in {"127.0.0.1", "localhost", "::1"}:
            raise SystemExit(
                "Refusing to start: FM_AUTH_DISABLED is set but FM_HOST is not "
                "loopback. Set FM_AUTH_USER / FM_AUTH_PASSWORD, or bind 127.0.0.1."
            )
        return
    if auth_credentials() is None:
        raise SystemExit(
            "Refusing to start without authentication.\n"
            "Set FM_AUTH_USER and FM_AUTH_PASSWORD, or for local-only use set "
            "FM_AUTH_DISABLED=true with FM_HOST=127.0.0.1.\n"
            "See .env.example."
        )


def _unauthorized() -> Response:
    return Response(
        "Authentication required.",
        401,
        {"WWW-Authenticate": 'Basic realm="FMScouter"'},
    )


def install_basic_auth(flask_app) -> None:
    """Protect all routes (pages + Dash callback endpoints) with HTTP Basic Auth."""
    if auth_disabled():
        print(
            "WARNING: FM_AUTH_DISABLED=true — HTTP Basic Auth is off. "
            "Use only on loopback."
        )
        return

    creds = auth_credentials()
    if creds is None:
        raise SystemExit(
            "Refusing to start without authentication.\n"
            "Set FM_AUTH_USER and FM_AUTH_PASSWORD, or for local-only use set "
            "FM_AUTH_DISABLED=true with FM_HOST=127.0.0.1.\n"
            "See .env.example."
        )
    expected_user, expected_password = creds

    @flask_app.before_request
    def _require_basic_auth():
        auth = request.authorization
        if (
            auth
            and auth.username == expected_user
            and auth.password == expected_password
        ):
            return None
        return _unauthorized()
