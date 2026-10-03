# Восстановление работы

**Обновлено:** 2026-10-02 · Два сценария: пропал компьютер и пропал доступ к Claude. Они не связаны — читайте тот, который случился.

---

## 🔑 Главное: что защищено, а что нет

| Что | Где лежит | Теряется при потере компа / блокировке Claude? |
|---|---|---|
| Прототип `docs/grillmax/wireframes/02-report.html` (~1 МБ) | **GitHub (git)** | ✅ нет |
| Все документы гейта `docs/grillmax/*.md` + `_SESSION.json` | **GitHub (git)** | ✅ нет |
| Код проекта (`src`, `frontend`, `migrations`, `deploy`) | **GitHub (git)** | ✅ нет |
| Этот файл `docs/RECOVERY.md` | **GitHub (git)** | ✅ нет |
| `research/` — рыночные исследования | только Яндекс.Диск | ⚠️ да, если Диск не синхронизирован |
| Память Claude (`~/.claude/projects/.../memory/`) | только компьютер + Яндекс.Диск | ⚠️ да |
| Транскрипт сессии (`.jsonl`) | только компьютер + Яндекс.Диск | ⚠️ да |
| SSH-ключ к GitHub, ключ сервера `mark_prod_ed25519` | только компьютер | ⚠️ да |

**Вывод.** Всё, что в git, не зависит ни от компьютера, ни от аккаунта Claude: GitHub хранит это на своих серверах. Реальная зона риска — `research/`, память, транскрипт и ключи: они существуют в одном-двух экземплярах. Их и надо держать продублированными (см. раздел «Что держать в порядке»).

---

# Сценарий 1. Потерян компьютер

Сломался диск, украли ноутбук, залили кофе. Доступ к Claude при этом есть.

## Шаг 1. Поставить инструменты

```bash
# Node.js должен быть установлен
npm install -g @anthropic-ai/claude-code

# клиент Яндекс.Диска — скачать с disk.yandex.ru и войти
```

## Шаг 2. Забрать код

```bash
mkdir -p ~/Projects && cd ~/Projects
git clone git@github.com:tyshenkoanton-eng/lunora.git
```

Если ключ SSH остался на старом компьютере — через HTTPS:

```bash
git clone https://github.com/tyshenkoanton-eng/lunora.git
```

Логин — учётная запись GitHub, пароль — токен из настроек GitHub (Developer settings → Personal access tokens).

После клонирования проверьте актуальную ветку работы:

```bash
cd lunora
git fetch origin
git branch -a          # рабочая ветка последней сессии — claude/recovery-lost-computer-a0vl5l
```

## Шаг 3. Вернуть то, чего нет в GitHub

Дождаться синхронизации Яндекс.Диска, затем:

```bash
Д="$HOME/Yandex.Disk.localized/Лунора"

# исследования (в git их нет)
cp -R "$Д/research" ~/Projects/lunora/

# память Claude Code
mkdir -p ~/.claude/projects/-Users-Lunera-Yandex-Disk-localized-VPN
cp -R "$Д/claude-настройки/memory" ~/.claude/projects/-Users-Lunera-Yandex-Disk-localized-VPN/

# скилл проработки проекта
mkdir -p ~/.claude/skills
cp -R "$Д/claude-настройки/grillmax" ~/.claude/skills/
```

⚠️ Путь `-Users-Lunera-Yandex-Disk-localized-VPN` — это зашифрованное имя рабочей папки. Если имя пользователя на новой машине другое, папка памяти будет называться иначе: запустите Claude один раз, посмотрите, какая папка появилась в `~/.claude/projects/`, и кладите память туда.

## Шаг 4. Запустить и вернуть контекст

```bash
cd ~/Projects/lunora && claude
```

Первым сообщением:

> Прочитай `docs/grillmax/INDEX.md`, `docs/grillmax/_SESSION.json` и `docs/RECOVERY.md`. Мы на гейте G7, работаем над прототипом `docs/grillmax/wireframes/02-report.html`. Обращайся ко мне Антон, рассуждай по-русски.

## Шаг 5. Проверить, что всё на месте

```bash
cd ~/Projects/lunora
ls -la docs/grillmax/wireframes/02-report.html   # прототип, ~1 МБ
ls docs/grillmax/*.md | wc -l                    # около 50 документов
ls ~/.claude/projects/*/memory/*.md | wc -l      # файлы памяти (если вернули с Диска)
```

---

# Сценарий 2. Потерян доступ к Claude

Заблокирована учётная запись, кончилась подписка, сервис недоступен. Компьютер при этом цел.

## Что происходит

| Что | Состояние |
|---|---|
| Файлы проекта и прототип | **целы**, лежат в git локально |
| Прототип как файл | **цел**: `docs/grillmax/wireframes/02-report.html` |
| Прототип по ссылке `claude.ai/.../artifact/...` | **недоступен** |
| Память Claude | цела на диске, но без Claude бесполезна |
| История переписки | цела в `.jsonl`, читается как текст |

🔑 Работа не потеряна. Потерян инструмент, которым её делали. Весь проект — обычный текст и HTML, они открываются без Claude.

## Шаг 1. Открыть прототип без Claude

Файл хранится как фрагмент без заголовка страницы — без обёртки браузер покажет кракозябры вместо кириллицы. Собираем просматриваемую версию:

```bash
cd ~/Projects/lunora/docs/grillmax/wireframes

{ printf '<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head><body>\n'; \
  cat 02-report.html; \
  printf '\n</body></html>\n'; } > view.html

python3 -m http.server 8765
```

Открыть `http://localhost:8765/view.html` — прототип работает целиком, ничего больше не требуется.

Чтобы он открылся не на пустом экране, а на нужном шаге, можно заранее задать стартовый экран — добавить в `<head>` обёртки строку (ключ экрана из реестра, например `obName` или `profile`):

```html
<script>try{localStorage.setItem("lunora_screen","obName")}catch(e){}</script>
```

## Шаг 2. Восстановить доступ или сменить инструмент

**Если дело в подписке или блокировке:** новая учётная запись Claude ставится поверх тех же файлов, ничего переносить не нужно.

```bash
npm install -g @anthropic-ai/claude-code
cd ~/Projects/lunora && claude
```

Память при этом сохраняется — она лежит в `~/.claude/projects/`, а не в облаке Claude.

**Если нужен другой инструмент:** проект не привязан к Claude ничем, кроме удобства. Документы — обычный текст, прототип — обычный HTML. Любой редактор или другой помощник продолжит с того же места.

## Шаг 3. Прочитать историю работы

Переписка лежит в `Яндекс.Диск/Лунора/claude-настройки/транскрипт-сессии.jsonl`. Вытащить текст:

```bash
python3 - <<'PY'
import json
with open('транскрипт-сессии.jsonl') as f:
    for line in f:
        try: d = json.loads(line)
        except: continue
        m = d.get('message', {})
        c = m.get('content')
        if isinstance(c, str) and c.strip():
            print(f"\n=== {m.get('role','?')} ===\n{c[:2000]}")
PY
```

---

# Что держать в порядке

Цель — чтобы реальная зона риска (то, чего нет в git) всегда была продублирована.

| Действие | Когда | Закрывает |
|---|---|---|
| `git add -A && git commit -m "работа $(date +%F)" && git push` | после каждого дня работы | прототип, документы, код |
| копировать `research/` и память на Яндекс.Диск и проверять синхронизацию | раз в неделю | исследования, память |
| копировать транскрипт `.jsonl` на Яндекс.Диск | раз в месяц | история сессий |

### Как закрыть дыру надёжнее (рекомендуется)

Пока `research/`, память и транскрипт живут только на компьютере и Яндекс.Диске — это единственная точка отказа. Чтобы убрать её совсем, положите их тоже под git (тогда GitHub хранит всё):

```bash
cd ~/Projects/lunora
# снимок памяти и скилла рядом с проектом
mkdir -p .recovery-backup
cp -R ~/.claude/skills/grillmax .recovery-backup/
cp -R ~/.claude/projects/-Users-Lunera-Yandex-Disk-localized-VPN/memory .recovery-backup/
# research можно взять в git или оставить на Диске — если берёте, учтите размер
git add .recovery-backup research
git commit -m "backup: память, скилл, исследования" && git push
```

Если `research/` велик и не нужен в основном репозитории — оставьте его на Яндекс.Диске, но тогда следите за синхронизацией вручную.

## Чего не покрывают копии

| Что | Почему | Что делать |
|---|---|---|
| Ключ SSH к GitHub | лежит только на компьютере | завести токен в GitHub заранее |
| Ключ к серверу `mark_prod_ed25519` | то же | хранить копию в менеджере паролей |
| Опубликованные версии артефакта | живут в учётной записи Claude | не важно: источник — файл в git |

---

# Ориентировка

| Что | Где |
|---|---|
| Репозиторий | `git@github.com:tyshenkoanton-eng/lunora.git` |
| Основная ветка | `main` |
| Рабочая ветка последней сессии | `claude/recovery-lost-computer-a0vl5l` (PR в `main`) |
| Рабочая копия | `~/Projects/lunora` |
| Резервная копия | `~/Yandex.Disk.localized/Лунора` |
| Прототип, файл | `docs/grillmax/wireframes/02-report.html` |
| Прототип, ссылка-артефакт | привязана к аккаунту Claude; источник истины — файл в git |
| Состояние гейтов | `docs/grillmax/_SESSION.json` |
| Индекс документов | `docs/grillmax/INDEX.md` |
| Сервер проекта | `lun-ra.ru` |
| Панель разработки | `dev.lunera.org`, VPS `91.196.35.124`, ключ `mark_prod_ed25519` |
