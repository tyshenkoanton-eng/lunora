import httpx

from lunora.config import settings
from lunora.llm.prompts import (
    SAFETY_ADDENDUM_CRISIS,
    SAFETY_ADDENDUM_FINANCIAL,
    SAFETY_ADDENDUM_MEDICAL,
    SYSTEM_PROMPT,
    format_chart_data,
)
from lunora.llm.safety import Category, classify_input
from lunora.llm.validator import validate_output

MAX_RETRIES = 2


async def generate_response(
    question: str,
    chart_data: dict,
    precision: str,
    history: list[dict] | None = None,
) -> tuple[str, Category]:
    category = classify_input(question)

    system = SYSTEM_PROMPT
    if category == Category.MEDICAL:
        system += "\n\n" + SAFETY_ADDENDUM_MEDICAL
    elif category == Category.CRISIS:
        system += "\n\n" + SAFETY_ADDENDUM_CRISIS
    elif category == Category.FINANCIAL:
        system += "\n\n" + SAFETY_ADDENDUM_FINANCIAL

    chart_text = format_chart_data(chart_data)
    precision_note = f"\nТочность времени рождения: {precision}."
    if precision in ("unknown", "approximate"):
        precision_note += " Не интерпретируй дома и ASC."

    user_content = f"## Данные натальной карты\n{chart_text}\n{precision_note}\n\n## Вопрос\n{question}"

    messages = [{"role": "system", "content": system}]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": user_content})

    for attempt in range(MAX_RETRIES + 1):
        raw = await _call_llm(messages)

        valid, reason = validate_output(raw)
        if valid:
            return raw, category

        if attempt < MAX_RETRIES:
            messages.append({"role": "assistant", "content": raw})
            messages.append({
                "role": "user",
                "content": f"Твой ответ не прошёл валидацию: {reason}. Перепиши ответ в правильном формате.",
            })

    return raw, category


async def _call_llm(messages: list[dict]) -> str:
    if not settings.llm_api_key:
        raise RuntimeError("LUNORA_LLM_API_KEY not set")

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            f"{settings.llm_base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.llm_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": settings.llm_model,
                "messages": messages,
                "max_tokens": 1000,
                "temperature": 0.7,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]
