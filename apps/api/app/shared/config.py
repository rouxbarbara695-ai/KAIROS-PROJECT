from functools import lru_cache
from typing import Literal

from pydantic import SecretStr, model_validator
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
    session_lifetime_days: int = 30

    # Valeur de développement uniquement. En production, une origine en dur
    # autoriserait un site qui n'est pas le nôtre à porter des requêtes
    # authentifiées : le validateur ci-dessous l'interdit.
    cors_allowed_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]

    @model_validator(mode="after")
    def _refuse_local_defaults_outside_local(self) -> "Settings":
        if self.environment == "local":
            return self

        local_origins = {
            origin
            for origin in self.cors_allowed_origins
            if "localhost" in origin or "127.0.0.1" in origin
        }
        if local_origins or not self.cors_allowed_origins:
            raise ValueError(
                "CORS_ALLOWED_ORIGINS doit être renseigné avec les origines "
                "réelles hors développement local : une origine locale laissée "
                "en place autoriserait des requêtes authentifiées depuis "
                "n'importe quel poste."
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
