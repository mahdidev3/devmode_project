\
import base64
import hashlib
import hmac
import secrets
from typing import Dict, Optional, Tuple

PBKDF2_ROUNDS = 240000


def hash_password(password: str) -> Dict[str, str]:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ROUNDS)
    return {
        "salt": salt.hex(),
        "password_hash": digest.hex(),
        "rounds": str(PBKDF2_ROUNDS),
    }


def verify_password(record: Dict[str, str], password: str) -> bool:
    try:
        salt = bytes.fromhex(record["salt"])
        expected = bytes.fromhex(record["password_hash"])
        rounds = int(record.get("rounds", PBKDF2_ROUNDS))
    except Exception:
        return False
    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, rounds)
    return hmac.compare_digest(actual, expected)


def decode_basic_auth(headers: Dict[str, str]) -> Tuple[Optional[str], Optional[str]]:
    auth_value = headers.get("proxy-authorization") or headers.get("authorization")
    if not auth_value:
        return None, None
    parts = auth_value.split(" ", 1)
    if len(parts) != 2:
        return None, None
    scheme, encoded = parts
    if scheme.lower() != "basic":
        return None, None
    try:
        decoded = base64.b64decode(encoded.strip()).decode("utf-8")
    except Exception:
        return None, None
    if ":" not in decoded:
        return None, None
    return decoded.split(":", 1)


def encode_basic_auth(username: str, password: str) -> str:
    token = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
    return f"Basic {token}"
