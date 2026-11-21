# Единый вход проверок (Lunera). PASS слайса = зелёный `make verify`.
# Воспроизводимость: любой в любой сессии прогоняет те же команды.
# Рецепты — с ТАБУЛЯЦИЕЙ. Подставь реальные команды проекта под <...>.

.PHONY: setup verify slice-check docs board

setup:          ## установка зависимостей/окружения
	pip install -e ".[dev]"
	cd frontend && npm ci

verify:         ## полная проверка: линт + типы + тесты + дисциплина доков
	ruff check .
	pytest -q
	python scripts/docs_discipline.py --docs docs

slice-check:    ## G17-S1: эфемериды + время/пояса (карточка docs/current/G17-S1-план.md)
	pytest -q tests/test_golden_audit.py tests/test_timeplace.py tests/test_tz_crosscheck.py tests/test_tz_disputes.py
	python scripts/spike/golden_audit.py tests/golden --require-active

docs:           ## только дисциплина документов
	python scripts/docs_discipline.py --docs docs

board:          ## сгенерировать ROADMAP_BOARD.md из ROADMAP_STATUS.yaml
	python scripts/board_gen.py
