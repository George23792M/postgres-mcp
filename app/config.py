"""Typed application settings loaded from the environment or .env file."""

from functools import lru_cache
from typing import Annotated

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Validated database, server, and logging configuration."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
    )

    db_user: str = Field(min_length=1)
    db_password: SecretStr = Field(min_length=1)
    db_host: str = Field(min_length=1)
    db_port: int = Field(ge=1, le=65535)
    db_name: str = Field(min_length=1)
    mcp_host: str = Field(default="127.0.0.1", min_length=1)
    mcp_port: int = Field(default=8000, ge=1, le=65535)
    mcp_allowed_hosts: list[Annotated[str, Field(min_length=1)]] = Field(default_factory=list)
    mcp_auth_token: SecretStr = Field(min_length=32)
    log_level: str = Field(
        default="INFO",
        pattern="^(TRACE|DEBUG|INFO|SUCCESS|WARNING|ERROR|CRITICAL)$",
    )
    db_pool_min_size: int = Field(default=1, ge=1, le=100)
    db_pool_max_size: int = Field(default=10, ge=1, le=100)
    db_command_timeout: float = Field(default=30.0, gt=0, le=300)

    @model_validator(mode="after")
    def validate_pool_sizes(self) -> "Settings":
        """Ensure the configured pool maximum is not below its minimum."""
        if self.db_pool_max_size < self.db_pool_min_size:
            raise ValueError("DB_POOL_MAX_SIZE must be at least DB_POOL_MIN_SIZE")
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Load and cache validated application settings."""
    return Settings()
