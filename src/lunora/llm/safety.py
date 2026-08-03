import re
from enum import StrEnum


class Category(StrEnum):
    NORMAL = "normal"
    MEDICAL = "medical"
    CRISIS = "crisis"
    FINANCIAL = "financial"


_MEDICAL_PATTERNS = re.compile(
    r"болезн|здоровь|лечени|болит|диагноз|рак|опухол|операци|беременн|"
    r"медицин|симптом|таблетк|лекарств|врач|больниц",
    re.IGNORECASE,
)

_CRISIS_PATTERNS = re.compile(
    r"суицид|убить себя|не хочу жить|покончить|смерть|умереть|"
    r"бессмысленно|нет смысла жить|конец жизни|повеситься|"
    r"отравиться|прыгну|порежу",
    re.IGNORECASE,
)

_FINANCIAL_PATTERNS = re.compile(
    r"инвестиц|акци[яию]|крипто|биткоин|торговл[яю]|биржа|вложи|"
    r"кредит|ипотек|заработ|бизнес.*открыть|открыть.*бизнес",
    re.IGNORECASE,
)


def classify_input(text: str) -> Category:
    if _CRISIS_PATTERNS.search(text):
        return Category.CRISIS
    if _MEDICAL_PATTERNS.search(text):
        return Category.MEDICAL
    if _FINANCIAL_PATTERNS.search(text):
        return Category.FINANCIAL
    return Category.NORMAL
