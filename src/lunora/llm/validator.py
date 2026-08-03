import re

_FORBIDDEN = re.compile(
    r"ты умрёшь|дата смерти|точная дата|гарантирую|100%|"
    r"обязательно случится|неизбежно|я предсказываю",
    re.IGNORECASE,
)

_REQUIRED_SECTIONS = ["🔮", "🪷", "🐉", "🔢", "✨"]


def validate_output(response: str) -> tuple[bool, str]:
    if _FORBIDDEN.search(response):
        return False, "Ответ содержит запрещённые формулировки"

    missing = [s for s in _REQUIRED_SECTIONS if s not in response]
    if missing:
        return False, f"Отсутствуют секции: {', '.join(missing)}"

    if len(response) < 200:
        return False, "Ответ слишком короткий"

    return True, ""
