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

    # Recherche autonome de comparables. Source : API officielle eBay (programme
    # développeur gratuit). Sans identifiants, la source reste inerte : elle
    # n'émet aucune requête et l'écran le dit. Les identifiants ne sont jamais
    # journalisés.
    ebay_client_id: SecretStr | None = None
    ebay_client_secret: SecretStr | None = None
    ebay_environment: Literal["production", "sandbox"] = "production"
    # Adresse de l'API eBay, seulement pour la remplacer par un serveur d'essai
    # (parcours navigateur de la CI). Vide : l'adresse officielle du programme.
    ebay_api_base_url: str | None = None
    # Places de marché interrogées, séparées par des virgules.
    ebay_marketplaces: str = "EBAY_FR,EBAY_DE,EBAY_IT"
    # Lancer la recherche dès qu'une référence est confirmée.
    market_search_auto: bool = True

    # Valeur de développement uniquement. En production, une origine en dur
    # autoriserait un site qui n'est pas le nôtre à porter des requêtes
    # authentifiées : le validateur ci-dessous l'interdit.
    cors_allowed_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]

    @model_validator(mode="after")
    def _refuse_local_defaults_outside_local(self) -> "Settings":
        if self.environment == "local":
            return self

        # Envoyer des identifiants eBay en clair vers une adresse qui n'est pas
        # en HTTPS serait les divulguer : refusé hors développement local.
        if self.ebay_api_base_url and not self.ebay_api_base_url.startswith("https://"):
            raise ValueError(
                "EBAY_API_BASE_URL doit être en https hors développement local."
            )

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
