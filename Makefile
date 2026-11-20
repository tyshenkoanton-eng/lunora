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

slice-check:    ## проверки текущего слайса (заполняется из карточки слайса)
	@echo "TODO: подставь проверки текущего слайса (конкретные тесты/команды PASS)"

docs:           ## только дисциплина документов
	python scripts/docs_discipline.py --docs docs

board:          ## сгенерировать ROADMAP_BOARD.md из ROADMAP_STATUS.yaml
	python scripts/board_gen.py
