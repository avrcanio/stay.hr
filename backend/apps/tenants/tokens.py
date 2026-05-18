import hashlib
import secrets

DEFAULT_KEY_PREFIX = "stay_pk_live_"
TOKEN_SUFFIX_BYTES = 32


def generate_token(prefix: str = DEFAULT_KEY_PREFIX) -> str:
    return f"{prefix}{secrets.token_urlsafe(TOKEN_SUFFIX_BYTES)}"


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def verify_token(token: str, stored_hash: str) -> bool:
    return secrets.compare_digest(hash_token(token), stored_hash)


def extract_token_from_request(request) -> str | None:
    authorization = request.META.get("HTTP_AUTHORIZATION", "")
    if authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
        if token:
            return token
    header_key = request.META.get("HTTP_X_STAY_APP_KEY", "").strip()
    if header_key:
        return header_key
    return None
