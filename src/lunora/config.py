from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {"env_prefix": "LUNORA_"}

    bot_token: str = ""
    database_url: str = "postgresql+asyncpg://lunora:lunora@localhost:5432/lunora"
    redis_url: str = "redis://localhost:6379/0"

    webhook_base_url: str = ""
    telegram_proxy: str = ""

    debug: bool = False


settings = Settings()
