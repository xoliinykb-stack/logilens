# logilens

logilens проверяет схемы [Logisim](http://www.cburch.com/logisim/) из терминала. Он находит ошибки в соединениях, печатает таблицы истинности и карты Карно и, где это возможно, сравнивает двухуровневую схему с доказанным минимумом.

[![CI](https://github.com/xoliinykb-stack/logilens/actions/workflows/ci.yml/badge.svg)](https://github.com/xoliinykb-stack/logilens/actions/workflows/ci.yml) [![License: GPL-3.0](https://img.shields.io/badge/license-GPL--3.0-blue.svg)](LICENSE) [![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](pyproject.toml)

English version: [README.md](README.md).

```sh
brew install xoliinykb-stack/tap/logilens
```

Logisim — бесплатный учебный симулятор цифровых схем, его автор — Carl Burch. logilens читает файлы `.circ` из Logisim 2.7.1. Так начинается вывод `logilens --lang ru analyze --spec examples/converter.spec.txt examples/converter_nand_nor.circ`:

```text
╭─ logilens · отчёт по схеме ──────────────────────────────────────────────────────────────────────╮
│                                                                                                  │
│  Файл          converter_nand_nor.circ  (схема main)                                             │
│  Движок        Logisim 2.7.1 · бэкенд java                                                       │
│  Входы/выходы  входы: 5 (a b c d e) → выходы: 8 (A_N B_N C_N D_N A_R B_R C_R D_R)                │
│  Компоненты    NAND ×19, NOR ×18, Pin ×13                                                        │
│  Тип           комбинационная                                                                    │
│  Спецификация  converter.spec.txt (таблица кодов, строк: 12)                                     │
│  Вердикт       ✓ ОПТИМАЛЬНО                                                                      │
│                                                                                                  │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
Проверка соединений (lint) ─────────────────────────────────────────────────────────────────────────
✓ 0 проблем — ошибок в соединениях не найдено
Сверка со спецификацией ────────────────────────────────────────────────────────────────────────────
A_N, B_N, C_N, D_N  ✓ 12/12 строк верно
A_R, B_R, C_R, D_R  ✓ 12/12 строк верно
```

Дальше в отчёте идут карты Карно, результаты всех методов минимизации и перевод в базис NAND и NOR.

## Установка

### Homebrew (macOS)

```sh
brew install xoliinykb-stack/tap/logilens
logilens doctor
```

Вместе с logilens `brew install` ставит OpenJDK и скачивает `logisim.jar` от Logisim 2.7.1 (с проверкой SHA-256), так что движок Java работает сразу. Espresso и Java-помощник собираются во время установки. Удалить пакет можно командой `brew uninstall logilens`.

### pipx

```sh
pipx install git+https://github.com/xoliinykb-stack/logilens
logilens setup        # собирает Espresso и Java-помощник в кэш пользователя
```

Нужны Python 3.11 или новее, а для Espresso — `make` и компилятор C (на macOS их ставит `xcode-select --install`). Java и `logisim.jar` не обязательны: без них logilens работает на встроенном движке Python. Подробнее — в разделе [Движок Java и движок Python](#движок-java-и-движок-python).

### Скрипт установки

Из клона репозитория:

```sh
bash scripts/install.sh                 # окружение в ~/.local/share/logilens, команда в ~/.local/bin
bash scripts/install.sh --download-jar  # заодно скачать Logisim 2.7.1 с проверкой SHA-256
bash scripts/install.sh --uninstall     # удалить установку
```

Скрипту нужно то же, что и pipx.

## Быстрый старт

В каталоге [examples/](examples/) лежат три схемы для примера. Homebrew ставит те же файлы, поэтому после `brew install` запускайте команды ниже из каталога `$(brew --prefix logilens)/share/logilens`.

```sh
logilens lint examples/converter_draft.circ
logilens check --spec examples/converter.spec.txt examples/converter_nand_nor.circ
logilens analyze --spec examples/converter.spec.txt examples/converter_draft.circ
logilens seq --input 0110 examples/moore_fsm.circ
```

`converter_draft.circ` — черновик преобразователя 5-битного кода в 4-битный. `lint` находит в нём неподключённый вход гейта, повторяющиеся метки контактов, висящие провода и выходы без меток, а `analyze` показывает, что обе половины схемы можно собрать на меньшем числе гейтов. `converter_nand_nor.circ` — исправленный вариант, он проходит все 12 строк спецификации. `moore_fsm.circ` — небольшой автомат Мура для команды `seq`.

## Возможности

* Проверка соединений по 14 правилам, L001–L014. К каждому сообщению прилагается совет, как исправить ошибку.
* Таблицы истинности, карты Карно для 2–6 переменных, минимальные ДНФ и КНФ.
* Доказательство оптимальности через целочисленное линейное программирование (HiGHS). Для сравнения рядом работают методы Квайна — Мак-Класки, Петрика, Тисона и Espresso.
* Сверка со спецификацией: таблицей кодов, таблицей истинности или формулами.
* Перевод в базис NAND и NOR с подсчётом гейтов и входов.
* Триггеры, автоматы Мура и Мили, кодирование состояний, временные диаграммы.
* Отчёты в терминале, а также в файлах Markdown, HTML и JSON.

## Команды

| Команда | Что делает |
|---------|------------|
| `parse` | Показывает схемы, компоненты, входные и выходные контакты. |
| `lint` | Проверяет соединения по правилам L001–L014. |
| `check` | Сравнивает схему со спецификацией: таблицей кодов, таблицей истинности или формулами. |
| `analyze` | Печатает таблицу истинности, карты Карно, минимальные ДНФ и КНФ, перевод в NAND и NOR и вердикт об оптимальности. |
| `seq` | Показывает триггеры, таблицу переходов, тип автомата (Мура или Мили), граф состояний и временную диаграмму. |
| `report` | Выводит полный анализ в терминал или записывает его в файл Markdown, HTML или JSON. |
| `doctor` | Показывает, какие дополнительные инструменты найдены: Java, Logisim, Espresso, Graphviz. |
| `setup` | Собирает Java-помощник и Espresso в кэш пользователя. |
| `cache clear` | Удаляет собранные файлы из кэша. |

У каждой команды есть `--help`. Все опции описаны в [docs/USAGE.md](docs/USAGE.md).

## Интерактивный режим

Если запустить `logilens` в терминале без команды, откроется выбор файла. `logilens FILE --spec SPEC` сразу открывает нужный файл. Клавиша `?` показывает список горячих клавиш. Вне терминала команда просто печатает список команд.

## Движок Java и движок Python

С `--backend java` схему считает сам движок Logisim 2.7.1 через небольшой Java-помощник. Для этого нужны JDK (Java 11 или новее) и `logisim.jar`, который не входит ни в репозиторий, ни в пакет Python. С `--backend python` работает встроенный симулятор, которому ничего не нужно. По умолчанию стоит `auto`: если найдены и Java, и jar, выбирается Java. Команда `logilens parse --crossval FILE` сверяет движок Python с Logisim, см. [docs/USAGE.md](docs/USAGE.md#parse).

## Ограничения

* Эталон — файлы Logisim 2.7.1. Файлы Logisim-evolution 3.x читаются в экспериментальном режиме по правилам 2.7.1. Другие версии не проверялись.
* Схема называется оптимальной, только если это доказано. Если входов больше 8, ILP выбирает только среди многовыходных простых импликант.
* Минимизируются только двухуровневые формы. Многоуровневую схему logilens никогда не назовёт минимальной.
* Группы, в которых больше 10 переменных, не минимизируются. Таблица истинности ограничена 20 входными битами.
* Без `--spec` безразличные наборы неизвестны, поэтому минимизируется полностью определённая функция самой схемы.
* Последовательные схемы анализируются на Python-моделях триггеров. RAM и ROM только описываются.

## Документация

* [docs/USAGE.md](docs/USAGE.md): все команды и опции, форматы спецификаций, коды выхода.
* [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md): частые проблемы с установкой и их решения.

Документация в `docs/` написана на английском. Об ошибках и с вопросами пишите в [issues](https://github.com/xoliinykb-stack/logilens/issues), об уязвимостях — как описано в [SECURITY.md](SECURITY.md).

## Лицензия

logilens — свободная программа под лицензией GNU General Public License версии 3 или более поздней, см. [LICENSE](LICENSE). В комплект входит Espresso (MIT), см. [third_party/espresso/LICENSE](third_party/espresso/LICENSE). logilens никак не связан с Logisim и Carl Burch.
