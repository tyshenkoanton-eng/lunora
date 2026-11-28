import httpx

from lunora.config import settings
from lunora.llm.pii import guard_package
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

# Аддендум безопасности по категории вопроса. Порядок прежний: CRISIS приоритетнее
# остальных — это решает classify_input, а не таблица.
_SAFETY_ADDENDUM_BY_CATEGORY = {
    Category.MEDICAL: SAFETY_ADDENDUM_MEDICAL,
    Category.CRISIS: SAFETY_ADDENDUM_CRISIS,
    Category.FINANCIAL: SAFETY_ADDENDUM_FINANCIAL,
}


def build_messages(
    question: str,
    chart_data: dict,
    precision: str,
    history: list[dict] | None = None,
    category: Category | None = None,
) -> list[dict]:
    """Собрать пакет сообщений, уходящий в модель.

    Чистая функция: без сети, без состояния, без чтения конфига. Собранный пакет
    можно получить офлайн и проверить, что в нём нет персональных данных
    (152-ФЗ; проверка — tests/test_llm_privacy.py).

    `category` — классификация вопроса по safety. Если не передана, определяется
    здесь: classify_input чистая и дешёвая. `generate_response` передаёт категорию
    явно, чтобы не классифицировать вопрос дважды.
    """
    if category is None:
        category = classify_input(question)

    system = SYSTEM_PROMPT
    addendum = _SAFETY_ADDENDUM_BY_CATEGORY.get(category)
    if addendum is not None:
        system += "\n\n" + addendum

    chart_text = format_chart_data(chart_data)
    precision_note = f"\nТочность времени рождения: {precision}."
    if precision in ("unknown", "approximate"):
        precision_note += " Не интерпретируй дома и ASC."

    user_content = (
        f"## Данные натальной карты\n{chart_text}\n{precision_note}\n\n## Вопрос\n{question}"
    )

    messages = [{"role": "system", "content": system}]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": user_content})
    return messages


async def generate_response(
    question: str,
    chart_data: dict,
    precision: str,
    history: list[dict] | None = None,
) -> tuple[str, Category]:
    category = classify_input(question)
    messages = build_messages(question, chart_data, precision, history, category)

    for attempt in range(MAX_RETRIES + 1):
        raw = await _call_llm(messages)

        valid, reason = validate_output(raw)
        if valid:
            return raw, category

        if attempt < MAX_RETRIES:
            messages.append({"role": "assistant", "content": raw})
            messages.append(
                {
                    "role": "user",
                    "content": (
                        f"Твой ответ не прошёл валидацию: {reason}. "
                        "Перепиши ответ в правильном формате."
                    ),
                }
            )

    return raw, category


async def _call_llm(messages: list[dict]) -> str:
    # Рантайм-страж ПДн (152-ФЗ): единая точка перед сетью на обоих путях (чат и
    # портрет). Fail-closed: при ПДн в служебной части пакета он в сеть не уходит.
    # Проверка — первой, до чтения конфига: предохранитель не зависит от настроек.
    guard_package(messages)

    if not settings.llm_api_key:
        raise RuntimeError("LUNORA_LLM_API_KEY not set")

    body = {
        "model": settings.llm_model,
        "messages": messages,
        "max_tokens": settings.llm_max_tokens,
        "temperature": 0.7,
    }
    # Минимальный ризонинг для Claude 5.5 (мышление не выключить; по умолчанию съедает
    # бюджет вывода → пустой ответ). Пустой effort → поле не слать. Доказано замером S3b.
    if settings.llm_reasoning_effort:
        body["reasoning"] = {"effort": settings.llm_reasoning_effort}

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            f"{settings.llm_base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.llm_api_key}",
                "Content-Type": "application/json",
            },
            json=body,
        )
        resp.raise_for_status()
        data = resp.json()
        # content=None приходит, когда ответ обрезан на лимите (finish_reason=length) —
        # мышление съело бюджет. Не роняем вызов TypeError'ом: пустая строка не пройдёт
        # validate_output и уйдёт на ретрай (чат), а не обрушит путь.
        return data["choices"][0]["message"]["content"] or ""
