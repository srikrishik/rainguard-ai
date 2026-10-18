
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ENV_FILE = Path(__file__).resolve().parents[1] / ".env"


def _load_environment() -> None:
    load_dotenv(dotenv_path=ENV_FILE)


_load_environment()


def _get_optional_env(name: str) -> str | None:
    """Return a trimmed environment value, or None if empty or missing."""
    return os.getenv(name, "").strip() or None


def _get_bool_env(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    frontend_origin: str = "http://localhost:5173"
    mongodb_uri: str | None = None
    database_name: str | None = None

    # Hosted Gemma multimodal integration
    gemma_api_key: str | None = None
    gemma_api_url: str | None = None
    gemma_model_id: str | None = None

    # Optional Temporal integration; disabled until a server and worker exist.
    temporal_address: str = "127.0.0.1:7233"
    temporal_namespace: str = "default"
    temporal_enabled: bool = False


def get_settings() -> Settings:
    return Settings(
        frontend_origin=(
            os.getenv("FRONTEND_ORIGIN", "http://localhost:5173").strip()
            or "http://localhost:5173"
        ),
        mongodb_uri=_get_optional_env("MONGODB_URI"),
        database_name=_get_optional_env("DATABASE_NAME"),
        gemma_api_key=_get_optional_env("GEMMA_API_KEY"),
        gemma_api_url=_get_optional_env("GEMMA_API_URL"),
        gemma_model_id=_get_optional_env("GEMMA_MODEL_ID"),
        temporal_address=(
            os.getenv("TEMPORAL_ADDRESS", "127.0.0.1:7233").strip()
            or "127.0.0.1:7233"
        ),
        temporal_namespace=(
            os.getenv("TEMPORAL_NAMESPACE", "default").strip()
            or "default"
        ),
        temporal_enabled=_get_bool_env("TEMPORAL_ENABLED"),
    )
