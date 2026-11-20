# Лунора — индекс документации

Точка входа. **Источник правды по статусу — `docs/CURRENT_STATE.md`.**
Карта документов: что где искать и что читать под какую нужду. Проработка (Discovery) ведена по ГРИЛЛ МИ МАКС v4 и лежит в `docs/grillmax/` — её не дублируем, ссылаемся.

## Статус (живое «где мы»)
| Документ | Что внутри |
|---|---|
| `CURRENT_STATE.md` | Где мы сейчас — тонкий, источник правды |
| `current/ROADMAP_STATUS.yaml` | Статус карты L→G→S→R (источник; витрина `../ROADMAP_BOARD.md` генерируется) |
| `current/WORKLOG.md` | Журнал текущего слайса (append-only, антидот потере контекста) |
| `gates/` | Закрытые этапы (по одному файлу на событие) |
| `changelog.md` | Летопись: дата · scope · SHA · verdict |

## Справочник (стабильное «что и как») — ведёт в Discovery-пакет
| Слот | Где в проекте |
|---|---|
| Продукт | `grillmax/01_context.md`, `grillmax/02_problem.md`, `grillmax/04_product.md` |
| Аудитория | `grillmax/03_audience.md` |
| Экономика | `grillmax/05_business.md` |
| Бренд | `grillmax/06_brand.md`, `grillmax/brand.tokens.json` |
| UX / экраны | `grillmax/06_ux.md`, `grillmax/07_mockups.md`, `grillmax/09_visual.md`, `grillmax/tokens.json` |
| Архитектура | `grillmax/ARCHITECTURE.md`, `grillmax/API-КОНТРАКТ.md`, `grillmax/ENGINE-SPEC-РАСЧЕТ.md` |
| Аналитика / запуск | `grillmax/14_analytics.md`, `grillmax/15_launch.md` |
| Дорожная карта + вердикт | `grillmax/16_roadmap.md` |
| Решения (ADR) | `grillmax/ADR-001-эфемериды.md`, `grillmax/ADR-002-клиенты-и-движок.md`, `grillmax/ADR-003-token-driven-frontend.md`, `grillmax/РЕШЕНИЯ-БЛОКЕРЫ.md` |
| Право / данные | `grillmax/legal/`, `grillmax/ПРАВОВЫЕ-ТЕКСТЫ.md` |
| Риски | `grillmax/RISKS.md` |
| Полный навигатор Discovery | `grillmax/INDEX.md` |
| Методология (скилл) | `grillmax/ГРИЛЛ-МИ-МАКС-v4/` |

## Канон
| Документ | Что внутри |
|---|---|
| `LUNERA_STANDARDS.md` | Общие правила Lunera (одинаков во всех проектах) |
| `../CLAUDE.md` | Стартовые правила агента + проектные жёсткие правила |
