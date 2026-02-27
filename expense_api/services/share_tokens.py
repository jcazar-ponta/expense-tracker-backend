import hashlib
import hmac
import secrets

from django.conf import settings


def generate_share_token() -> str:
    # token_urlsafe(32) uses 32 random bytes (~256-bit entropy).
    return secrets.token_urlsafe(32)


def hash_share_token(raw_token: str) -> str:
    pepper = getattr(settings, "SHARE_TOKEN_PEPPER", settings.SECRET_KEY)
    digest = hmac.new(
        key=str(pepper).encode("utf-8"),
        msg=raw_token.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).hexdigest()
    return digest
