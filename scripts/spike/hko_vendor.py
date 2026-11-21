#!/usr/bin/env python3
"""hko_vendor — чтение вендоренных таблиц Гонконгской обсерватории (эталон GE-07/GE-08).

Данные — data/vendor/hko (набор `hko-solar-terms` в MANIFEST.yaml, SHA-256 сверяет
vendor_check). Только для тестов: рантайм считает моменты терминов сам (§2.9).

  - 24SolarTerms_YYYY.xml — 24 термина года по порядку от «Moderate cold» (小寒, 285°),
    время HKT до минуты (UTC+8 — примечание на вендоренной странице Solar_Term.htm);
  - TYYYYe.txt — таблица перевода календаря: дата термина по HKT, без времени.

Файлы — недоверенные данные: только разбор текста, ничего не исполняется.
"""

from __future__ import annotations

import pathlib
import re
import xml.etree.ElementTree as ET  # noqa: S405 — локальный вендоренный файл с SHA-256
from datetime import date, datetime, timedelta

DEFAULT = pathlib.Path(__file__).resolve().parents[2] / "data" / "vendor" / "hko"
HKT = timedelta(hours=8)
# порядок терминов в XML обсерватории: от 小寒 (285°) с шагом 15°
FIRST_TERM_LON = 285.0
# 12 цзе (節) — нечётные по счёту от 小寒: 285°, 315° (立春), 345°, 15°, …, 255°
JIE_INDEXES = tuple(range(0, 24, 2))


def term_longitude(index: int) -> float:
    return (FIRST_TERM_LON + 15.0 * index) % 360.0


def load_term_times(year: int, root: pathlib.Path = DEFAULT) -> list[tuple[float, datetime]]:
    """[(долгота Солнца, момент HKT без пояса)] из 24SolarTerms_YYYY.xml, 24 строки."""
    tree = ET.parse(root / f"24SolarTerms_{year}.xml")  # noqa: S314
    rows = []
    for i, node in enumerate(tree.getroot().findall("Data")):
        hh, mm = node.findtext("hm").split(":")
        moment = datetime(year, int(node.findtext("M")), int(node.findtext("D")), int(hh), int(mm))
        rows.append((term_longitude(i), moment))
    if len(rows) != 24:
        raise ValueError(f"24SolarTerms_{year}.xml: {len(rows)} терминов вместо 24")
    return rows


_DAYS = "Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday"
# дата · лунная дата (бывает из нескольких слов, «Ninth Month») · день недели · термин
_LINE = re.compile(rf"^(\d{{4}})/(\d{{1,2}})/(\d{{1,2}})\s.*?\b(?:{_DAYS})\s+(\S.*?)\s*$")


def load_term_dates(year: int, root: pathlib.Path = DEFAULT) -> dict[str, date]:
    """{английское имя термина: дата HKT} из TYYYYe.txt (кодировка — latin-1, байты как есть)."""
    out: dict[str, date] = {}
    text = (root / f"T{year}e.txt").read_bytes().decode("latin-1")
    for line in text.splitlines()[2:]:
        m = _LINE.match(line)
        if m:
            out[m.group(4)] = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    return out
