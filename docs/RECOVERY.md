# Восстановление работы с нуля

**Дата:** 2026-09-12 · **Для:** ситуации, когда потерян компьютер или доступ к учётной записи

---

## ⛔ Сначала прочтите это

**Вся работа по Луноре за последние недели не сохранена в GitHub.**

| Папка | Размер | Файлов | В git? |
|---|---|---|---|
| `docs/` — все документы гейта, прототип, исследования | 2,5 МБ | 69 | **нет** |
| `research/` — рыночные исследования | 61 МБ | 37 | **нет** |
| `.claude/` — настройки запуска | 4 КБ | 1 | **нет** |
| `frontend/public`, `frontend/src/assets` | 56 КБ | 5 | **нет** |

Последний коммит — `3b65f09 docs: добавить ROADMAP_BOARD.md`. Всё, что сделано после, существует **в одном экземпляре на этом компьютере**.

Если диск умрёт сегодня — потеряны: прототип на 183 экрана, структура 44 ячеек, модель данных, правила безопасности, три сквозных среза, четыре рыночных исследования.

🔒 **Первое действие — не читать дальше, а сохранить.** Команда в конце документа.

---

## Где что лежит

### Код и документы

```
/Users/Lunera/Projects/lunora            основной репозиторий
├── docs/grillmax/                        всё по гейту G7
│   ├── wireframes/02-report.html         прототип, 183 экрана, ~800 КБ
│   ├── cell-structure.md                 структура 44 ячеек
│   ├── data-model.md                     модель данных
│   ├── safety-rules.md                   правила безопасности
│   ├── consultation-structure.md         структура разборов
│   ├── structure-proposal.md             предложение на ревью
│   ├── slice-character.md                срез «Характер»
│   ├── slice-crisis.md                   срез «Кризисы»
│   ├── theme-matrix.md                   матрица тем и школ
│   └── _SESSION.json                     состояние гейтов
└── research/                             рыночные исследования
```

### Рабочая папка сессий

```
/Users/Lunera/Yandex.Disk.localized/VPN   90 МБ
```

✅ Эта папка синхронизируется с Яндекс.Диском — то есть уже в облаке. Проверьте, что синхронизация включена и завершена.

### Настройки Claude Code

```
/Users/Lunera/.claude/skills/grillmax                            скилл проработки проекта
/Users/Lunera/.claude/projects/-Users-Lunera-Yandex-Disk-localized-VPN/
├── memory/                                                      15 файлов памяти
└── 009447c1-110a-4f2f-9c23-5c6eecc0e5f6.jsonl                   транскрипт этой сессии
```

⚠️ Память и скилл **не в облаке и не в git**. При потере компьютера они пропадают.

### Внешние ресурсы

| Что | Адрес | Доступ |
|---|---|---|
| Репозиторий | `git@github.com:tyshenkoanton-eng/lunora.git` | ключ SSH на этом компьютере |
| Прототип | `claude.ai/code/artifact/bb6f7100-1a36-4ff2-bd1e-31ff6323e738` | привязан к учётной записи Claude |
| Сервер проекта | `lun-ra.ru` | — |
| Панель разработки | `dev.lunera.org`, VPS `91.196.35.124`, ключ `mark_prod_ed25519` | ключ на этом компьютере |

---

## Что делать при потере компьютера

### Шаг 1. Проверить, что уцелело

| Источник | Что вернёт |
|---|---|
| GitHub | код и документы **на момент последнего пуша** |
| Яндекс.Диск | папка `VPN` целиком |
| Claude — галерея артефактов | прототип, если учётная запись жива |

### Шаг 2. Развернуть на новой машине

```bash
# 1. поставить Claude Code
npm install -g @anthropic-ai/claude-code

# 2. забрать репозиторий
mkdir -p ~/Projects && cd ~/Projects
git clone git@github.com:tyshenkoanton-eng/lunora.git
# если ключ SSH утерян — через HTTPS:
# git clone https://github.com/tyshenkoanton-eng/lunora.git

# 3. восстановить Яндекс.Диск — поставить клиент и дождаться синхронизации

# 4. запустить
cd ~/Projects/lunora && claude
```

### Шаг 3. Восстановить контекст

Память и скилл не переносятся автоматически. Скажите новому сеансу:

> Прочитай `docs/grillmax/INDEX.md`, `docs/grillmax/_SESSION.json` и `docs/RECOVERY.md`. Мы на гейте G7, работаем над прототипом `docs/grillmax/wireframes/02-report.html`.

Восстановить память вручную: `/Users/Lunera/.claude/projects/<путь>/memory/`, 15 файлов, перечислены в `MEMORY.md`.

### Шаг 4. Если заблокирована учётная запись Claude

Прототип перестанет открываться по ссылке, но **файл цел**: `docs/grillmax/wireframes/02-report.html`.

Чтобы посмотреть его без Claude:

```bash
cd ~/Projects/lunora/docs/grillmax/wireframes
python3 -m http.server 8765
# открыть http://localhost:8765/02-report.html
```

⚠️ Файл — фрагмент без `<head>`, поэтому в браузере кириллица поедет. Обёртка:

```bash
{ printf '<!doctype html><html><head><meta charset="utf-8"></head><body>\n'; \
  cat 02-report.html; printf '\n</body></html>\n'; } > view.html
```

Новая учётная запись Claude Code ставится как в шаге 2 и работает с теми же файлами.

---

## Что сделать прямо сейчас

### 1. Сохранить несохранённое

```bash
cd ~/Projects/lunora
git add docs .claude frontend ROADMAP_BOARD.md
git commit -m "docs: работа по гейту G7 — прототип, структура разборов, модель данных"
git push
```

⚠️ `research/` весит 61 МБ — если не нужен в репозитории, добавьте в `.gitignore` и храните на Яндекс.Диске.

### 2. Скопировать память и скилл в репозиторий

```bash
mkdir -p ~/Projects/lunora/.claude-backup
cp -r ~/.claude/skills/grillmax ~/Projects/lunora/.claude-backup/
cp -r "/Users/Lunera/.claude/projects/-Users-Lunera-Yandex-Disk-localized-VPN/memory" ~/Projects/lunora/.claude-backup/
```

### 3. Взять за правило

Пушить после каждого дня работы. Одна команда:

```bash
cd ~/Projects/lunora && git add -A && git commit -m "работа $(date +%F)" && git push
```

---

## Чего не вернуть ничем

| Что | Почему |
|---|---|
| Переписка этой сессии | лежит в `.jsonl` на диске, в облако не уходит |
| Опубликованные версии артефакта | живут в учётной записи Claude |

Первое можно сохранить руками: скопировать `.jsonl` в репозиторий. Второе — не нужно, файл прототипа и есть источник.
