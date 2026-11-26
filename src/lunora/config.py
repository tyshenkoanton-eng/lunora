from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {"env_prefix": "LUNORA_"}

    bot_token: str = ""
    database_url: str = "postgresql+asyncpg://lunora:lunora@localhost:5432/lunora"
    redis_url: str = "redis://localhost:6379/0"

    webhook_base_url: str = ""
    webapp_url: str = ""
    telegram_proxy: str = ""
    # тестовая среда Telegram (/bot<token>/test/…) — смоук Stars без реальных звёзд (G17-S3a)
    telegram_test_env: bool = False

    llm_api_key: str = ""
    llm_base_url: str = "https://openrouter.ai/api/v1"
    llm_model: str = "openai/gpt-4o-mini"

    # серверный перец для input_hash карты: HMAC, а не голый SHA-256 входа (ARCHITECTURE §3.2)
    calc_server_pepper: str = "lunora-dev-pepper-change-me"

    debug: bool = False


settings = Settings()
