# Единый вход проверок (Lunera). PASS слайса = зелёный `make verify`.
# Воспроизводимость: любой в любой сессии прогоняет те же команды.
# Рецепты — с ТАБУЛЯЦИЕЙ. Подставь реальные команды проекта под <...>.

.PHONY: setup setup-oracle verify slice-check spike-full docs board

setup:          ## установка зависимостей/окружения + эфемериды DE440s (SHA-256 из манифеста)
	pip install -e ".[dev]"
	python scripts/fetch_vendor.py --group runtime
	cd frontend && npm ci

setup-oracle:   ## тестовые оракулы: pyswisseph и DE440 для него (дифф-тесты, slice-check)
	pip install -e ".[dev,oracle]"
	python scripts/fetch_vendor.py --group oracle

verify:         ## полная проверка: линт + типы + тесты + дисциплина доков
	ruff check .
	pytest -q
	python scripts/docs_discipline.py --docs docs

slice-check:    ## G17-S1: эфемериды + время/пояса (карточка docs/current/G17-S1-план.md)
	python scripts/spike/ephem_data_check.py         # DE440s на месте, SHA-256 = §0.5, Skyfield 1.55, tzdata 2026f
	pytest -q tests/test_golden_audit.py tests/test_timeplace.py tests/test_tz_crosscheck.py tests/test_tz_disputes.py tests/test_vendor_manifest.py tests/test_geonames_vendor.py tests/test_tz_backzone.py tests/test_ephem_data.py tests/test_ephem.py tests/test_golden_ephemeris.py
	pytest -q tests/diff -m "not full"                # дифф с оракулом SE на фикс. выборке (seed)
	python scripts/spike/vendor_check.py
	python scripts/spike/golden_audit.py tests/golden --require-active

spike-full:     ## долгие прогоны вручную; отчёт — docs/current/spike/ephem-oracle-дифф.md
	pytest -q tests/diff -m full
	python scripts/spike/ephem_diff_report.py --n 3000

docs:           ## только дисциплина документов
	python scripts/docs_discipline.py --docs docs

board:          ## сгенерировать ROADMAP_BOARD.md из ROADMAP_STATUS.yaml
	python scripts/board_gen.py
