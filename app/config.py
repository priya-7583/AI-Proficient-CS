from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    app_name: str = "AI-Proficient URL Shortener"
    db_path: str = "shortener.db"
    short_code_length: int = 7
    create_limit_per_minute: int = 60
    require_mutating_auth: bool = True
    api_key: str = "dev-change-me"
    jwt_secret: str = "dev-jwt-secret-change-me"
    jwt_algorithm: str = "HS256"
    redis_url: str = ""


def load_settings() -> Settings:
    require_auth = os.getenv("SHORTENER_REQUIRE_MUTATING_AUTH", "1").strip() not in {
        "0",
        "false",
        "False",
    }
    return Settings(
        app_name=os.getenv("SHORTENER_APP_NAME", "AI-Proficient URL Shortener"),
        db_path=os.getenv("SHORTENER_DB_PATH", "shortener.db"),
        short_code_length=int(os.getenv("SHORTENER_CODE_LENGTH", "7")),
        create_limit_per_minute=int(os.getenv("SHORTENER_CREATE_LIMIT", "60")),
        require_mutating_auth=require_auth,
        api_key=os.getenv("SHORTENER_API_KEY", "dev-change-me"),
        jwt_secret=os.getenv("SHORTENER_JWT_SECRET", "dev-jwt-secret-change-me"),
        jwt_algorithm=os.getenv("SHORTENER_JWT_ALGORITHM", "HS256"),
        redis_url=os.getenv("SHORTENER_REDIS_URL", ""),
    )
