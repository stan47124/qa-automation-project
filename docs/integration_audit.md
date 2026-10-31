# Аудит интеграции QA.Guru

Дата: 31 октября 2026 года. Рабочая папка: `E:\Progects\qa-automation-project`.

**Обновление после первого этапа интеграции:** созданы `.gitignore`, README и общая схема requirements/constraints; сохранены рабочие версии. В pytest.ini добавлен testpaths=tests. Повторная collection: 22 теста; pip check и офлайн dry-run успешны. Подробные изменения, состав будущей публикации и ограничения приведены в [дополнении об этапе 1](#этап-1-выполненная-подготовка-структуры-и-зависимостей). Разделы исходного аудита ниже сохраняют историческое состояние до этих изменений; сведения об отсутствовавших файлах больше не описывают текущее состояние.

## Вывод и границы проверки

Три направления совместимы на уровне обнаружения: из корня pytest обнаружил **22 теста: API 8, UI 8, Mobile 6**, без ошибок импорта. Это результат collection, а не новый результат `22 passed`. Полный набор в рамках аудита не запускался.

Тестовый код, fixtures, конфигурация и зависимости не изменены. Создан только этот документ; команды collection могли штатно обновить pytest cache/pycache. Зависимости не устанавливались и не обновлялись. Git commit/push, инициализация Git, запуск Chrome, создание Appium-сессий, запуск/сброс эмулятора и удаление файлов не выполнялись.

Текущий каталог не является Git working tree: `git rev-parse --show-toplevel` вернул `fatal: not a git repository`. Поэтому проверить tracked-файлы, историю и правила GitHub сейчас невозможно. Ни `.git`, ни корневого `.gitignore` не найдено.

## Дерево на момент исходного аудита

Служебные каталоги и многочисленные JSON/attachment-файлы свёрнуты; файлы исходного кода перечислены полностью. Этот документ включён как результат аудита.

```text
qa-automation-project/
├── AGENTS.md
├── pytest.ini
├── mobile_sample.txt
├── se-metadata.json
├── .venv/                         # локальное окружение
├── .pytest_cache/                 # старый каталог, недоступен из песочницы
├── .pytest_cache_local/           # активный кэш pytest
├── __pycache__/
├── artifacts/
│   ├── api/
│   │   ├── run_01/{allure-results/, pytest.xml}
│   │   └── run_02/{allure-results/, pytest.xml}
│   └── ui/
│       ├── run_01/{allure-results/, pytest.xml}
│       └── run_02/{allure-results/, pytest.xml}
├── docs/
│   ├── api_test_results.md
│   ├── integration_audit.md
│   ├── mobile_refactoring_results.md
│   ├── poc_results.md
│   └── ui_test_results.md
└── tests/
    ├── api/
    │   ├── conftest.py
    │   ├── petstore.py
    │   ├── requirements.txt
    │   ├── test_petstore_smoke.py
    │   └── __pycache__/
    ├── ui/
    │   ├── conftest.py
    │   ├── requirements.txt
    │   ├── storefront.py
    │   ├── test_contact_us_upload.py
    │   ├── test_product_search.py
    │   ├── test_storefront.py
    │   └── __pycache__/
    └── mobile/
        ├── conftest.py
        ├── material_files.py
        ├── mobile_config.py
        ├── test_material_files_functional.py
        ├── test_material_files_smoke.py
        └── __pycache__/
```

Корневых `requirements.txt`, `conftest.py`, `README.md`, `pyproject.toml` и CI-конфигурации не найдено. Отсутствие общего conftest само по себе не проблема: локальные fixtures хорошо разделяют направления. Ранее встречавшегося `test_example.py` в текущей папке нет; лишний 23-й тест не обнаружен. Пользовательские `mobile_sample.txt` и старый кэш сохранены.

## Фактически выполненные проверки

Все команды pytest выполнены через `.venv`, без запуска тестовых функций и fixtures:

| Команда | Результат | Код выхода |
| --- | --- | --- |
| `.\.venv\Scripts\python.exe -m pytest --collect-only -q` | 22 tests collected in 0.91s | 0 |
| `.\.venv\Scripts\python.exe -m pytest tests/api --collect-only -q` | 8 tests collected in 0.01s | 0 |
| `.\.venv\Scripts\python.exe -m pytest tests/ui --collect-only -q` | 8 tests collected in 0.02s | 0 |
| `.\.venv\Scripts\python.exe -m pytest tests/mobile --collect-only -q` | 6 tests collected in 0.01s | 0 |
| `.\.venv\Scripts\python.exe -m pip check` | No broken requirements found | 0 |

Дополнительно прочитаны установленные package metadata, исходники, документация, JUnit XML и результаты Allure. У тестов нет операций запуска сервисов на уровне импорта. Общая collection прошла даже при недоступном Appium и отсутствии подключённых ADB-устройств.

## Проблемы по приоритету

P1 — устранить перед переносом/публикацией и первым общим запуском; P2 — оформить при интеграции; P3 — дальнейшее улучшение. Блокирующей ошибки обнаружения или несовместимости установленных Python-пакетов не выявлено.

| Приоритет | Наблюдение и доказательство | Следствие / предлагаемое действие |
| --- | --- | --- |
| P1 | Нет корневого `.gitignore`; присутствуют `.venv`, два кэша, artifacts, pycache и `se-metadata.json` | Перед GitHub подготовить ignore и проверить будущий состав публикации. Сейчас файлы не публиковались; отсутствие ignore не означает уже случившуюся утечку |
| P1 | Нет единой установки и Mobile requirements. API/UI повторяют pytest/Allure; Appium существует только в текущей `.venv` | Новая машина не восстановит Mobile по файлам проекта. Описать общие ограничения версий и три профиля установки |
| P1 | `/status` на `127.0.0.1:4723` недоступен: ConnectionError; `adb devices -l` вернул пустой список | Готовность Mobile к реальному запуску сейчас не подтверждена. Предварительно запустить/подготовить сервисы без сброса данных и проверить ready/boot/package/path |
| P2 | Нет README с общей архитектурой, установкой и командами. `poc_results.md` описывает прежний одиночный lifecycle и прежние версии Chrome | Сохранить PoC как датированную историю, добавить актуальную точку входа на 22 теста и ссылки на отчёты направлений |
| P2 | API/UI имеют Allure/JUnit, Mobile — только Markdown с прошлыми результатами | После согласованного запуска получить машинные результаты всех 22 тестов, не выдавать сумму прошлых запусков за единый прогон |
| P2 | Пути отчётов задаются вручную `run_01`/`run_02`; нет общего runner/run ID | Повтор команды в старый каталог может смешать Allure разных запусков и перезаписать JUnit. Использовать новый каталог на каждый запуск без удаления старых |
| P2 | Скриншоты Selene находятся в `tmp_path/selene`, не прикрепляются к Allure; Mobile не имеет своих Allure-шагов/вложений | Для разборов ошибок предложить единый путь скриншотов и безопасные вложения. Плагин создаст базовый результат Mobile, но сам не добавит подробные UI-шаги |
| P2 | pytest.ini содержит только cache_dir; нет testpaths/маркеров/общей политики запуска | Зафиксировать testpaths=tests и последовательный запуск. Раздельные запуски уже работают по путям; маркеры не обязательны |
| P2 | Appium URL, udid, пути, адреса сайтов и таймауты локальные и жёстко заданные | После отдельного обоснования добавить параметры с текущими значениями по умолчанию; не переносить конфигурацию всех направлений в один Page Object |
| P2 | Один udid и один UIAutomator2 systemPort по умолчанию; xdist не установлен | Не применять `-n auto`. UUID-папки изолируют файлы, но не действия UI на одном эмуляторе |
| P3 | Bare imports (`from petstore`, `from storefront`, `from material_files`) зависят от обычного pytest prepend | Сейчас всё собирается. Не переключать import-mode на importlib без отдельной проверки/изменения упаковки |
| P3 | API-файл назван smoke, но содержит все 8 сценариев; часть общих UI-настроек остаётся в fixture | Не использовать имя файла как классификацию smoke; переименование/маркеры и перенос настроек не нужны для первого общего запуска |

## Зависимости и единая схема установки

Текущий Python: **3.14.3**. Совместимость на другой версии Python не проверялась; основные установленные библиотеки указывают Requires-Python >=3.10, но это не равно проверке всего набора на 3.10.

| Пакет | Установлен | Где нужен / как зафиксирован сейчас |
| --- | --- | --- |
| pytest | 9.2.0 | Все; продублирован в API/UI requirements |
| allure-pytest | 2.16.2 | API/UI импортируют allure; плагин может репортить все направления |
| requests | 2.34.2 | API; зафиксирован в API requirements |
| selene | 2.0.0rc10 | UI; зафиксирован, prerelease указан явно |
| selenium | 4.52.0 | UI и Appium; зафиксирован только в UI requirements |
| Appium-Python-Client | 6.0.12 | Mobile; не зафиксирован ни в одном requirements |

Установленный Appium Client требует selenium >=4.51.0,<5.0; Selene требует selenium >=4.12.0. Версия 4.52.0 удовлетворяет обоим. typing_extensions 4.16.0 также согласован с установленными зависимостями. `pip check` подтверждает отсутствие объявленных конфликтов текущего окружения, но не доказывает воспроизводимость чистой установки.

Не следует использовать весь `pip freeze` как архитектуру проекта: в `.venv` есть также webdriver-manager, python-dotenv и другие пакеты, не импортируемые проверенными исходниками. Удалять их в рамках аудита не нужно. Selenium Manager вызывается через webdriver.Chrome; библиотека webdriver-manager кодом UI не используется.

**Предлагаемая схема, ещё не создана:**

```text
requirements.txt                  # -r requirements/api.txt, ui.txt, mobile.txt
requirements/
├── constraints.txt               # 6 точных версий из таблицы выше
├── common.txt                    # -c constraints.txt; pytest; allure-pytest
├── api.txt                       # -r common.txt; requests
├── ui.txt                        # -r common.txt; selene; selenium
└── mobile.txt                    # -r common.txt; Appium-Python-Client; selenium
```

Здесь записи через `;` обозначают отдельные строки файлов. Constraints ограничивает версии, но не устанавливает все пакеты сам. В существующих `tests/api/requirements.txt` и `tests/ui/requirements.txt` можно оставить короткие ссылки на новые профили, чтобы прежние команды установки не сломались. При необходимости добавить аналогичную ссылку `tests/mobile/requirements.txt`. Транзитивный lock генерировать отдельно после проверки чистой установки; пока зафиксированы только прямые зависимости.

**Будущие команды, не выполнялись:**

```powershell
# Все направления в одном окружении
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

# Либо только нужное направление
.\.venv\Scripts\python.exe -m pip install -r requirements/api.txt
.\.venv\Scripts\python.exe -m pip install -r requirements/ui.txt
.\.venv\Scripts\python.exe -m pip install -r requirements/mobile.txt
```

После любой выбранной установки запускать `pip check` и collection соответствующего пути. Для API-only окружения использовать `pytest tests/api`, а не collection всего корня. Фильтр `-m api` не избавляет от импорта conftest других направлений; кроме того, таких маркеров сейчас нет.

Appium Server, Node.js, Android SDK/ADB, AVD, установленное Android-приложение и Chrome — внешние компоненты, их нельзя восстановить одним pip requirements. Версии и инструкции подготовки нужно документировать отдельно без глобальных установок из fixtures.

## Pytest, fixtures, таймауты и данные

Текущий pytest.ini:

```ini
[pytest]
cache_dir = .pytest_cache_local
```

Параметр работает: четыре сборки завершились без предупреждений кэша. Старый `.pytest_cache` не используется; чтение его содержимого из песочницы запрещено, удалять или менять права на него не требуется.

Fixtures всех направлений function-scoped; межнаправленных конфликтов имён не выявлено. API закрывает requests.Session; UI и Mobile закрывают driver в finally. Общий conftest не обязателен. Напротив, импорт Appium или Selene в корневом conftest сломал бы минимальные установки API-only; инфраструктурные зависимости следует оставить локальными.

| Направление | Ожидания | Изоляция и ограничения |
| --- | --- | --- |
| API | requests timeout=15 на запрос, max_retries=0, redirects выключены | Случайный ID, предварительный 404, cleanup DELETE и GET даже при ошибке. Общий публичный сервис может перезапускаться или меняться другими пользователями |
| UI | Selene 15 с, page-load 45 с; таймаут отдельной команды WebDriver не настроен явно | Отдельный ChromeDriver/временный профиль; TXT через tmp_path; гостевая корзина. Цена/категория Blue Top заданы явно и могут измениться на сайте |
| Mobile | WebDriverWait и ADB timeout по 20 с; HTTP-таймаут Appium Client не задан явно | UUID-папка, mkdir без -p, удаление только прямого test_<uuid>. Общий udid/noReset, английские тексты и существующий qa_guru остаются предпосылками |

Request timeout requests не является общим лимитом длительности теста. Аналогично WebDriverWait не ограничивает длительность блокирующей HTTP-команды Appium. Перед CI целесообразно отдельно согласовать лимиты соединения/чтения клиента и общий лимит job. Слепо приводить все таймауты к одному значению не нужно.

Адресный повтор поиска/клика при StaleElementReferenceException сохранён в FilesScreen. Другие исключения не маскируются. При недоступном ADB cleanup Mobile может завершиться ошибкой и оставить собственную UUID-папку; нет основания удалять весь qa_guru. При недоступном Petstore cleanup аналогично не гарантирован, но ошибка фиксируется. Запуск не следует переводить в зелёный результат автоматическими skip/retry.

## Allure и JUnit: фактическое состояние

| Каталог | JUnit | Allure результатов |
| --- | --- | --- |
| artifacts/api/run_01 | tests=8, failures=0, errors=0, skipped=0 | 8 passed |
| artifacts/api/run_02 | tests=8, failures=0, errors=0, skipped=0 | 8 passed |
| artifacts/ui/run_01 | tests=8, failures=0, errors=0, skipped=0 | 8 passed |
| artifacts/ui/run_02 | tests=8, failures=0, errors=0, skipped=0 | 8 passed |

Файлы XML разобраны, JSON Allure прочитан для подсчёта результатов. API/UI имеют по два сохранённых запуска; Mobile-артефактов в `artifacts` не обнаружено. Его прежние три успешных прогона описаны в `docs/mobile_refactoring_results.md` (187,15 / 103,54 / 99,94 с). Эти старые тестовые прогоны в данном аудите не повторялись.

`artifacts` на момент проверки содержит 236 файлов, 104876 байт. Сами каталоги allure-results — сырые результаты, а не готовый HTML. Команда `allure` не найдена в текущем PATH, Java найдена. Python-плагин не заменяет Allure CLI; генерацию HTML следует предусмотреть отдельным инструментом/шагом после согласования установки. API run_01 сохранён с первоначально повреждёнными подписями; актуальные подписи — в run_02, это описано в отчёте API.

Предлагаемый стандарт одного запуска:

```text
artifacts/<unique-run-id>/
├── allure-results/     # все 22 результата при едином процессе pytest
├── junit.xml
└── screenshots/        # если позже согласована привязка UI/Mobile вложений
```

Раздельный запуск может использовать `artifacts/<unique-run-id>/<suite>/...`. Run ID должен быть новым; старые пользовательские результаты не удалять и не применять `--clean-alluredir` к существующим каталогам. Для первого общего запуска достаточно CLI-параметров Allure/JUnit — без изменения бизнес-проверок. Привязку скриншотов и Mobile-шаги вынести в отдельное минимальное изменение инфраструктуры.

## .gitignore и подготовка к GitHub

Корневого `.gitignore` нет. Скрытые env/ключевые файлы в проверенных `tests/` и `docs/` по именам не обнаружены, однако это не полноценное сканирование секретов и не аудит Git-истории. Перед публикацией необходима проверка состава добавляемых файлов без вывода значений секретов.

Минимальный предлагаемый `.gitignore`, **не создан в рамках аудита**:

```gitignore
# Python environments and caches
.venv/
venv/
.venv-*/
__pycache__/
*.py[cod]
.pytest_cache/
.pytest_cache_local/
.mypy_cache/
.ruff_cache/
.coverage
.coverage.*
htmlcov/

# Generated reports and local diagnostics
artifacts/
allure-results/
allure-report/
test-results/
*.log
se-metadata.json

# Local configuration and credentials
.env
.env.*
!.env.example
!.env.template
*.pem
*.key
*.p12
*.pfx
.aws/

# Editors and OS metadata
.idea/
.vscode/
.DS_Store
Thumbs.db
```

Это только начальный список, а не гарантия отсутствия секретов. Если появятся `.env.example`/template, в них должны быть только фиктивные значения. Не игнорировать целиком `docs/`, `tests/` или `*.txt`: requirements и документированные результаты нужны проекту. `mobile_sample.txt` пока сохранить как пользовательский файл; его включение в публикацию определить отдельно. `.gitignore` не удаляет уже tracked-файлы, когда Git будет подключён.

`se-metadata.json` содержит верхнеуровневые разделы browsers/drivers/stats/cached_assets и относится к локальным метаданным инструмента, а не исходникам тестов. Его предлагается игнорировать, а не удалять. Не добавлять в ignore AGENTS.md автоматически: он содержит действующие правила проекта и должен сохраняться.

## Документация и фактическая архитектура

- AGENTS.md верно отражает Python/pytest и разделение API/UI/Mobile, ограничения на данные и требования к фактическим результатам. Необходимо сохранить эти правила.
- `api_test_results.md`, `ui_test_results.md` и `mobile_refactoring_results.md` соответствуют актуальным модулям/fixtures и результатам направлений. Текущий API-файл действительно содержит 8 отдельных тестов, Mobile — 5 functional + smoke, UI — 8 тестов с общими Browser/Storefront.
- `poc_results.md` — датированная история 30 октября. Описанный там одиночный API lifecycle уже заменён; UI теперь использует fixture/Storefront, Chrome обновлён, поэтому раздел «последний запуск» нельзя воспринимать как итог всего проекта. Не переписывать историю: добавить заметку о её статусе и ссылку из нового README.
- Нет общего документа с установкой и архитектурой на 22 теста, внешними предпосылками Mobile/Chrome, расположением отчётов и отсутствием подтверждённого общего запуска. Это должен стать README, ссылающийся на подробные отчёты.

## Потенциальные проблемы совместного запуска

1. **Предпосылки среды.** Сейчас status Appium недоступен, ADB-устройств нет. Установленные пакеты Appium Server 3.9.0 и UiAutomator2 8.7.3 найдены, но установка пакета не означает работающий сервис. Проверка Material Files/qa_guru/boot в этой сессии не выполнялась из-за отсутствия устройства; прежняя успешная подготовка описана в Mobile-отчёте.
2. **Chrome.** Установлен Chrome 156.0.8078.76. webdriver.Chrome может задействовать Selenium Manager и сеть для подбора драйвера; офлайн-кэш и совместимость проверяются отдельно перед реальным запуском. Браузер в аудите не запускался. Версия из прежнего UI-отчёта сама по себе не является новой проверкой ChromeDriver.
3. **Нагрузка/порядок.** Последовательный pytest по умолчанию не требует одновременного управления Chrome и Mobile. Сам эмулятор потребляет ресурсы даже при прохождении API/UI. Доказательств, что все 22 теста уже проходили в одном процессе, пока нет.
4. **Параллельность.** Один emulator-5554 не подходит для конкурентных Mobile-сессий без отдельных устройств и портов. В первом интеграционном запуске xdist не использовать. Установка xdist сама по себе не решит изоляцию устройства.
5. **Глобальные импорты/зависимости.** Общая collection требует всех Python-библиотек, хотя fixtures запускаются позже. Отдельный путь направления позволяет минимальную установку. Не вносить тяжёлые импорты в корневой conftest и не менять import-mode в первом шаге.
6. **Внешние сервисы.** Публичные Petstore и Automation Exercise, реклама и обновления каталога могут вызывать падения независимо от интеграции. Ограниченные ожидания и отключённые HTTP-retry API сохранять; ошибки среды/сервиса фиксировать отдельно от ошибок тестового кода.
7. **Отчёты и сбои cleanup.** Все направления должны иметь новый общий run ID; teardown-ошибки нельзя терять при последующей генерации отчёта. Полный XML/HTML страниц может содержать CSRF-токены; настройка UI save_page_source_on_failure=False уже учитывает это.

## Конкретный план интеграции для согласования

1. **Защита и точка входа.** Добавить предложенный `.gitignore` и README. Не инициализировать Git и не публиковать файлы без отдельной задачи. README описывает 22 теста, внешние компоненты, отдельные команды и ссылку на исторический PoC.
2. **Установка.** Создать предложенные профили requirements/constraints и корневой агрегатор; существующие API/UI requirements превратить в ссылки. Использовать уже проверенные версии, без обновлений. Сначала проверить согласованность файлов; чистую установку согласовать отдельно, текущую `.venv` не пересоздавать.
3. **Минимальная конфигурация pytest.** Сохранить cache_dir, добавить testpaths=tests. Сохранить function-scoped fixtures и локальные conftest. Запуск по путям оставить основным; маркеры и упаковку импортов отложить, поскольку текущая общая collection исправна.
4. **Команды и отчётность.** Описать единый run ID и CLI-опции Allure/JUnit. При необходимости добавить небольшой runner, который сохраняет exit code pytest и не устанавливает пакеты, не запускает сервисы скрыто и не удаляет старые результаты. Скриншоты/дополнительные Mobile-вложения — отдельный согласованный инфраструктурный шаг.
5. **Проверка готовности.** До общего прогона проверить Appium /status, adb devices/boot, установленный package/activity, доступность qa_guru и английский интерфейс; проверить Chrome/драйвер. При необходимости подготовить существующий AVD без wipe-data и сервис Appium. Не сбрасывать приложение, эмулятор и исходный sample.txt.
6. **Повторная безопасная сборка.** После конфигурационных изменений повторить четыре команды collection из этого аудита и pip check. Ожидаемый результат — 22/8/8/6 и отсутствие новых конфликтов.
7. **Только после согласования плана — первый общий последовательный прогон:**

   ```powershell
   .\.venv\Scripts\python.exe -m pytest tests -v --alluredir=artifacts/<new-run-id>/allure-results --junitxml=artifacts/<new-run-id>/junit.xml
   ```

   `<new-run-id>` — шаблон, до запуска заменить уникальным значением. Эта команда в аудите **не выполнялась**. Не добавлять -n, --reruns и не скрывать недоступность Mobile через skip. Зафиксировать exit code, результаты каждого направления и teardown. При ошибке классифицировать её до повторного запуска; не утверждать «22 passed» по успешной collection.

8. **Приёмка интеграции.** Подтвердить один общий отчёт с 22 результатами, отсутствие ошибок очистки и сохранность пользовательских Android-данных; затем отдельно согласовать повторный общий прогон/CI. Сам GitHub/CI и глобальная установка Allure CLI не входят в текущий аудит.

Раздельные команды останутся доступными: `pytest tests/api`, `pytest tests/ui`, `pytest tests/mobile` через `.venv`. План не требует изменения работающих assertions, Page Objects и бизнес-поведения тестов.

## Этап 1: выполненная подготовка структуры и зависимостей

Выполнен 31 октября 2026 года. Полный набор тестов не запускался. Git init/commit/push не выполнялись; `.git` не создан. Сервисы Appium, Android Emulator и Chrome не запускались. Пользовательские файлы и старые результаты не удалялись.

### Созданные и изменённые файлы

| Файл | Изменение |
| --- | --- |
| `.gitignore` | Исключает окружения, pycache, `.pytest_cache*`, временные данные, отчёты, скриншоты, JUnit, Allure, логи, известные имена/расширения секретов и личные настройки |
| `README.md` | Актуальная русская точка входа: 22 теста, архитектура, технологии, установка, команды, предпосылки Mobile/Chrome, отчёты и ограничения |
| `requirements.txt` | Корневой агрегатор API/UI/Mobile |
| `requirements/constraints.txt` | Единые 6 точных версий, совпадающих с установленными |
| `requirements/common.txt` | Общие pytest/Allure и ссылка на constraints |
| `requirements/api.txt` | requests и общие зависимости |
| `requirements/ui.txt` | Selene/Selenium и общие зависимости |
| `requirements/mobile.txt` | Appium Python Client/Selenium и общие зависимости |
| `tests/api/requirements.txt` | Ссылка на ../../requirements/api.txt вместо дублирования версий |
| `tests/ui/requirements.txt` | Ссылка на ../../requirements/ui.txt вместо дублирования версий |
| `tests/mobile/requirements.txt` | Новый совместимый путь установки Mobile-профиля |
| `pytest.ini` | Добавлен `testpaths = tests`, сохранён `cache_dir = .pytest_cache_local` |
| `docs/integration_audit.md` | Этот статус и результаты проверок; исходный аудит сохранён как история |

Полное актуальное описание структуры находится в README. Ни один Python-файл тестов, fixtures или вспомогательных модулей не менялся: SHA-256 всех **13 файлов tests/**/*.py** до и после совпали. Отдельно совпали SHA-256 AGENTS.md, mobile_sample.txt и se-metadata.json. Версии 6 прямых зависимостей также не изменились.

Схема реализована без корневого conftest и смены import-mode. Установка всех зависимостей из корня:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Эта команда здесь показана как инструкция, **реальная установка не выполнялась**. Во время этапа использовался только pip с `--dry-run --no-index`: без обращения к package index и без изменения установленных пакетов.

### Результаты проверок этапа 1

| Проверка | Фактический результат |
| --- | --- |
| `.\.venv\Scripts\python.exe -m pytest --collect-only -q` | **22 tests collected in 1.08s**, exit 0: API 8, Mobile 6, UI 8 |
| `.\.venv\Scripts\python.exe -m pip check` | **No broken requirements found**, exit 0 |
| `pip install --dry-run --no-index --disable-pip-version-check -r requirements.txt` через .venv | Успех, exit 0; все зависимости уже удовлетворены |
| Аналогичный dry-run для requirements/api.txt, ui.txt, mobile.txt | Все 3 профиля успешны, exit 0 |
| Аналогичный dry-run для tests/api/requirements.txt, tests/ui/requirements.txt, tests/mobile/requirements.txt | Все 3 совместимых пути успешны, exit 0 |
| Разбор constraints через packaging.Requirement | 6 уникальных pins соответствуют установленным версиям |
| Разбор pytest.ini через configparser | testpaths=tests, исходный cache_dir сохранён |
| Контрольные суммы исходников и пользовательских файлов | Все проверенные файлы неизменны |
| Статические примеры .gitignore | 40 из 40 ожидаемых решений совпали |

Selene 2.0.0rc10 оставлен явно в constraints, без замены на иной release. Selenium 4.52.0 удовлетворяет Appium Client >=4.51.0,<5.0 и Selene >=4.12.0; pip check подтвердил согласованность текущего окружения. Dry-run также проверил корректность относительных ссылок `-r` и `-c`, включая старые entry points. Проверка в установленной `.venv` не является проверкой чистой установки на другой машине; полный транзитивный lock пока не добавлен.

### Анализ будущего состава Git

Поскольку Git init запрещён на этом этапе, **git status/check-ignore не имитировались через создание временного репозитория**. Выполнен статический обход дерева с применением используемых в .gitignore форм шаблонов (директории, корневые пути, wildcard и отрицания), с проверкой 40 контрольных примеров. Это прогноз состава файлов после будущей инициализации, а не существующий Git index; глобальные пользовательские Git-excludes и будущие правила .gitattributes не проверялись. После разрешённого git init нужно подтвердить результат штатными git status/check-ignore до добавления файлов.

Получен **31 файл-кандидат** для будущего version control:

```text
.gitignore
AGENTS.md
README.md
pytest.ini
requirements.txt
requirements/api.txt
requirements/common.txt
requirements/constraints.txt
requirements/mobile.txt
requirements/ui.txt
docs/api_test_results.md
docs/integration_audit.md
docs/mobile_refactoring_results.md
docs/poc_results.md
docs/ui_test_results.md
tests/api/conftest.py
tests/api/petstore.py
tests/api/requirements.txt
tests/api/test_petstore_smoke.py
tests/mobile/conftest.py
tests/mobile/material_files.py
tests/mobile/mobile_config.py
tests/mobile/requirements.txt
tests/mobile/test_material_files_functional.py
tests/mobile/test_material_files_smoke.py
tests/ui/conftest.py
tests/ui/requirements.txt
tests/ui/storefront.py
tests/ui/test_contact_us_upload.py
tests/ui/test_product_search.py
tests/ui/test_storefront.py
```

Исключённые существующие корни/файлы: `.venv/`, `.pytest_cache/`, `.pytest_cache_local/`, корневой и вложенные `__pycache__/`, `artifacts/`, `mobile_sample.txt`, `se-metadata.json`. Каталоги исключались до обхода: закрытый старый кэш не читался и не менялся. Обе локальные TXT/JSON-заготовки физически сохранены.

Дополнительно на контрольных путях проверены: JUnit XML, allure-results, reports, screenshots, Selene reports, логи, tmp, `.env`, `.env.local`, ключи и credentials JSON. `.vscode/launch.json` и вложенные личные файлы исключаются; `.vscode/settings.json` и `.vscode/extensions.json` разрешены для общих проверенных настроек. Самой .vscode сейчас нет. `.env.example` и `.env.template` допускаются только с фиктивными значениями; произвольные TXT/PNG-файлы в tests/fixtures не игнорируются, чтобы не скрывать полезные тестовые ресурсы.

`.gitignore` предотвращает обычное добавление совпавших путей, но не анализирует содержимое разрешённых исходников, не защищает от git add -f и не удаляет ранее tracked-файлы. Настоящих tracked-файлов пока нет. Полный аудит секретов/истории не проводился; перед публикацией необходимо проверить содержимое и будущий staged diff. Не следует трактовать 31 кандидат как автоматическое разрешение публикации.

### Статус проблем и оставшиеся риски

- Закрыты P1 по отсутствию ignore и схемы прямых зависимостей, P2 по README и testpaths; добавлены Mobile requirements и сохранены прежние команды установки API/UI.
- P1 готовности Mobile остаётся: Appium/эмулятор на этом этапе не проверялись заново и не запускались. Последний аудит отмечал недоступный /status и отсутствие устройств. Перед реальным прогоном требуется preflight из README.
- Не выполнен единый запуск 22 тестов. Collection подтверждает обнаружение/импорты, а не прохождение тестов.
- Не выполнена чистая установка; constraints фиксирует прямые версии, но не все транзитивные зависимости. Среда Python 3.14.3 остаётся единственной проверенной.
- Selenium Manager/Chrome, публичные API/UI-сервисы, английский Android-интерфейс и один общий udid остаются внешними зависимостями. Параллельный Mobile-запуск не разрешён этой подготовкой.
- Новые каталоги отчётов/run ID описаны в README, но runner и единые скриншоты/Allure-вложения Mobile пока не реализованы. Allure CLI не устанавливался.
- Следующий этап: отдельно согласовать подготовку среды и общий последовательный прогон с новым run ID. Текущий этап завершён без запуска тестовых функций, установки пакетов, удаления файлов и Git-операций.
