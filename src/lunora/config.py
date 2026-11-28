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
    # У моделей Claude 5.5 «мышление» не выключается и тарифицируется как выход; при малом
    # лимите оно съедает весь бюджет вывода → finish_reason=length, content=None (пустой
    # ответ). Поэтому: запас по max_tokens + минимальный ризонинг (effort=low). Доказано
    # живым замером S3b (scripts/spike/llm_measure.py). Пустая строка в reasoning_effort —
    # не слать поле reasoning (для провайдеров/моделей, где оно не нужно).
    llm_max_tokens: int = 3000
    llm_reasoning_effort: str = "low"

    # серверный перец для input_hash карты: HMAC, а не голый SHA-256 входа (ARCHITECTURE §3.2)
    calc_server_pepper: str = "lunora-dev-pepper-change-me"

    debug: bool = False


settings = Settings()
