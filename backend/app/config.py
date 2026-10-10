
from functools import lru_cache
import json
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    database_url: str = ""

    oneid_issuer_url: str = "http://localhost:8000"

    oneid_allowed_origins: str = (
        "http://localhost:8000,"
        "http://127.0.0.1:8000,"
        "http://localhost:5500,"
        "http://127.0.0.1:5500,"
        "http://localhost:5501,"
        "http://127.0.0.1:5501,"
        "http://localhost:5502,"
        "http://127.0.0.1:5502,"
        "http://localhost:5503,"
        "http://127.0.0.1:5503"
    )

    oneid_jwt_secret: str = "local-only-change-me"

    oneid_bootstrap_admin_username: str = ""

    oneid_client_redirect_uris: str = (
        '{"fakepress":["http://localhost:5500/","http://127.0.0.1:5500/"],'
        '"inkvoid":["http://localhost:5501/","http://127.0.0.1:5501/"],'
        '"pigsty":["http://localhost:5502/","http://127.0.0.1:5502/"],'
        '"nova":["http://localhost:5503/login.html","http://127.0.0.1:5503/login.html"]}'
    )

    model_config = SettingsConfigDict(
        env_file=ROOT_DIR / ".env",
        extra="ignore",
    )

    @property
    def allowed_origins(self) -> list[str]:
        return [
            origin.strip()
            for origin in self.oneid_allowed_origins.split(",")
            if origin.strip()
        ]

    @property
    def client_redirect_uris(self) -> dict[str, list[str]]:
        try:
            value = json.loads(self.oneid_client_redirect_uris)
        except json.JSONDecodeError as exc:
            raise ValueError(
                "ONEID_CLIENT_REDIRECT_URIS must be a JSON object."
            ) from exc

        if not isinstance(value, dict) or any(
            not isinstance(items, list) for items in value.values()
        ):
            raise ValueError(
                "ONEID_CLIENT_REDIRECT_URIS must map client IDs "
                "to redirect URI lists."
            )

        return {
            str(client): [str(uri) for uri in uris]
            for client, uris in value.items()
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()
