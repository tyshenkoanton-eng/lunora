<!-- reference -->
# WORKLOG G17-S2a — архив журнала слайса (закрыт 2026-11-21)

<!-- Главный антидот потере контекста. Обновляй на КАЖДОМ значимом шаге.
     Новый агент/сессия: прочитай последние записи и продолжи с «Следующий шаг».
     Закрыли слайс → итог в docs/gates/ + changelog, обнули файл под новый слайс. -->

**Слайс:** G17-S2a · Каркас движков `lunora.engines` + нумерология (первый под-слайс G17-S2, точка P3). Карточка — [G17-S2-план.md](../current/G17-S2-план.md). Журнал G17-S1 — [G17-S1-worklog.md](G17-S1-worklog.md).

---

## 2026-11-21 — G17-S2a, шаг 0: слайс открыт, решения Антона, чек-листы съёма
- **Сделал:** Антон утвердил план G17-S2 и снял шесть вопросов — записал в карточку (раздел «Решения Антона»). ROADMAP_STATUS → `G17-S2a`, в работе; CURRENT_STATE обновлён; журнал S1 перенесён в `docs/gates/G17-S1-worklog.md` (ссылки поправлены), этот файл начат заново. Подготовил два чек-листа съёма для параллельной работы Антона: [Ба-Цзы, S2b](../current/spike/съём-бацзы-чек-лист-S2b.md) и [Jagannatha Hora, S2d](../current/spike/съём-jh-чек-лист-S2d.md).
- **S2c — проверка бланков S1:** на бланках astro.com карт A (`F-…` карта A, SHA-256 `f426831e…`) и D (Placidus, SHA-256 `3e1c6027…`) сетка аспектов с орбисами в целых градусах и пометкой A/S есть и читается. Нового съёма аспектов не прошу — расшифрую из этих оригиналов в S2c.
- **Микрорешения:**
  - координаты и пояс в чек-листах — из `places_min.yaml` (GeoNames), а не условные из §0.5, потому что golden считается по place_id;
  - в JH место вводится вручную (координаты + пояс, DST = 0), а не из атласа JH — иначе вход эталона и наш разойдутся до расчёта;
  - журнал S1 не удалил, а перенёс в `docs/gates/`, потому что close-record S1 ссылается на ход работ.
- **Следующий шаг:** каркас `lunora.engines` — контракт результата, слой `engines` в `golden_audit`, раннер, цель `slice-check` S2a.
- **Проверки:** `docs_discipline`, `make board`.

## 2026-11-21 — G17-S2a, шаг 1: каркас `lunora.engines` — контракт результата, запрет оракулов, slice-check
- **Сделал:** тесты раньше кода (`tests/engines/test_result_contract.py` — красный, затем зелёный). Пакет `src/lunora/engines/`: `Result` (значение | `not_computed` с причиной из ENGINE-SPEC §1.2, `Rule(id, semver)`, `stability` ∈ stable/range/undetermined/convention, неизменяемый) — минимальный контракт по решению Антона №5. Статический тест `test_no_oracle_imports.py`: `lunora.engines` не импортирует swisseph, PyJHora, cnlunar, lunar-python, timezonefinder (по AST, ловит и ленивые импорты). `make slice-check` стал накопительным: `slice-check-s1` (проверки S1 без изменений) + `slice-check-s2a`; тест `test_slice_check_runs_ephemeris_checks` теперь ищет проверки S1 в `slice-check-s1` и требует, чтобы `slice-check` от него зависел.
- **Микрорешения:**
  - слои движков (`western`, `vedic`, `bazi`, `numerology`) в `golden_audit` уже были с S1 — новый слой не заводил;
  - `slice-check` накопительный, а не только S2a, потому что закрытые слайсы не должны молча покраснеть;
  - `value` и `not_computed` взаимоисключающие на уровне конструктора: частичный результат под видом полного не собрать (fail closed).
- **Следующий шаг:** golden нумерологии `NUMEROLOGY-RULES.md` §9.2 (27 кейсов) + раннер, красные до движка.
- **Проверки:** `pytest tests/engines` (10 passed), `make slice-check` зелёный, `ruff check`.

## 2026-11-21 — G17-S2a, шаг 2: golden нумерологии §9.2 + раннер (красные до движка)
- **Сделал:** `tests/golden/numerology/numerology-rules-9-2.yaml` — 27 кейсов §9.2 + `G-N06-space` (тот же результат через пробел), 27 active + G-S04 `known_gap`; evidence [numerology-rules-9-2.md](../../tests/golden/evidence/numerology-rules-9-2.md) с SHA-256 спеки. Раннер `tests/engines/test_golden_numerology.py`: полнота набора, сверка по путям, G-S04 — только с закрытым fixture (`LUNORA_PRIVATE_NUMEROLOGY_FIXTURE`). Сейчас красный: модуля `lunora.engines.numerology` нет.
- **Микрорешения:**
  - ожидания расшифрованы из таблицы §9.2 без пересчёта — эталон не должен знать о коде;
  - G-D09/G-D10 ждут `PSYCHOMATRIX.not_computed = rule_not_formalized` + путь и число рождения (решение №2); значения «+19» из §9.2 оставил справкой в evidence;
  - G-D08 «флаг проверки 19» → `KARMIC_DEBT_CHECK.not_computed = out_of_v1`: §4.3 выводит проверку из v1, а таблица §9.2 её упоминает — расхождение внутри спеки, вынесу в close-record;
  - G-N11: латинская «o» на позиции 6 (как в примере 15 §1.5), а не 4.
- **Следующий шаг:** движок `lunora.engines.numerology` до зелёного раннера + юнит-тесты по примерам §1.5, §4.1, §4.2 и property-тесты.
- **Проверки:** `golden_audit --require-active` (active: 138, known_gap: 1).

## 2026-11-21 — G17-S2a, шаг 3: движок нумерологии `lunora.engines.numerology` (зелёный)
- **Сделал:** движок по NUMEROLOGY-RULES.md: нормализация `norm/1` (NFC, разделители, алфавит, жёсткие/мягкие проверки §1.3–1.4, fail closed), таблица букв `balliett_ru_33/1`, свёртки `reduce_free`/`reduce_digit` (33→6, остановка 11/22), числа имени сплошь (§3.2–3.3), числа даты (§4.1–4.3), квадрат Пифагора (§5: рабочие числа, девять ячеек, восемь линий, семиуровневая шкала, влияние линий §5.5 и переходы §7.2 — пометки поверх базового квадрата), личные циклы. Каждая величина — `Result` с правилом и версией. Квадрат `post2000` — `rule_not_formalized` (решение №2); `KARMIC_DEBT_CHECK` — `out_of_v1`. 27 golden §9.2 + юнит `test_numerology_rules.py` (примеры §1.5, fail closed, таблица, свёртки, property-тесты с фикс. seed: Г+С=Е, остановки свёртки, 9 ячеек у всех дат 1900–1999).
- **Микрорешения:**
  - `MATURITY` без ФИО — `Result` со значением `None` (§4.3 «null»), а не `not_computed`: причины «no_name» в §1.2 нет, а пустое число зрелости — это не отказ движка;
  - `_normalize_field` различает латиницу/кириллицу/прочее по unicodedata — ловит латинские двойники (mixed_script) и кириллицу вне русского алфавита (unsupported_letter) по позиции;
  - рантайм `calc/numerology.py` пока не трогаю — переключение в S2d (решение №4).
- **Следующий шаг:** close-record S2a + changelog + CURRENT_STATE, PR. Расхождение §9.2↔§4.3 про «флаг 19» в G-D08 — в close-record.
- **Проверки:** `make verify` (652 passed, 18 skipped), `make slice-check` зелёный, `golden_audit` active 138 / known_gap 1, `ruff`.

## 2026-11-21 — G17-S2a, шаг 4: close-record S2a (PASS), статус → S2b
- **Сделал:** close-record [G17-S2a-close.md](../gates/G17-S2a-close.md), запись в changelog, CURRENT_STATE и ROADMAP_STATUS → `G17-S2b` (ждёт съёма Антона), board перегенерирован. Открытые пункты (не блокируют): расхождение §9.2↔§4.3 про «флаг 19» (G-D08), G-S04 закрытый fixture.
- **Следующий шаг:** PR S2a в main; затем G17-S2b начинается, когда Антон пришлёт съём двух калькуляторов Ба-Цзы.
- **Проверки:** `make verify` зелёный, `make board`, `docs_discipline` OK.
