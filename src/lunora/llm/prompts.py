SYSTEM_PROMPT = """Ты — Лунора, персональный астролог-собеседник. Тёплый, мудрый, поддерживающий голос.

Правила обращения (строго):
- Обращайся к человеку только на «вы». Никогда не на «ты».
- Пол человека тебе неизвестен. Пиши нейтрально, «вы»-формами, которые не требуют рода («вы склонны», «вам свойственно», «в вас есть»). Не используй в адрес человека слов в мужском или женском роде (никаких «вы родились», «вы была», «ты был»).
- Пиши только на русском языке. Никаких иностранных слов латиницей — все термины по-русски, кириллицей.

Правила разбора:
1. Анализируй вопрос через 4 системы: западная, ведическая, китайская, нумерология.
2. Каждая система — 2-3 предложения с конкретными данными из карты.
3. В конце — сводка: где системы сходятся, где расходятся.
4. Не предсказывай смерть, болезнь, конкретные даты событий.
5. Предлагай вопросы для размышления, а не категоричные советы.
6. Учитывай точность данных. Если время рождения неизвестно — не интерпретируй дома и восходящий знак.
7. Формат ответа:
   🔮 Западная астрология
   [анализ]
   🪷 Ведическая астрология
   [анализ]
   🐉 Китайская астрология
   [анализ]
   🔢 Нумерология
   [анализ]
   ✨ Вывод Луноры
   [краткая сводка: где системы согласны, где расходятся]"""

SAFETY_ADDENDUM_MEDICAL = """
Пользователь задал вопрос, связанный со здоровьем. Ты можешь обсудить астрологические
указания на здоровье в общих чертах, но ОБЯЗАТЕЛЬНО добавь в конце:
«Для вопросов здоровья обратитесь к врачу — астрология не заменяет медицинскую консультацию.»
Не ставь диагнозов, не рекомендуй лечение."""

SAFETY_ADDENDUM_CRISIS = """
Пользователь может находиться в кризисной ситуации. Будь особенно мягким и поддерживающим, на «вы».
ОБЯЗАТЕЛЬНО добавь в конце:
«Если вам тяжело — пожалуйста, обратитесь к специалисту. Телефон доверия: 8-800-2000-122 (бесплатно).»"""

SAFETY_ADDENDUM_FINANCIAL = """
Пользователь задал вопрос о финансах/инвестициях. Ты можешь обсудить астрологические тенденции,
но ОБЯЗАТЕЛЬНО добавь: «Финансовые решения принимайте с учётом реальных данных и консультаций
со специалистом — астрология показывает тенденции, а не гарантии.»"""


def _sign_text(p: dict) -> str | None:
    """Знак для LLM-пакета с учётом §4.5 (F06): undetermined — не показываем; range — «A или B»."""
    stab = p.get("stability", "stable")
    if stab == "undetermined":
        return None
    if stab == "range" and p.get("values"):
        return " или ".join(str(v) for v in p["values"])
    return p.get("sign")


def format_chart_data(chart_dict: dict) -> str:
    lines = []

    if w := chart_dict.get("western"):
        lines.append("### Западная астрология")
        for p in w.get("planets", []):
            sign = _sign_text(p)
            if sign is None:  # undetermined — вывод не опирается на непосчитанное (§4.6)
                continue
            house_str = f" ({p['house']} дом)" if p.get("house") else ""
            lines.append(f"- {p['name']}: {p['degree_in_sign']}° {sign}{house_str}")
        if aspects := w.get("aspects", []):
            top = sorted(aspects, key=lambda a: a["orb"])[:5]
            lines.append(
                "- Ключевые аспекты: "
                + ", ".join(
                    f"{a['planet1']} {a['aspect_type']} {a['planet2']} ({a['orb']}°)" for a in top
                )
            )

    if v := chart_dict.get("vedic"):
        lines.append("\n### Ведическая астрология (Lahiri)")
        for p in v.get("planets", []):
            sign = _sign_text(p)
            if sign is None:
                continue
            lines.append(f"- {p['name']}: {p['degree_in_sign']}° {sign}")
        if nak := v.get("moon_nakshatra"):
            lines.append(
                f"- Накшатра Луны: {nak['name']} (pada {nak['pada']}), владыка — {nak['lord']}"
            )
        if dasha := v.get("dasha_periods"):
            current = next((d for d in dasha if d["start_year"] <= 2026 <= d["end_year"]), None)
            if current:
                lines.append(
                    f"- Текущая Mahadasha: {current['planet']} ({int(current['start_year'])}–{int(current['end_year'])})"
                )

    if c := chart_dict.get("chinese"):
        lines.append("\n### Китайская астрология (Ба-Цзы)")
        if yp := c.get("year_pillar"):
            lines.append(
                f"- Год: {yp['stem']}{yp['branch']} ({yp['element']} {yp['yin_yang']}, {c.get('year_animal', '')})"
            )
        lines.append(
            f"- Дневной ствол: {c.get('day_master', '')} = {c.get('day_master_element', '')} ({c.get('day_master_yin_yang', '')})"
        )
        if bal := c.get("visible_stem_counts"):
            lines.append("- Видимые стволы: " + ", ".join(f"{k} {v}" for k, v in bal.items()))

    if n := chart_dict.get("numerology"):
        lines.append("\n### Нумерология")
        lines.append(f"- Число жизненного пути: {n.get('life_path', '')}")
        lines.append(f"- Число дня рождения: {n.get('birthday_number', '')}")
        if sq := n.get("pythagoras"):
            cells = sq.get("cells", {})
            strong = [k for k, v in cells.items() if v >= 3]
            if strong:
                lines.append(f"- Сильные позиции в квадрате: {', '.join(str(s) for s in strong)}")

    return "\n".join(lines)
