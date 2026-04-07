from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = Field(default="Renjz Kitchen", alias="APP_NAME")
    api_prefix: str = Field(default="/api", alias="API_PREFIX")
    secret_key: str = Field(default="change-me", alias="SECRET_KEY")
    access_token_expire_minutes: int = Field(default=720, alias="ACCESS_TOKEN_EXPIRE_MINUTES")
    seed_demo_data: bool = Field(default=False, alias="SEED_DEMO_DATA")
    business_timezone: str = Field(default="Asia/Kolkata", alias="BUSINESS_TIMEZONE")
    receipt_printer_enabled: bool = Field(default=False, alias="RECEIPT_PRINTER_ENABLED")
    receipt_printer_host: str = Field(default="", alias="RECEIPT_PRINTER_HOST")
    receipt_printer_port: int = Field(default=9100, alias="RECEIPT_PRINTER_PORT")
    receipt_printer_timeout_seconds: float = Field(default=3.0, alias="RECEIPT_PRINTER_TIMEOUT_SECONDS")
    receipt_printer_chars_per_line: int = Field(default=42, alias="RECEIPT_PRINTER_CHARS_PER_LINE")
    receipt_shop_name: str = Field(default="RENJZ KITCHEN", alias="RECEIPT_SHOP_NAME")
    receipt_address_lines: list[str] = Field(
        default=[
            "Bhuvanappa layout, 30, 31, 32",
            "2nd cross road, Tavarekere Main Rd,",
            "DRC Post, Bengaluru, Karnataka 560029",
        ],
        alias="RECEIPT_ADDRESS_LINES",
    )
    receipt_phone: str = Field(default="9400204473", alias="RECEIPT_PHONE")
    receipt_header: str = Field(default="Renjz Kitchen", alias="RECEIPT_HEADER")
    receipt_footer: str = Field(default="Thank you. Visit again.", alias="RECEIPT_FOOTER")
    database_url: str = Field(
        default="postgresql+psycopg://postgres:postgres@localhost:5432/restaurant_app",
        alias="DATABASE_URL",
    )
    cors_origins: list[str] = Field(
        default=["http://localhost:5173", "http://127.0.0.1:5173"],
        alias="CORS_ORIGINS",
    )

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @field_validator("receipt_address_lines", mode="before")
    @classmethod
    def parse_receipt_address_lines(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, str):
            return [line.strip() for line in value.split("|") if line.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
