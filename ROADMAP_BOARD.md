# Лунора — дорожная карта (витрина)

<!-- СГЕНЕРИРОВАНО scripts/board_gen.py из docs/current/ROADMAP_STATUS.yaml.
     Руками не править: правь источник и прогони `make board`. -->

**Уровень:** L1 · **Гейт:** G17 · **Слайс:** G17-S1 (в работе)

| | |
|---|---|
| Последнее ревью | — (—) |
| Блокер | нет active golden-кейсов — нужен ручной съём эталонов Антоном (astro.com, Jagannatha Hora, калькуляторы Ба-Цзы); golden_audit --require-active красный намеренно |
| Следующий шаг | G17-S1: эфемеридный слой _ephem.py (Skyfield 1.55 + DE440s, SHA-256 сверен) готов, дифф с SE по §2.11 и 10 дат Horizons зелёные; tzdata 2026f и GeoNames завендорены. Дальше: golden-кейсы GE/timeplace по съёму Антона, справочник мест в рантайме, истинное солнечное время и момент терминов (§2.8–2.9). Карточка docs/current/G17-S1-план.md. PASS = зелёные make slice-check и make verify. |

Подробная карта — `docs/05_roadmap.md`. Источник статуса — `docs/current/ROADMAP_STATUS.yaml`.
