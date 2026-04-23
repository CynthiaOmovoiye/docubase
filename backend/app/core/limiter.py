"""
Rate limiter — SlowAPI backed by Redis.

Import `limiter` and apply @limiter.limit("N/period") to route functions.
The SlowAPIMiddleware must be added to the FastAPI app (see main.py).

Key limits (adjust in config):
  - Auth endpoints (login, register):  10 req / minute per IP
  - Public chat:                        30 req / minute per IP
  - Default global limit:             300 req / minute per IP (applied at middleware level)
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.config import get_settings

settings = get_settings()

limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=settings.redis_url,
    default_limits=["300/minute"],
)
