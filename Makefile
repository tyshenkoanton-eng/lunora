# Единый вход проверок (Lunera). PASS слайса = зелёный `make verify`.
# Воспроизводимость: любой в любой сессии прогоняет те же команды.
# Рецепты — с ТАБУЛЯЦИЕЙ. Подставь реальные команды проекта под <...>.

.PHONY: setup setup-oracle verify slice-check slice-check-s1 slice-check-s2a slice-check-s2c slice-check-s2b slice-check-s2d slice-check-s2e slice-check-s2f slice-check-s3a slice-check-s3b spike-full docs board

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

slice-check: slice-check-s1 slice-check-s2a slice-check-s2c slice-check-s2b slice-check-s2d slice-check-s2e slice-check-s2f slice-check-s3a  ## G17 накопительно: закрытые слайсы не должны покраснеть

slice-check-s1: ## G17-S1: эфемериды + время/пояса (docs/gates/G17-S1-close.md)
	python scripts/spike/ephem_data_check.py         # DE440s на месте, SHA-256 = §0.5, Skyfield 1.55, tzdata 2026f
	pytest -q tests/test_golden_audit.py tests/test_timeplace.py tests/test_tz_crosscheck.py tests/test_tz_disputes.py tests/test_vendor_manifest.py tests/test_geonames_vendor.py tests/test_tz_backzone.py tests/test_ephem_data.py tests/test_ephem.py tests/test_golden_ephemeris.py tests/test_golden_timeplace.py tests/test_golden_time_tolerance.py tests/test_stability.py tests/test_places.py
	pytest -q tests/diff -m "not full"                # дифф с оракулом SE на фикс. выборке (seed)
	python scripts/spike/vendor_check.py
	python scripts/spike/golden_audit.py tests/golden --require-active

slice-check-s2a: ## G17-S2a: каркас движков + нумерология (docs/current/G17-S2-план.md)
	pytest -q tests/engines
	python scripts/spike/golden_audit.py tests/golden --require-active

slice-check-s2c: ## G17-S2c: западный движок (docs/current/G17-S2-план.md)
	pytest -q tests/engines/test_golden_western.py tests/engines/test_western_rules.py
	python scripts/spike/golden_audit.py tests/golden --require-active

slice-check-s2b: ## G17-S2b: движок Ба-Цзы (docs/current/G17-S2-план.md)
	pytest -q tests/engines/test_golden_bazi.py tests/engines/test_bazi_rules.py tests/diff/test_bazi_oracle.py
	python scripts/spike/golden_audit.py tests/golden --require-active

slice-check-s2d: ## G17-S2d: ведический движок (docs/current/G17-S2-план.md)
	pytest -q tests/engines/test_golden_vedic.py tests/engines/test_vedic_rules.py tests/diff/test_vedic_oracle.py
	python scripts/spike/golden_audit.py tests/golden --require-active

slice-check-s2e: ## G17-S2e: рантайм на движках lunora.engines.*, оракулы вне рантайма (docs/gates/G17-S2e-close.md)
	pytest -q tests/test_calc.py tests/test_serialize.py tests/test_geocode.py tests/test_runtime_no_oracles.py tests/engines/test_no_oracle_imports.py
	python scripts/spike/golden_audit.py tests/golden --require-active

slice-check-s2f: ## G17-S2f: доводка интеграции P3 (F01–F11) сквозь calculate/onboard (docs/gates/G17-S2f-close.md); настоящая PostgreSQL обязательна
	pytest -q tests/integration/test_p3_sweep.py tests/integration/test_product_contract.py tests/test_stability.py tests/engines/test_result_contract.py
	LUNORA_REQUIRE_PG=1 pytest -q tests/integration/test_onboard_p3.py
	python scripts/spike/golden_audit.py tests/golden --require-active

slice-check-s3a: ## G17-S3a: адаптер Telegram Stars, правила S1–S5 (docs/current/G17-S3-план.md); настоящая PostgreSQL обязательна
	LUNORA_REQUIRE_PG=1 pytest -q tests/payments

slice-check-s3b: ## офлайн-гарды LLM: приватность пакета (152-ФЗ) + дрейф порогов бюджета; без сети/ключей/артефакта замера. НЕ в накопительном slice-check: слайс S3b не открыт
	if [ -f tests/test_llm_privacy.py ]; then PYTHONPATH=src pytest -q tests/test_llm_privacy.py; else echo "slice-check-s3b: нет набора tests/test_llm_privacy.py — пропущен"; fi
	if [ -f tests/test_llm_portrait_privacy.py ]; then PYTHONPATH=src pytest -q tests/test_llm_portrait_privacy.py; else echo "slice-check-s3b: нет набора tests/test_llm_portrait_privacy.py — пропущен"; fi
	if [ -f tests/test_llm_cost_thresholds.py ]; then PYTHONPATH=src pytest -q tests/test_llm_cost_thresholds.py; else echo "slice-check-s3b: нет набора tests/test_llm_cost_thresholds.py — пропущен"; fi
	if [ -f tests/test_llm_cost.py ]; then PYTHONPATH=src pytest -q tests/test_llm_cost.py; else echo "slice-check-s3b: нет набора tests/test_llm_cost.py — пропущен"; fi
	if [ -f docs/current/spike/llm_cost.json ]; then python scripts/spike/llm_cost.py --check; else echo "slice-check-s3b: нет артефакта docs/current/spike/llm_cost.json — сверка с порогами ждёт живого замера"; fi

spike-full:     ## долгие прогоны вручную; отчёт — docs/current/spike/ephem-oracle-дифф.md
	pytest -q tests/diff -m full
	python scripts/spike/ephem_diff_report.py --n 3000

docs:           ## только дисциплина документов
	python scripts/docs_discipline.py --docs docs

board:          ## сгенерировать ROADMAP_BOARD.md из ROADMAP_STATUS.yaml
	python scripts/board_gen.py
