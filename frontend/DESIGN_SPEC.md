# DESIGN_SPEC — дизайн-спецификация брендбука

Источник: Figma, файл `9dTPIYTnRIc0ulbLcfyvEw`, страница «брендбук» (0:1).
Все значения извлечены из фреймов брендбука через Figma MCP (точные значения из кода узлов).

---

## 1. Палитра

| Имя | HEX | Роль в UI мониторинга |
|---|---|---|
| Accent | `#00AC86` | Основной акцент: primary-кнопки, активные ссылки, выбранные элементы, статус **up** |
| Accent 10% | `#E6F7F3` | Подложка активных фильтров, hover secondary-кнопок, фон бейджа статуса up |
| Accent dark | `#009B79` | Hover-состояние акцентных элементов (кнопки, ссылки, числа в фильтрах) |
| Red | `#F26F75` | Статус **down**, критические бейджи/индикаторы |
| Yellow | `#EDC45A` | Статус **degraded**, предупреждения |
| Grey 01 | `#F5F5F5` | Фон приложения, secondary-кнопки, подложки тогглов/фильтров |
| Grey 02 | `#E7E7E7` | Границы (инпуты, разделители), disabled-фон primary-кнопки |
| Grey 03 | `#969FA8` | Плейсхолдеры, вторичный текст, неактивные иконки, статус **pending** |
| Grey 04 | `#787F86` | Лейблы инпутов, второстепенные подписи, текст toggle-кнопок |
| Black | `#2C2D2E` | Основной текст |
| White | `#FFFFFF` | Карточки, поверхности, текст на акцентных кнопках |

Маппинг статусов мониторинга: **up** = Accent `#00AC86`, **down** = Red `#F26F75`, **degraded** = Yellow `#EDC45A`, **pending** = Grey 03 `#969FA8`.

Дополнительные цвета, обнаруженные в компонентах (не в основной палитре):

| Имя | HEX | Где используется |
|---|---|---|
| Red (forms error) | `#E0362D` | Границы и тексты ошибок в инпутах/кнопках (все error-состояния форм) |
| Black alt | `#0D0D0D` | Текст в календаре, чекбоксах/радио (компоненты «без изменений») |
| Grey alt 1 | `#F6F6F6` | Разделители и фон диапазона дат в календаре |
| Grey alt 2 | `#D0D2D2` | Disabled-дни календаря |

> Важно: для ошибок форм макет везде использует `#E0362D`, а `#F26F75` из палитры — статусный/индикаторный красный.

---

## 2. Типографика

Шрифт: **Open Sans** (Google Fonts). Используемые начертания: Regular 400, Medium 500, SemiBold 600.

В макете колонки брейкпоинтов desktop / laptop / tablet / mobile присутствуют, но значения заданы едиными — **адаптивных вариаций размеров в брендбуке нет**, все размеры одинаковы на всех брейкпоинтах.

### Заголовки (headlines)

| Стиль | Size | Weight | Line-height |
|---|---|---|---|
| h1 | 24px | 600 (SemiBold) | 32px |
| h2 | 18px | 600 (SemiBold) | 24px |
| h3 | 16px | 500 (Medium) | 24px |
| h4 | 14px | 600 (SemiBold) | 20px |

### Текст (text)

| Стиль | Size | Weight | Line-height |
|---|---|---|---|
| text 01 | 16px | 400 | 24px |
| text 01 — semi | 16px | 600 | 24px |
| text 02 | 14px | 400 | normal (100%) |
| text 02 — med | 14px | 500 | 20px |
| text 02 — semi | 14px | 600 | 20px |
| text 03 | 12px | 400 | normal (100%) |
| text 03 — semi | 12px | 600 | normal (100%) |
| text 04 | 11px | 600 | 16px |
| number | 12px | 500 | normal (100%) |

### Кнопки и ссылки (btn&link)

| Стиль | Size | Weight | Line-height |
|---|---|---|---|
| button big | 16px | 500 | normal (100%) |
| button small | 14px | 500 | 20px |
| link | 14px | 400 | 20px |

### Прочее (other)

| Стиль | Size | Weight | Line-height |
|---|---|---|---|
| search | 15px | 400 | 20px |
| filter 01 | 13px | 400 | 20px |
| filter num | 14px | 600 | 20px |
| reg input / body m | 14px | 400 | 20px |
| reg input / body xs (лейбл в поле) | 11px | 400 | normal (100%) |

---

## 3. Тени

Точные CSS-значения из фрейма «тени» (1:299):

```css
/* shadow 01 — карточки (сценариев, мониторов) */
box-shadow: 0px 2px 24px 0px rgba(0, 0, 0, 0.08);

/* shadow 02 — нижние плашки (bottom sheets, закреплённые панели снизу) */
box-shadow: 0px -4px 10px 0px rgba(0, 0, 0, 0.05);

/* shadow 03 — плавающая боковая кнопка («нераспределено» сбоку) */
box-shadow: 0px 4px 16px 0px rgba(0, 0, 0, 0.12);
```

Дополнительные тени, встречающиеся внутри компонентов:

```css
/* тень выпадающего списка (dropdown list) */
box-shadow: 0px 4px 24px 0px rgba(0, 0, 0, 0.06);

/* тень поповера календаря */
box-shadow: 0px 8px 20px 0px rgba(0, 0, 0, 0.10);
```

---

## 4. Радиусы и отступы

| Элемент | Радиус |
|---|---|
| Кнопки (big/small), инпуты, дропдауны, карточки, фильтры, дни календаря, элементы toggle group | **8px** — базовый радиус системы |
| Контейнер toggle group | 12px |
| Тоггл (активный, внутри группы) | 6px |
| Мини-кнопка (button min 24×24), инпут значения в карточке (secondary), скроллбар списка | 4px |
| Превью-изображение в карточке | 7px |
| Аватар в шапке | 20px (круг, 32×32) |

Типовые внутренние отступы:

| Элемент | Padding | Gap |
|---|---|---|
| Кнопка big | 11px 16px | 8px |
| Кнопка small | 6px 12px | 8px |
| Фильтр, тоггл | 6px 12px | 4px / 8px |
| Инпут (reg) | 16px | 2px (лейбл—значение) |
| Инпут (форма) | 16px 12px | 4px (лейбл—поле—ошибка) |
| Опция дропдауна | 12px 24px 12px 12px | 8px |
| Ячейка календаря | 36×36px | — |
| Карточка | gap 16px между превью и телом | 4–8px внутри тела |

---

## 5. Компоненты

### 5.1 Button (1:807)

Общее: радиус 8px, gap 8px, шрифт Open Sans Medium; big — текст 16px/normal, иконки 20px, padding 11px 16px; small — текст 14px/20px, иконки 16px, padding 6px 12px.

| Вариант | Состояние | Фон | Граница | Текст |
|---|---|---|---|---|
| primary | default | `#00AC86` | — | `#FFFFFF` |
| primary | hover | `#009B79` | — | `#FFFFFF` |
| primary | disabled | `#E7E7E7` | — | `#FFFFFF` |
| secondary | default | `#F5F5F5` | — | `#00AC86` |
| secondary | hover | `#E6F7F3` | — | `#00AC86` |
| tertiary | default | transparent/white | 1px solid `#F5F5F5` | `#00AC86` |
| tertiary | hover | transparent/white | 1px solid `#E7E7E7` | `#00AC86` |
| tertiary | error (small) | transparent/white | 1px solid `#E0362D` | `#787F86` |

Мини-кнопка (button min): 24×24px, фон `#F5F5F5`, радиус 4px, иконка 12px, padding 4px.

```css
.btn { border-radius: 8px; font: 500 14px/20px 'Open Sans'; gap: 8px; padding: 6px 12px; }
.btn--big { font-size: 16px; line-height: normal; padding: 11px 16px; }
.btn--primary { background: #00AC86; color: #fff; }
.btn--primary:hover { background: #009B79; }
.btn--primary:disabled { background: #E7E7E7; color: #fff; }
.btn--secondary { background: #F5F5F5; color: #00AC86; }
.btn--secondary:hover { background: #E6F7F3; }
.btn--tertiary { border: 1px solid #F5F5F5; color: #00AC86; background: transparent; }
.btn--tertiary:hover { border-color: #E7E7E7; }
.btn--tertiary.is-error { border-color: #E0362D; color: #787F86; }
```

### 5.2 Link (1:790)

Текст 14px/20px Regular, gap с иконками 4px, иконки 20px.

| Вариант | Состояние | Цвет |
|---|---|---|
| primary | default | `#00AC86` |
| primary | hover | `#009B79` |
| secondary | default | `#969FA8` |
| secondary | hover | `#00AC86` |

### 5.3 Input — reg/input (1:1090)

Поле с плавающим лейблом (используется в основных формах):

- **default**: высота 52px, фон `#FFFFFF`, граница 1px solid `#E7E7E7`, радиус 8px, padding 16px; плейсхолдер 14px/20px Regular `#787F86`; опциональная иконка справа 24px.
- **hover / active (focus)**: граница `#969FA8` (без изменения фона).
- **active / fulled**: лейбл поднимается наверх — 11px Regular `#787F86`, значение 14px/20px Regular `#2C2D2E`, вертикальный gap 2px.
- **error**: граница 1px solid `#E0362D`, лейбл 11px `#E0362D`; под полем текст ошибки 11px Regular `#E0362D` (gap 4px от поля).
- **big (textarea)**: высота 120px, ширина 344px, padding 16px (active/fulled: 8px сверху, 16px снизу/бока), остальное как у default; в правом нижнем углу resize-уголок 10×10px с отступом 3px.

### 5.4 Input — форма регистрации (1:1248)

Инпут с внешним лейблом:

- Лейбл над полем: 14px Regular `#969FA8`; gap 4px.
- Поле: высота 44px, ширина 292px, фон `#FFFFFF`, граница 1px solid `#E7E7E7`, радиус 8px, padding 16px 12px; текст 16px/24px Regular `#2C2D2E`; плейсхолдер `#969FA8`.
- **error**: граница `#E0362D`; под полем текст ошибки 11px/16px SemiBold `#E0362D`.

### 5.5 Dropdown — reg/dropdown (1:1179)

Триггер идентичен reg/input: высота 52px, граница 1px `#E7E7E7` (hover/active — `#969FA8`), радиус 8px, padding 16px, иконка-стрелка 24px справа. Заполненный: лейбл 11px `#787F86` + значение 14px/20px `#2C2D2E`.

Выпадающий список:
- Контейнер: фон `#FFFFFF`, граница 1px solid `#F5F5F5`, радиус 8px, padding 4px 0, `box-shadow: 0px 4px 24px 0px rgba(0,0,0,0.06)`, gap 2px.
- Поиск внутри списка: обёртка padding 4px; инпут высота 36px, граница 1px `#E7E7E7`, радиус 8px, padding 8px 12px, иконка 20px, текст 14px/20px `#787F86`.
- Опция (selector): padding 12px 24px 12px 12px, текст 14px/20px Regular `#2C2D2E`; hover/выбранная — фон `#F5F5F5`.
- Скроллбар: 4px шириной, `#E7E7E7`, радиус 4px, отступ справа 3px.

### 5.6 Search (1:556)

Строка поиска с нижним подчёркиванием (не рамкой):
- Фон `#FFFFFF`, `border-bottom: 1px solid #E7E7E7`, padding 8px 0, gap 8px.
- Иконка поиска слева 20px.
- Текст 15px/20px Regular; плейсхолдер `#969FA8`, введённый текст `#2C2D2E`.
- **active**: справа кнопка очистки (close-иконка 20px, зона 8px паддинга).

### 5.7 Card (1:573)

Карточка позиции: фон `#FFFFFF`, радиус 8px, тень shadow 01 (`0px 2px 24px rgba(0,0,0,0.08)`), горизонтальный gap 16px.

- Превью-изображение: 48×48px, радиус 7px.
- Заголовок-код: 14px/20px SemiBold `#00AC86`; рядом иконка удаления (trash) 16px; gap 8px.
- Название: 12px Regular `#2C2D2E`.
- Метаданные («Линейка: …»): 12px Regular, ключ `#969FA8`, значение `#2C2D2E`.

**version=default** — справа степпер «plus & minus» (1:920):
- Кнопки «−»/«+»: 24×24px, фон `#F5F5F5`, радиус 8px, иконка 12px.
- Поле значения: высота 24px, фон `#FFFFFF`, граница 1px `#E7E7E7`, радиус 8px, padding 4px 10px, текст 12px Medium `#2C2D2E` по центру; gap между элементами 4px.

**version=secondary** — вместо степпера:
- Ссылка «Распределить» (link primary: 14px/20px `#00AC86`, иконка 20px).
- Справа значение: высота 24px, фон `#F5F5F5`, радиус 4px, padding 8px, текст 12px Medium `#2C2D2E`.

### 5.8 Filter (1:961)

Чип фильтра: padding 6px 12px, радиус 8px, gap 4px.

| Состояние | Фон | Текст |
|---|---|---|
| default | `#F5F5F5` | 13px/20px Regular `#2C2D2E` + стрелка вниз 16px |
| hover | `#F5F5F5` | текст `#00AC86` |
| opened | `#F5F5F5` | текст `#00AC86` + стрелка вверх 16px |
| active (применён) | `#E6F7F3` | текст 13px `#00AC86` + счётчик 14px/20px SemiBold `#00AC86` + close-иконка 16px |
| active hover | `#E6F7F3` | счётчик `#009B79` |

### 5.9 Toggle (1:991)

Элемент-переключатель (сегмент, живёт внутри серой подложки):
- Padding 6px 12px, gap 8px, текст 14px/20px Medium.
- **active**: фон `#FFFFFF`, радиус 6px, текст `#00AC86`; счётчик «15/22»: 12px/20px, число — SemiBold `#787F86`, «/22» — Regular.
- **default** (не выбран): без фона, текст `#00AC86`, счётчик как выше.
- **disabled**: без фона, текст и иконка `#969FA8`, без счётчика.
- Иконка слева 16px.

### 5.10 Toggle group (1:663)

Группа-шкала (оценка 0–10):
- Контейнер: фон `#F5F5F5`, радиус 12px, padding 4px, gap 4px.
- Кнопка сегмента: padding 12px 20px, радиус 8px, текст 14px/20px Regular `#787F86`; **выбранная** — фон `#FFFFFF`, текст `#2C2D2E`.
- Разделители между сегментами: вертикальная линия 1px × 16px, `#E7E7E7`.
- Заголовок над группой: 14px/20px SemiBold `#787F86`.
- Подписи под группой («Не доволен» / «Очень доволен»): 12px/16px Regular `#787F86`.
- Вариант со звёздами: ячейки 32×32px, иконки star 24px (заливка `#00AC86` у активных, контур `#969FA8` у неактивных), padding контейнера 10px 4px.

### 5.11 Checkbox / Radio (1:1377)

- Radio: 20×20px; off — круг с контуром `#969FA8`; on — контур/заливка `#00AC86`, внутренняя точка (37.5% размера, белая/акцентная).
- Checkbox: 18×18px; off — контур `#969FA8`; on — заливка `#00AC86` с белой галочкой.
- Подпись: 14px/20px Regular `#0D0D0D`, gap 6px.

### 5.12 Calendar (1:1315)

- Поповер: фон `#FFFFFF`, радиус 8px, `box-shadow: 0px 8px 20px 0px rgba(0,0,0,0.10)`, ширина 284px.
- Шапка месяца: padding 12px 16px, `border-bottom: 1px solid #F6F6F6`; заголовок «Октябрь, 2024»: 14px/20px SemiBold `#0D0D0D` + стрелка 16px; кнопки навигации: padding 8px, радиус 8px, иконки 20px.
- Сетка: padding 12px 16px; ячейка дня 36×36px, радиус 8px.
- Дни недели: 12px SemiBold `#969FA8`.
- Обычный день: 14px Regular `#0D0D0D`.
- День вне месяца (disabled): `#D0D2D2`.
- Выбранный день (граница диапазона): фон `#00AC86`, текст 14px/20px SemiBold `#FFFFFF`, радиус 8px.
- День внутри диапазона: фон `#F6F6F6`, без радиуса.
- Сегодня / hover: граница 1px solid `#00AC86`, текст 14px/20px SemiBold `#00AC86`.

### 5.13 Шапка (head, 1:765)

- Высота 60px, фон `#F5F5F5`, padding 0 24px, элементы по краям.
- Логотип 90×28px + вертикальный разделитель + подпись 14px/16px `#969FA8`.
- Блок пользователя (gap 12px): аватар 32×32px (круг, фон `#E7E7E7`, иконка user 16px); имя 14px `#2C2D2E` + организация 12px `#969FA8`; вертикальный разделитель 24px; стрелка вниз 16px.

---

## 6. Иконки

Стиль: **контурные (outline)** иконки, отрисованы залитыми путями (`fill` + `fill-rule: evenodd`, без stroke-атрибутов); эффективная толщина линии ~1.5px на сетке 24px, скруглённые окончания. Цвет задаётся через `fill` (в экспорте — `var(--fill-0, #969FA8)`): базовый `#969FA8`, активный/акцентный `#00AC86`, на кнопках — `#FFFFFF`.

Два размера сетки: **24px** (основной) и **16px** (компактный; отдельные иконки 20px).

Набор `ic/24/*`: fish, user, trash, plus, info, download, upload, minus, file, search, close, shablon, speka, arrow down, arrow right, arrow up, arrow left, buy, eye closed, eye opened, checkbox off, checkbox on, refresh, log out, pencil, basket, lock, arrows, history, excel, local, box, message, star.

Набор `ic/16/*`: info, minus, plus, close min, arrow up, arrow right, arrow left, arrow down, local, box, question (20px), shop.

Прочее: `Icon/20px/Message`.

---

## 7. CSS-переменные для theme.css (shadcn-токены, светлая тема)

```css
:root {
  /* Базовые поверхности */
  --background: #F5F5F5;            /* Grey 01 — фон приложения */
  --foreground: #2C2D2E;            /* Black — основной текст */

  --card: #FFFFFF;                  /* White — карточки */
  --card-foreground: #2C2D2E;

  --popover: #FFFFFF;
  --popover-foreground: #2C2D2E;

  /* Акцент */
  --primary: #00AC86;               /* Accent */
  --primary-foreground: #FFFFFF;
  --primary-hover: #009B79;         /* Accent dark — hover primary-кнопок */

  --secondary: #F5F5F5;             /* Grey 01 — secondary-кнопки */
  --secondary-foreground: #00AC86;

  --muted: #F5F5F5;
  --muted-foreground: #787F86;      /* Grey 04 — вторичный текст, лейблы */

  --accent: #E6F7F3;                /* Accent 10% — hover/active подложки */
  --accent-foreground: #009B79;

  /* Ошибки и статусы */
  --destructive: #E0362D;           /* красный ошибок форм (из компонентов) */
  --destructive-foreground: #FFFFFF;

  --status-up: #00AC86;             /* Accent */
  --status-down: #F26F75;           /* Red (палитра) */
  --status-degraded: #EDC45A;       /* Yellow */
  --status-pending: #969FA8;        /* Grey 03 */

  /* Границы и инпуты */
  --border: #E7E7E7;                /* Grey 02 */
  --input: #E7E7E7;                 /* граница инпутов */
  --input-background: #FFFFFF;
  --input-border-hover: #969FA8;    /* Grey 03 — hover/focus граница */
  --placeholder: #969FA8;           /* Grey 03 */

  --ring: #00AC86;                  /* focus ring = акцент */

  /* Геометрия */
  --radius: 0.5rem;                 /* 8px — кнопки, инпуты, карточки, фильтры */
  --radius-sm: 0.25rem;             /* 4px — мини-кнопки, мелкие поля */
  --radius-lg: 0.75rem;             /* 12px — контейнер toggle group */

  /* Тени */
  --shadow-card: 0px 2px 24px 0px rgba(0, 0, 0, 0.08);       /* shadow 01 */
  --shadow-bottom-sheet: 0px -4px 10px 0px rgba(0, 0, 0, 0.05); /* shadow 02 */
  --shadow-floating: 0px 4px 16px 0px rgba(0, 0, 0, 0.12);    /* shadow 03 */
  --shadow-dropdown: 0px 4px 24px 0px rgba(0, 0, 0, 0.06);
  --shadow-calendar: 0px 8px 20px 0px rgba(0, 0, 0, 0.10);

  /* Типографика */
  --font-sans: 'Open Sans', system-ui, -apple-system, sans-serif;
}
```

Подключение шрифта:

```html
<link href="https://fonts.googleapis.com/css2?family=Open+Sans:wght@400;500;600&display=swap" rel="stylesheet">
```
