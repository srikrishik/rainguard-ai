import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ENV_FILE = Path(__file__).resolve().parents[1] / ".env"


def _load_environment() -> None:
    load_dotenv(dotenv_path=ENV_FILE)


_load_environment()


@dataclass(frozen=True)
class Settings:
    frontend_origin: str = "http://localhost:5173"
    mongodb_uri: str | None = None
    database_name: str | None = None


def get_settings() -> Settings:
    return Settings(
        frontend_origin=os.getenv("FRONTEND_ORIGIN", "http://localhost:5173").strip()
        or "http://localhost:5173",
        mongodb_uri=os.getenv("MONGODB_URI", "").strip() or None,
        database_name=os.getenv("DATABASE_NAME", "").strip() or None,
    )
