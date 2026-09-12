# Модель данных Лунора: от расчёта до текста

**Дата:** 2026-09-08 · **Версия:** 3 · **Статус:** [РЕШЕНИЕ] каноническая модель · контракт заморожен

Контракт между расчётным движком, интерпретационным слоем, языковой моделью и интерфейсом.

⚠️ Это единственное описание модели. Предыдущая редакция состояла из основной схемы и списка поправок внизу — по такому документу два разработчика реализовали бы разные контракты, и оба были бы правы.

---

## Принцип одной строкой

> **Signal** — что рассчитано. **Evidence** — почему это важно внутри метода. **Claim** — что это значит про человека. **Relation** — как соотносится с другими системами. **Narrative Plan** — что и в каком порядке рассказать. **LLM** — только как это сформулировать.

---

## Цепочка

```
InputSnapshot
      ↓
MethodProfile
      ↓
   Signal
      ↓
  Evidence
      ↓
   Claim
      ↓
 CellBundle          система × раздел
      ↓
SectionBundle        весь раздел
      ├── CrossSystemRelation
      └── SynthesisCluster
      ↓
NarrativePlan
      ↓
     LLM
      ↓
NarrativeRender
      ↓
Тема · Школа · Кризисы · Периоды · Почему · Приложение
```

⚠️ **Evidence появляется до Claim.** Claim хранит ссылки на доказательства, из-за чего кажется, будто зависимость обратная. Порядок вывода строго: `signals → evidence → claims`.

**Пример прохода:**

| Слой | Содержание |
|---|---|
| Signal | Марс в Скорпионе, собственный знак |
| Evidence | Марс имеет высокую эссенциальную силу, относится к действию и инициативе |
| Claim | Действие запускается без внешнего разрешения |
| Narrative | «Взяться за трудное вам проще, чем долго готовиться» |

---

## Сущности

### 1. Signal

Нижний результат детерминированного расчёта.

🔒 **Signal не содержит интерпретации ни в каком виде.** Он не знает, что важно, что сильно и что чем отменено. «Условие выполнено» — сигнал. «Отмена сработала» — уже доказательство.

```
Signal:
  id · person_report_id · system_id
  method_profile_id · method_profile_version
  technique_id · signal_type
  raw_value · normalized_value
  input_dependencies[]
  calculation_rule_id · calculation_rule_version
  time_scope: natal | period | current | transition
  valid_from · valid_to
  sensitivity: { birth_time, birth_place, name_form, transliteration, method_choice }
  calculation_confidence
  user_visible: false
```

### 2. Evidence

Значение сигнала **внутри выбранной методики**. Здесь появляются сила, условия и отмены.

```
Evidence:
  id · system_id · method_profile_id
  signal_refs[]
  interpretation_rule_id · interpretation_rule_version
  semantic_axis · domain_tags[]

  axis_effect:      supports | weakens | contextualizes | activates | null
  relation_effect:  modifies | cancels | null
  target_refs[]

  strength: major | medium | minor
  conditions[]
  time_scope · confidence
  explainability_short · explainability_advanced
```

⚠️ **Два разных действия, которые раньше были одним полем.**

| Поле | Что описывает | Пример |
|---|---|---|
| `axis_effect` | как доказательство влияет на смысловую ось | Солнце в изгнании ослабляет ось предъявления себя |
| `relation_effect` | как доказательство относится к другому доказательству | правило кендр отменяет трактовку одинокой Луны |

Смешение давало ложное требование: «ослабляет» вынуждено было указывать цель, хотя ослабляет оно ось, а не другое доказательство.

🔒 **Инвариант:**

```
relation_effect != null  →  target_refs непустой
```

### 3. Claim

Одно утверждение о человеке, которое можно показать.

```
Claim:
  id · system_id · method_profile_id

  proposition          ← что утверждается; по нему идёт сравнение систем
  mechanism            ← как это устроено; в сравнении не участвует

  semantic_coordinates:
    domain · facet · construct
    locus:     internal | interpersonal | social
    phase:     initiation | execution | expression | evaluation
    direction: self_to_world | world_to_self
    valence:   resource | tension | neutral

  claim_class: trait | motivation | capacity | tension | resource |
               preference | relational_pattern | work_pattern |
               temporal_activation | transition

  primary_section_id · secondary_section_ids[]
  evidence_refs[]
  time_scope: stable | natal | current_period | forecast_window
  valid_from · valid_to

  salience:
    grade: major | medium | minor
    reasons[]
    ⚠️ ранг живёт не здесь — см. CellClaimMembership

  confidence:
    data · calculation · interpretation

  method_scope:
    universal_within_system: bool
    school_specific: bool
    profile
  method_consensus: established | contested

  internal_relations: { reinforces[], tensions[], qualifies[] }
  safety_tags[] · terminology_tags[]
  surface_policy: { main_text, why, advanced, hidden }
  status: active | suppressed | insufficient_data
```

#### Утверждение и механизм — разные поля

Вывод «сделанное не присваивается, потому что критерий достаточности привязан к усилию» содержит два утверждения и причинную связь между ними. При сравнении систем это давало ложные схождения.

| Поле | Пример | Участвует в сравнении |
|---|---|---|
| proposition | трудно присвоить сделанное | да |
| mechanism | усилие используется как мера ценности | нет |

#### Три вида уверенности

🔒 Не делать `confidence = 87%`.

| Что | О чём |
|---|---|
| data | насколько надёжны исходные данные |
| calculation | насколько результат устойчив при этих данных и методике |
| interpretation | насколько вывод поддержан доказательствами внутри системы |

⚠️ Это **не вероятность того, что метод объективно верен**.

#### Спорность метода — отдельно от уверенности

Вывод может быть твёрдым внутри выбранной методики и при этом иначе считаться в другой школе той же системы. Это разные вещи, и путать их нельзя: читатель прочтёт «средняя уверенность» как «система не уверена в расчёте».

```
confidence:       { data: high, calculation: high, interpretation: high }
method_scope:     { school_specific: true, profile: zi_ping_structural_v1 }
method_consensus: contested
```

#### Значимость не сравнивается между системами 🔒

Баллы считаются разными движками и сопоставимыми не становятся. `0.94` западной ≠ `0.94` Ба-Цзы.

Межсистемный движок использует только `grade`, `within_cell_rank` и число независимых доказательств внутри своей системы.

### 4. CellBundle

**Одна ячейка = одна система × один раздел.** Текста не содержит.

```
CellBundle:
  id · person_report_id · system_id · section_id
  method_profile_id · method_profile_version

  availability:
    status: AVAILABLE | UNSUPPORTED | INSUFFICIENT_DATA |
            NO_SIGNIFICANT_SIGNAL | SUPPRESSED

  signal_profile:
    grade: strong | normal | weak
    reasons[]

  claim_memberships[]        ← вместо четырёх отдельных массивов
  evidence_refs[]
  featured_claim_id
  required_artifact_refs[]
  generation_constraints · engine_version
```

### 4a. CellClaimMembership

Один вывод живёт в нескольких ячейках, и его важность в каждой своя.

```
CellClaimMembership:
  cell_id · claim_id
  role:      primary | supporting | contextual | temporal
  reuse_mode: full | applied | reference
  within_cell_rank            ← уникален внутри ячейки, ничьих нет
  cell_relevance: major | medium | minor
```

⚠️ **Зачем отдельная сущность.** Вывод «способ достигать — накопление» имеет ранг 1 в ячейке «Ба-Цзы × Работа» и не имеет никакого ранга в ячейке «Ба-Цзы × Характер», где появляется ссылкой. Ранг, лежащий на самом выводе, задавал бы противоречие.

🔑 Здесь же схема начинает **принуждать** к режиму повторного использования: раньше «в характере это ссылка, а не раскрытие» было договорённостью, теперь это поле.

⚠️ **Два измерения, а не одно.** «Может ли система ответить» и «насколько наполнен ответ» — разные вопросы.

| Случай | availability | signal_profile |
|---|---|---|
| нумерология о характере: числа обычные | AVAILABLE | weak · нет необычных конфигураций |
| западная о детях: тема снята политикой | SUPPRESSED | — |
| джйотиш без времени рождения | INSUFFICIENT_DATA | — |
| нумерология о здоровье: инструмента нет | UNSUPPORTED | — |

🔒 `cross_system_relation_refs` в ячейке **нет**: связь по определению соединяет системы, её владелец — строка. Ячейка может иметь обратную ссылку, но не второй источник истины.

### 5. SectionBundle

Строка матрицы как объект. Без неё план темы выбирал бы выводы напрямую из четырёх систем, минуя несуществующую сущность.

```
SectionBundle:
  id · person_report_id · section_id
  cell_refs[]
  relation_refs[]           ← единственный владелец
  synthesis_cluster_refs[]
  temporal_overlay_refs[]
  featured_cluster_id
  divergence_refs[]
```

### 6. CrossSystemRelation

```
CrossSystemRelation:
  id · section_id · semantic_axis
  claim_refs[]
  relation_type: convergence | complement | divergence | non_comparable | no_signal
  same_construct · same_context · same_time_scope
  reconciliation_notes · mapping_confidence · user_visible
```

⚠️ **Зачем non_comparable.** Опаснейшая ошибка сводящего движка — «четыре системы что-то сказали, надо связать». Иногда связывать нечего: одна про склад мышления, другая про активный период. Без этого статуса модель изобретёт красивый ложный мост.

#### Алгоритм разрешения

```
1. Один конструкт по semantic_coordinates?
   нет → non_comparable или complement
2. Один locus и context?
   нет → complement
3. Один phase и time_scope?
   нет → complement
4. Один вывод существенно слабее по grade внутри своей системы?
   да → сохраняется как более слабое свидетельство
5. Противоречие осталось?
   да → divergence
```

🔒 Divergence не разрешается автоматически. Никаких «три системы против одной».

⚠️ Формулировка расхождения: не «решать читателю» — это сдача системы. Правильно: «объединить эти два вывода без натяжки нельзя, поэтому мы сохраняем оба».

### 7. SynthesisCluster

Группирует существующие выводы вокруг одной оси. **Новых утверждений не создаёт и пятой системой не является.**

```
SynthesisCluster:
  id · section_id · semantic_axis
  claim_refs[] · relation_refs[]
  relation_type: convergence | complement | mixed | divergence
  narrative_priority: high | medium | low
  coverage: { systems_count, systems[] }
```

🔒 **Охват и приоритет — разные поля.** То, что ось затронули четыре системы, делает её удобным выбором для свода, но **не делает вывод вернее**. Иначе голосование систем возвращается через заднюю дверь.

### 8. NarrativePlan

Формируется **до** языковой модели. Модель получает только план, а не карту.

```
NarrativePlan:
  id · view_type: theme | school | crisis | temporal | summary
  target_section_id · target_system_id
  allowed_system_ids[]        ← инвариант чистоты школы

  ordered_blocks[]:
    role: lead | explanation | support | counterpoint | application |
          timing | divergence | reference | conclusion |
          explicit_cross_system_comparison
    claim_refs[] · relation_refs[] · evidence_refs[]
    detail_level: headline | short | full
    max_words

  terminology_budget
  prior_exposures[]:
    claim_id · source_block_id · source_section_id
    exposure_mode: full | applied | reference
    blocks_since · same_screen

  must_not_repeat_claim_refs[]
  required_restatement_claim_refs[]
  safety_constraints[] · tone_profile · artifact_refs[]
```

#### Инвариант чистоты школы 🔒

```
view_type == school:
  ∀ claim ∈ plan:  claim.system_id == target_system_id
```

Единственное исключение — блок с ролью `explicit_cross_system_comparison`, и внутри обычного рассказа школы такого блока быть не должно.

⚠️ **Это проверка схемы при сборке, а не правило промпта.** План западной школы с выводом Ба-Цзы обязан завершаться ошибкой.

#### Словарь формулировок по типу связи

🔒 Тип связи определяет, какими словами о ней можно говорить. `complement` — это не «сходятся».

| Тип | Разрешено | Запрещено |
|---|---|---|
| convergence | независимо указывают на · описывают сходный паттерн · приходят к похожему выводу | — |
| complement | описывают разные стороны · добавляют разные грани · говорят о разных этапах | сходятся · подтверждают друг друга · показывают одно и то же · **складываются в механизм** |
| divergence | расходятся · дают несовместимые трактовки | — |
| non_comparable | говорят о разном | любая связка |

⚠️ «Складываются в механизм» заявляет причинную связь между выводами, которой кластер по контракту создавать не может.

#### Предыдущие упоминания

| Ситуация | Формулировка |
|---|---|
| один блок назад | «как мы только что увидели» |
| три–пять блоков | «это уже проявлялось выше» |
| другой крупный раздел | «та же черта, которую мы разбирали в характере» |

🔒 Если вывод показывался только в режиме `reference`, писать «как мы уже подробно разобрали» нельзя.

### 9. NarrativeRender

Текст не источник истины, но хранится: иначе нельзя расследовать плохую генерацию, сравнить версии и воспроизвести жалобу.

```
NarrativeRender:
  narrative_plan_id · text
  model_id · prompt_version · content_policy_version · generated_at

  blocks[]:
    sentences[]:
      text
      claim_refs[]
      relation_refs[]
      cluster_refs[]
      mode: paraphrase | synthesis | transition

  claim_refs_used[] · claim_refs_omitted[]
  qa_results[] · superseded_by
```

#### Проверка смысловой точности 🔒

**Рендер не имеет права добавлять новый предикат.** Переформулировать можно; добавить факт — нет.

Каждое фактическое предложение проверяется по восьми признакам:

| Признак | Что ищем |
|---|---|
| NEW_PREDICATE | утверждение, которого нет ни в одном выводе |
| NEW_CAUSALITY | причинная связь, которой в выводе не было |
| NEW_FREQUENCY | «всегда», «часто», «каждый раз» без основания |
| NEW_COMPARISON | сравнение с другими людьми, которого нет в выводе |
| NEW_CONTEXT | новая жизненная ситуация как иллюстрация |
| NEW_INTERNAL_STATE | приписанное переживание или самоощущение |
| NEW_OUTCOME | следствие или результат, не заявленный в выводе |
| STRENGTH_ESCALATION | «обычно верны» → «не обманывают» |

Хотя бы одно `true` — блок отклоняется и генерируется заново.

⚠️ Проверка применяется и к сводному тексту темы, не только к рассказу школы.

#### Предложение говорит не только о выводах

Фраза свода утверждает что-то не только про человека, но и про отношения между системами. Ссылки только на выводы этого не покрывают, и первая версия проверки такие места пропускала.

| Ссылка | Что проверяется |
|---|---|
| `claim_refs` | не добавлен ли новый предикат |
| `relation_refs` | соответствует ли язык типу связи по словарю формулировок |
| `cluster_refs` | не превратилась ли редакционная группировка в причинный механизм или в новый вывод |

**Примеры, которые ловит третья проверка:**

| Было | Признак |
|---|---|
| «системы называют две разные **причины**» при типе связи `complement` | причинность там, где заявлены разные грани |
| «наружу выходит **медленно**» при выводе «силе некуда выходить» | новый параметр — скорость |

---

## Как из одной строки строятся две вкладки

| | Тема | Школа |
|---|---|---|
| Отвечает на | «что **четыре системы** говорят про мои деньги» | «что **эта система** говорит обо мне целиком» |
| Источник | SectionBundle: кластеры и связи | CellBundle одной системы |
| Состав | главный кластер → второй → расхождение → четыре карточки | контекст предыдущих блоков → главные выводы → применение → ссылки |
| Объём | свод 150–250 слов, карточка по абзацу, полный рассказ ячейки по нажатию | 250–600 слов, если ячейка наполнена |

### Три режима повторного использования

🔑 **Нулевое дублирование — тоже ошибка.** Центральный вывод разумно появляется в трёх местах; разница в функции.

| Режим | Что делает |
|---|---|
| FULL | полное раскрытие, только в своём разделе |
| APPLIED | новое следствие того же вывода в другой области |
| REFERENCE | короткая ссылка на уже раскрытое |

---

## Типология одиннадцати разделов

| Раздел | Тип | Главный вопрос | Наложение периода |
|---|---|---|---|
| Характер | DOMAIN | Как я устроен? | если меняет проявление |
| Отношения и любовь | DOMAIN | Как я строю близость? | да |
| Работа и карьера | DOMAIN | Как я реализуюсь? | да |
| Таланты и способности | DOMAIN | Что даётся естественнее? | обычно нет |
| Деньги и достаток | DOMAIN | Как обращаюсь с ресурсами? | да |
| Энергия и здоровье | DOMAIN · чувствительный | Как расходую и восстанавливаю? | да |
| Семья и род | DOMAIN | Как переживаю принадлежность? | иногда |
| Путь и предназначение | DOMAIN | Что даёт смысл? | слабо |
| Мышление, решения и общение | DOMAIN | Как воспринимаю, решаю, объясняю? | иногда |
| **Кризисы и переломы** | **HYBRID** | Как прохожу нагрузку? | обязательно |
| **Периоды жизни** | **TEMPORAL** | Где я во времени? | является содержанием |

### Композиция предметного раздела

BASELINE · CORE TENSION / RESOURCE · HOW IT SHOWS · CURRENT OVERLAY (только если релевантно) · PRACTICAL REFLECTION.

⚠️ Раздел не обязан содержать все пять блоков.

### Композиция кризисов

LOAD SENSITIVITY · DEFAULT RESPONSE · RESOURCES · TEMPORAL ACTIVATION · ADAPTATION.

🔒 **Композитор кризисов не создаёт новых натальных выводов.** Обнаружил новую мысль — она сначала появляется в одном из девяти предметных разделов.

🔒 **Отсюда жёсткий порядок работ:** девять предметных разделов пишутся раньше гибридного. Композитор физически нечем наполнить, пока выводов нет.

```
CrisisMembership:
  section_id: crisis
  claim_id
  function: load_sensitivity | default_response | resource | adaptation
  activated_by[]          ← временны́е выводы
  direction: increases | decreases | neutral
```

⚠️ **Одному выводу разрешено иметь несколько функций.** Инерция — и то, что мешает сменить курс, и то, что держит под давлением. Без этого картина упрощается до «черта хорошая» или «черта плохая».

⚠️ **Временны́е выводы принадлежат разделу «Периоды».** Кризисы заимствуют их в режиме `applied` и не владеют ни одним.

⚠️ **Кризисы — сводная поверхность.** Значит запрет `cross_system_summary: false` действует здесь автоматически: телесные выводы отфильтровываются по метке `health_related`, а не по смыслу текста.

### Композиция периодов

WHERE YOU ARE · WHAT IT ACTIVATES · WHAT CHANGES · TRANSITION · HORIZON.

Интерфейс один, временны́е движки разные: профекции · вимшоттари · да-юнь · вершины и личный год.

---

## SectionDefinition — таксономия данными

```
SectionDefinition:
  id · type: DOMAIN | HYBRID | TEMPORAL
  allowed_claim_classes[] · prohibited_claim_classes[]
  primary_question
  temporal_overlay_policy: never | optional | required
  cross_system_policy
  required_narrative_slots[] · optional_narrative_slots[]
  safety_policy
  max_primary_claims · max_supporting_claims
  artifact_policy · terminology_budget
```

---

## Система и школа — разные поля

```
system         = western_astrology
method_profile = traditional_whole_sign_v1
```

| system | method_profile |
|---|---|
| western_astrology | traditional_whole_sign |
| jyotisha | parashari |
| bazi | zi_ping_structural |
| numerology | pythagorean + psychomatrix_lens |

⚠️ Слово «школа» не употребляется во внутренних идентификаторах — только в интерфейсе.

**Нумерология:** `primary_visual = psychomatrix`, `primary_interpretation_engine = core_numerology`. Квадрат — герой экрана, но дополнительной значимости от размера не получает.

---

## Телесные выводы

Решение оставить формулировки об уязвимых зонах в силе. Технические ограничения:

```
safety_tags: [health_related, body_zone_inference]
surface_policy:
  cross_system_summary: false
  push_notification: false
  temporal_alert: false
```

🔒 Телесный вывод не усиливается согласием систем. «Три школы сошлись, что уязвим желудок» — недопустимо.

В интерфейсе такие выводы живут в отдельном блоке «Традиционные телесные соответствия» внутри темы, а не в общем тексте, и выключаются одним флагом.

---

## Порядок реализации

1. ✔ Зафиксировать модель
2. **Character** — сквозной срез, пройден с исправительным прогоном
3. **Кризисы** — проверяют композитор
4. **Периоды** — проверяют временну́ю архитектуру
5. Масштабирование на остальные восемь предметных разделов

---

## Связанные документы

- [slice-character.md](slice-character.md) — сквозной срез
- [structure-proposal.md](structure-proposal.md) — продуктовая структура
- [safety-rules.md](safety-rules.md) — запреты и терминология
