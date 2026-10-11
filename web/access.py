"""Decide whether a web request comes from the owner (full access) or a public visitor (read-only).

Requests through the Cloudflare Tunnel reach Flask from cloudflared on this same machine, so
they look local; they count as the owner only with a valid Cloudflare Access JWT (the
Cf-Access-Jwt-Assertion header Access adds after login). Requests that arrive directly over the
home network — the Kindle's tap listener, or a browser at http://<pi-ip>:5000 — are trusted, as
before. Anything that fails or can't be verified falls back to public.
"""
import jwt
from flask import request

from config import Config

_jwks_client: jwt.PyJWKClient | None = None


def _team_url() -> str:
    domain = Config.CF_ACCESS_TEAM_DOMAIN.strip().removeprefix("https://").rstrip("/")
    return f"https://{domain}"


def _via_tunnel() -> bool:
    # Cloudflare always sets Cf-Connecting-Ip on proxied requests (clients can't strip it), and
    # cloudflared forwards to localhost:5000, so either signal means "came in from the internet".
    return request.remote_addr in ("127.0.0.1", "::1") or "Cf-Connecting-Ip" in request.headers


def _has_valid_access_jwt() -> bool:
    global _jwks_client
    token = request.headers.get("Cf-Access-Jwt-Assertion")
    if not token or not Config.CF_ACCESS_TEAM_DOMAIN or not Config.CF_ACCESS_AUD:
        return False
    try:
        if _jwks_client is None:
            _jwks_client = jwt.PyJWKClient(f"{_team_url()}/cdn-cgi/access/certs")
        key = _jwks_client.get_signing_key_from_jwt(token).key
        jwt.decode(token, key, algorithms=["RS256"], audience=Config.CF_ACCESS_AUD, issuer=_team_url())
        return True
    except Exception:
        return False


def is_owner() -> bool:
    return not _via_tunnel() or _has_valid_access_jwt()
