"""
Build a structured interpretation from chart data,
then ask LLM to synthesize into a unified personality portrait.
"""

from lunora.interpret.planets import (
    PLANET_INTERPRETATIONS,
    PLANET_LABELS,
    SIGN_LABELS,
    SIGN_SYMBOLS,
)


def build_interpretation_blocks(chart_data: dict) -> list[dict]:
    """Return list of {planet, planet_ru, sign, sign_ru, symbol, text} dicts."""
    blocks = []
    western = chart_data.get("western")
    if not western:
        return blocks

    for p in western.get("planets", []):
        name = p.get("name", "")
        sign = p.get("sign", "")
        interps = PLANET_INTERPRETATIONS.get(name, {})
        text = interps.get(sign)
        if text:
            blocks.append({
                "planet": name,
                "planet_ru": PLANET_LABELS.get(name, name),
                "sign": sign,
                "sign_ru": SIGN_LABELS.get(sign, sign),
                "symbol": SIGN_SYMBOLS.get(sign, ""),
                "house": p.get("house"),
                "degree": round(p.get("degree_in_sign", 0), 1),
                "text": text,
            })
    return blocks


PORTRAIT_SYSTEM_PROMPT = """Ты — Лунора, мудрый и тёплый астролог-рассказчик.

Тебе дан набор интерпретаций отдельных планетных положений пользователя.
Твоя задача — собрать из них ЕДИНЫЙ ПОРТРЕТ ЛИЧНОСТИ.

Правила:
1. Пиши от второго лица, на «ты».
2. Группируй по темам: Личность и характер, Эмоции и внутренний мир, Любовь и отношения, Мышление и общение, Энергия и действие.
3. Не перечисляй планеты по отдельности — переплетай их в связный текст.
4. Где положения противоречат друг другу — подчеркни это как внутреннее напряжение, не как ошибку.
5. Тон: тёплый, поддерживающий, как мудрая подруга. Без жаргона.
6. Длина: 300-500 слов.
7. Не упоминай технические термины (транзиты, аспекты, дома). Просто описывай человека.
8. Заверши 1-2 предложениями — чем уникальна эта комбинация качеств.

Формат ответа — чистый текст без заголовков и маркеров. Каждая тема — отдельный абзац."""


def build_portrait_prompt(blocks: list[dict], chart_data: dict) -> str:
    """Build user prompt for LLM portrait synthesis."""
    lines = ["Вот интерпретации положений натальной карты этого человека:\n"]

    for b in blocks:
        lines.append(f"**{b['planet_ru']} в {b['sign_ru']}**: {b['text']}")

    chinese = chart_data.get("chinese")
    if chinese:
        animal = chinese.get("year_animal", "")
        element = chinese.get("day_master_element", "")
        if animal:
            lines.append(f"\n**Китайская астрология**: год {animal}, стихия дневного мастера — {element}.")

    numerology = chart_data.get("numerology")
    if numerology:
        lp = numerology.get("life_path", 0)
        if lp:
            lines.append(f"\n**Нумерология**: число жизненного пути — {lp}.")

    lines.append("\nСобери из этого единый портрет личности.")
    return "\n".join(lines)
