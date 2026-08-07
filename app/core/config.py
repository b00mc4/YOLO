from functools import lru_cache
from typing import Literal
from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="forbid")

    database_url: str

    jwt_secret: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 30

    cookie_samesite: Literal["lax", "strict", "none"] = "lax"
    cookie_secure: bool = False
    cookie_domain: str | None = None

    trust_proxy_headers: bool = False
    trusted_proxy_hops: int = Field(default=1, ge=1)

    sse_ticket_expire_seconds: int = 30

    api_key_header_name: str = "X-API-Key"
    api_key: str

    storage_path: str = "./storage"

    frontend_url: str

    smtp_host: str
    smtp_port: int
    smtp_user: str
    smtp_password: str
    smtp_from_email: str

    mediamtx_api_url: str
    mediamtx_public_url: str
    mediamtx_api_user: str
    mediamtx_api_password: str

    ai_vision_api_url: str
    ai_vision_api_key: str

    @model_validator(mode="after")
    def check_cookie_security(self) -> "Settings":
        if self.cookie_samesite == "none" and not self.cookie_secure:
            raise ValueError(
                "cookie_samesite='none' requires cookie_secure=True: "
                "browsers reject SameSite=None cookies that are not Secure"
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()