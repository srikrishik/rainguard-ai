import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    frontend_origin: str = "http://localhost:5173"


def get_settings() -> Settings:
    return Settings(
        frontend_origin=os.getenv("FRONTEND_ORIGIN", "http://localhost:5173").strip()
        or "http://localhost:5173"
    )
