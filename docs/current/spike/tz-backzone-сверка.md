# Сверка сборок IANA: стандартная ↔ backzone (G17-S1, шаг 3д)

<!-- СГЕНЕРИРОВАНО scripts/spike/tz_backzone_check.py. Руками не править. -->

Источник: вендоренные `tzdata2026f` + `tzcode2026f` (`data/vendor/iana`, SHA-256 в манифесте), компилятор `zic (tzcode) 2026f`. Сборки: стандартная (345 зон) и с полным `backzone` (468 зон). Сравнение — переходы `zdump -V` в окне 1900–2015.

## Пакет tzdata ↔ вендоренные исходники

Пакет `tzdata` (PyPI), на котором считает рантайм, против стандартной сборки из вендора, все TZif-файлы зон побайтно и `tzdata.zi` построчно: **совпадает полностью**.

## Города бывшего СССР

Городов от 100 000 жителей (GeoNames, снимок data/vendor): **405**. Город попадает в таблицу, если у его зоны переходы в сборках различаются: **0** городов, зон: **0**.

### Тёзки из backzone

Зона `backzone` с именем самого города, а GeoNames ведёт город по другой зоне. Найдено: **1**. Это кандидаты в `tz_disputes`: стандартная сборка склеивает такую зону с соседней и прячет расхождение.

| GeoNames id | Город | Страна | Население | Зона GeoNames | Зона backzone | Дат сетки с разным смещением (из 340) | Период расхождения на сетке | Разбор |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 617239 | Tiraspol | MD | 157000 | Europe/Chisinau | Europe/Tiraspol | 82 | 1990-07…2014-01 | TZD-002 `disputed` (1990-05-06 — 1991-03-30), Europe/Chisinau / Europe/Moscow |

Период на сетке шире окна записи реестра: часть расхождения признана ошибкой источника — обоснование в `source_note` записи (`tz_disputes.yaml`).

## Все зоны (справочно)

Зон и ссылок, где сборки расходятся в окне 1900–2015: **120**. Из бывшего СССР среди них только тёзки из таблицы выше.

`Africa/Accra`, `Africa/Addis_Ababa`, `Africa/Asmara`, `Africa/Bamako`, `Africa/Bangui`, `Africa/Banjul`, `Africa/Blantyre`, `Africa/Brazzaville`, `Africa/Bujumbura`, `Africa/Conakry`, `Africa/Dakar`, `Africa/Dar_es_Salaam`, `Africa/Djibouti`, `Africa/Douala`, `Africa/Freetown`, `Africa/Gaborone`, `Africa/Harare`, `Africa/Kampala`, `Africa/Kigali`, `Africa/Kinshasa`, `Africa/Libreville`, `Africa/Lome`, `Africa/Luanda`, `Africa/Lubumbashi`, `Africa/Lusaka`, `Africa/Malabo`, `Africa/Maseru`, `Africa/Mbabane`, `Africa/Mogadishu`, `Africa/Niamey`, `Africa/Nouakchott`, `Africa/Ouagadougou`, `Africa/Porto-Novo`, `Africa/Timbuktu`, `America/Anguilla`, `America/Antigua`, `America/Argentina/ComodRivadavia`, `America/Aruba`, `America/Atikokan`, `America/Blanc-Sablon`, `America/Cayman`, `America/Coral_Harbour`, `America/Creston`, `America/Curacao`, `America/Dominica`, `America/Ensenada`, `America/Grenada`, `America/Guadeloupe`, `America/Montreal`, `America/Montserrat`, `America/Nassau`, `America/Nipigon`, `America/Pangnirtung`, `America/Port_of_Spain`, `America/Rainy_River`, `America/Rosario`, `America/St_Kitts`, `America/St_Lucia`, `America/St_Thomas`, `America/St_Vincent`, `America/Thunder_Bay`, `America/Tortola`, `Antarctica/DumontDUrville`, `Antarctica/McMurdo`, `Antarctica/Syowa`, `Asia/Aden`, `Asia/Bahrain`, `Asia/Brunei`, `Asia/Chongqing`, `Asia/Harbin`, `Asia/Kashgar`, `Asia/Kuala_Lumpur`, `Asia/Kuwait`, `Asia/Muscat`, `Asia/Phnom_Penh`, `Asia/Tel_Aviv`, `Asia/Vientiane`, `Atlantic/Jan_Mayen`, `Atlantic/Reykjavik`, `Atlantic/St_Helena`, `Australia/Currie`, `CET`, `EET`, `EST`, `Europe/Amsterdam`, `Europe/Belfast`, `Europe/Copenhagen`, `Europe/Guernsey`, `Europe/Jersey`, `Europe/Ljubljana`, `Europe/Luxembourg`, `Europe/Monaco`, `Europe/Oslo`, `Europe/Sarajevo`, `Europe/Skopje`, `Europe/Stockholm`, `Europe/Tiraspol`, `Europe/Zagreb`, `HST`, `Indian/Antananarivo`, `Indian/Christmas`, `Indian/Cocos`, `Indian/Comoro`, `Indian/Kerguelen`, `Indian/Mahe`, `Indian/Mayotte`, `Indian/Reunion`, `MET`, `MST`, `Pacific/Chuuk`, `Pacific/Enderbury`, `Pacific/Funafuti`, `Pacific/Johnston`, `Pacific/Majuro`, `Pacific/Midway`, `Pacific/Pohnpei`, `Pacific/Saipan`, `Pacific/Wake`, `Pacific/Wallis`, `WET`
