"""Утилиты для REST API аутентификации"""
import hmac
import hashlib
import time
from typing import Dict


def sign_request_hmac(secret: str, message: str) -> str:
    """HMAC SHA256 подпись"""
    return hmac.new(
        secret.encode('utf-8'),
        message.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()


def get_timestamp_ms() -> int:
    """Timestamp в миллисекундах"""
    return int(time.time() * 1000)


def build_query_string(params: Dict) -> str:
    """Построить query string из параметров"""
    return '&'.join([f"{k}={v}" for k, v in sorted(params.items())])
