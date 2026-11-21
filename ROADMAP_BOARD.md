# Лунора — дорожная карта (витрина)

<!-- СГЕНЕРИРОВАНО scripts/board_gen.py из docs/current/ROADMAP_STATUS.yaml.
     Руками не править: правь источник и прогони `make board`. -->

**Уровень:** L1 · **Гейт:** G17 · **Слайс:** G17-S1 (в работе)

| | |
|---|---|
| Последнее ревью | — (—) |
| Блокер | naif.jpl.nasa.gov закрыт в облачной среде (403) — нужен для DE440s, шаг 2 |
| Следующий шаг | G17-S1: tzdata 2026f и GeoNames завендорены (data/vendor, манифест SHA-256), сверка backzone сделана (TZD-002). Дальше: golden timeplace по съёму astro.com, затем _ephem.py (Skyfield+DE440s). Карточка docs/current/G17-S1-план.md. PASS = зелёные make slice-check и make verify. |

Подробная карта — `docs/05_roadmap.md`. Источник статуса — `docs/current/ROADMAP_STATUS.yaml`.
