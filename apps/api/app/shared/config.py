from functools import lru_cache
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration typée, validée une seule fois au démarrage.

    Toute variable obligatoire manquante fait échouer le démarrage
    immédiatement plutôt que de laisser une valeur par défaut silencieuse.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: Literal["local", "staging", "production"] = "local"
    database_url: SecretStr
    redis_url: SecretStr
    log_level: str = "INFO"
    default_currency: str = "EUR"
    fx_max_age_hours: int = 24
    active_ruleset_version: str = "1.2.0"
    cursor_secret: SecretStr
    dev_principal_email: str = "dev@kairos.local"
    cors_allowed_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
