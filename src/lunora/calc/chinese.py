from datetime import datetime

from cnlunar import Lunar

from lunora.calc.types import BaziPillar, BirthData, ChineseChart

STEMS = ["甲", "乙", "丙", "丁", "戊", "己", "庚", "辛", "壬", "癸"]
ELEMENTS = ["Дерево", "Дерево", "Огонь", "Огонь", "Земля", "Земля",
            "Металл", "Металл", "Вода", "Вода"]
YIN_YANG = ["Ян", "Инь", "Ян", "Инь", "Ян", "Инь", "Ян", "Инь", "Ян", "Инь"]

ANIMALS = ["Крыса", "Бык", "Тигр", "Кролик", "Дракон", "Змея",
           "Лошадь", "Коза", "Обезьяна", "Петух", "Собака", "Свинья"]


def _parse_pillar(chars: str) -> BaziPillar | None:
    if len(chars) < 2:
        return None
    stem = chars[0]
    branch = chars[1]
    if stem not in STEMS:
        return None
    idx = STEMS.index(stem)
    return BaziPillar(
        stem=stem,
        branch=branch,
        element=ELEMENTS[idx],
        yin_yang=YIN_YANG[idx],
    )


def calculate_chinese(data: BirthData) -> ChineseChart:
    hour = data.birth_time.hour if data.birth_time else 12
    minute = data.birth_time.minute if data.birth_time else 0
    dt = datetime(data.birth_date.year, data.birth_date.month, data.birth_date.day, hour, minute)

    lunar = Lunar(dt, godType="8char")

    year_pillar = _parse_pillar(lunar.year8Char)
    month_pillar = _parse_pillar(lunar.month8Char)
    day_pillar = _parse_pillar(lunar.day8Char)
    hour_pillar = _parse_pillar(lunar.twohour8Char)

    if year_pillar:
        animal_idx = (data.birth_date.year - 4) % 12
        year_pillar.animal = ANIMALS[animal_idx]

    element_balance: dict[str, int] = {
        "Дерево": 0, "Огонь": 0, "Земля": 0, "Металл": 0, "Вода": 0,
    }
    for pillar in [year_pillar, month_pillar, day_pillar, hour_pillar]:
        if pillar:
            element_balance[pillar.element] += 1

    day_master = ""
    day_master_element = ""
    day_master_yin_yang = ""
    if day_pillar:
        day_master = day_pillar.stem
        day_master_element = day_pillar.element
        day_master_yin_yang = day_pillar.yin_yang

    return ChineseChart(
        year_pillar=year_pillar,
        month_pillar=month_pillar,
        day_pillar=day_pillar,
        hour_pillar=hour_pillar,
        day_master=day_master,
        day_master_element=day_master_element,
        day_master_yin_yang=day_master_yin_yang,
        year_animal=year_pillar.animal if year_pillar else "",
        element_balance=element_balance,
    )
