"""Bridge configuration via environment variables.

All settings can be overridden with the ``SPAD_`` prefix, e.g. ``SPAD_VENDOR_PORT=9999``.
"""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SPAD_", env_file=".env", extra="ignore")

    vendor_host: str = "127.0.0.1"
    vendor_port: int = 9999

    bridge_host: str = "0.0.0.0"
    bridge_port: int = 8080

    data_root: str = "data"


@lru_cache
def get_settings() -> Settings:
    return Settings()
