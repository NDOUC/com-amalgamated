import os
import secrets
import redis
from typing import Optional

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
r = redis.from_url(REDIS_URL)

def create_signed_download_token(file_path: str, expires_seconds: int = 600) -> str:
    token = secrets.token_urlsafe(32)
    r.setex(f"download:{token}", expires_seconds, file_path)
    return token

def resolve_signed_download_token(token: str) -> Optional[str]:
    val = r.get(f"download:{token}")
    if not val:
        return None
    r.delete(f"download:{token}")
    return val.decode()
  
