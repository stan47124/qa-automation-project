# QA.Guru: дипломный проект автоматизации тестирования

Проект объединяет **22 независимых автотеста** на Python и pytest:

| Направление | Система | Проверки | Тестов |
| --- | --- | --- | --- |
| API | [Swagger Petstore v3](https://petstore3.swagger.io/) | Создание, чтение, обновление, поиск, изображение, удаление и два негативных сценария | 8 |
| Web UI | [Automation Exercise](https://automationexercise.com/) | Главная, каталог, поиск, карточка, добавление, корзина, количество, TXT в Contact Us без отправки формы | 8 |
| Mobile | Material Files для Android | Smoke, открытие папки, создание, переименование, копирование и удаление | 6 |

Ранее наборы успешно запускались отдельно: API и UI по два полных прогона, Mobile — три. **Первый общий последовательный прогон 31 октября 2026 года: 22 passed за 224,86 с**, без ошибок и пропусков; результаты сверены с JUnit и Allure. Подтверждён один общий прогон, а не длительная стабильность. Подробности — в [отчёте интеграции](docs/integration_run_results.md#первый-полноценный-интеграционный-прогон).

## Структура и технологии

```text
.
├── README.md
├── pytest.ini                        # testpaths=tests; локальный кэш
├── conftest.py                        # общий каталог отчётов и screenshots при ошибках
├── requirements.txt                  # установка всех направлений
├── requirements/
│   ├── constraints.txt               # единые проверенные версии
│   ├── common.txt                    # pytest и Allure
│   ├── api.txt                       # requests
│   ├── ui.txt                        # Selene и Selenium
│   └── mobile.txt                    # Appium Python Client и Selenium
├── tests/
│   ├── api/                          # PetstoreClient, fixtures, 8 тестов
│   ├── ui/                           # Storefront, fixtures, 8 тестов
│   └── mobile/                       # FilesScreen, настройки, fixtures, 6 тестов
├── docs/                             # аудит и результаты раздельных прогонов
└── artifacts/                        # локальные отчёты, исключены из Git
```

Каждое направление имеет свой `conftest.py`. Корневой conftest отвечает за отчётность, не импортирует Appium/Selene и не создаёт сессии: это позволяет устанавливать только выбранный профиль. Прежние `tests/api/requirements.txt` и `tests/ui/requirements.txt`, а также Mobile requirements ссылаются на соответствующие общие профили.

Проверенные прямые зависимости: pytest **9.2.0**, requests **2.34.2**, Selene **2.0.0rc10**, Selenium **4.52.0**, Appium Python Client **6.0.12**, allure-pytest **2.16.2**. Точные версии находятся только в `requirements/constraints.txt`. Constraints не является полным lock-файлом транзитивных зависимостей.

API использует requests.Session; UI — Selene с Selenium/Chrome; Mobile — Appium и UiAutomator2. Fixtures освобождают сессии в `finally`. Ожидания UI/Mobile выполняются средствами Selene/WebDriverWait без `time.sleep()`.

## Требования к окружению

- Проверенная локальная платформа: Windows, PowerShell, **Python 3.14.3**. Работа на других платформах/версиях Python пока не подтверждена.
- Для API нужен сетевой доступ к `https://petstore3.swagger.io/api/v3`.
- Для UI нужны Google Chrome и доступ к Automation Exercise. В прошлых UI-прогонах использовался Chrome 156.0.8078.76; Selenium Manager подбирает драйвер и может потребовать сеть/запись в свой локальный кэш. Каждый тест запускается headless с отдельным временным профилем 1440×1000.
- Для Mobile нужны Android SDK/ADB в PATH, существующий Android Emulator, Material Files, работающие Appium Server и UiAutomator2. Pip устанавливает только Python Client, **не сервер и не SDK**.
- Для HTML-отчёта Allure отдельно нужен Allure CLI и подходящая Java. Python-плагин сохраняет сырые результаты и не устанавливает CLI. Глобальные инструменты не устанавливаются из тестов автоматически.

Подготовку Android/Node.js/Appium/Chrome выполняют отдельно; никакие глобальные установки не включены в команду pip.

## Установка из корня проекта

Если `.venv` ещё нет, создать её, не перезаписывая существующее окружение:

```powershell
py -3.14 -m venv .venv
```

**Все Python-зависимости одной командой:**

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Либо установить только нужное направление:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements/api.txt
.\.venv\Scripts\python.exe -m pip install -r requirements/ui.txt
.\.venv\Scripts\python.exe -m pip install -r requirements/mobile.txt
```

Это альтернативы; для одного профиля достаточно одной соответствующей команды. Прежние пути установки `-r tests/api/requirements.txt`, `-r tests/ui/requirements.txt` и `-r tests/mobile/requirements.txt` тоже поддерживаются.

После установки:

```powershell
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m pytest --collect-only -q
```

Общая collection требует всех трёх профилей. Если установлен только один профиль, проверяйте соответствующий путь, например `pytest tests/api --collect-only -q`.

## Запуск наборов

Команды выполняются из корня через `.venv`:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/api -v
.\.venv\Scripts\python.exe -m pytest tests/ui -v
.\.venv\Scripts\python.exe -m pytest tests/mobile -v
```

Общий последовательный запуск при готовых Chrome, Android Emulator и Appium:

```powershell
.\.venv\Scripts\python.exe -m pytest tests -v
```

Не применять `-n auto` к одному эмулятору. Автоматических повторов API-запросов нет; сбои публичных сервисов и ошибки cleanup должны оставаться видимыми.

## Appium и Android Emulator

Текущие значения в `tests/mobile/mobile_config.py`:

| Параметр | Значение |
| --- | --- |
| Appium URL | `http://127.0.0.1:4723` |
| Проверенные Appium Server / UiAutomator2 | `3.9.0` / `8.7.3` |
| Android device | `emulator-5554` |
| Package | `me.zhanghai.android.files` |
| Activity | `.filelist.FileListActivity` |
| Базовая директория | `/sdcard/Download/qa_guru` |
| Явные ожидания / ADB timeout | 20 с |

Существующий локальный AVD — `Pixel_4`. Если он ещё не запущен, пример команды без сброса данных:

```powershell
& "$env:LOCALAPPDATA\Android\Sdk\emulator\emulator.exe" -avd Pixel_4 -port 5554
```

Appium запускается отдельно в терминале при уже установленных сервере и драйвере:

```powershell
appium --address 127.0.0.1 --port 4723
```

Перед Mobile проверить:

```powershell
adb devices -l
adb -s emulator-5554 shell getprop sys.boot_completed
adb -s emulator-5554 shell cmd package resolve-activity --brief me.zhanghai.android.files
adb -s emulator-5554 shell ls -ld /sdcard/Download/qa_guru
Invoke-RestMethod http://127.0.0.1:4723/status
```

Нужны состояние `device`, boot_completed=`1`, ожидаемая activity и готовый Appium. Материал Files должен быть установлен и иметь доступ к общей памяти; локаторы частично зависят от английского интерфейса. При первичной подготовке отсутствующую базовую папку можно создать через `adb -s emulator-5554 shell mkdir -p /sdcard/Download/qa_guru`; существующие данные не очищать.

Тесты создают собственные `test_<uuid>` внутри qa_guru и удаляют только их. Исходный `sample.txt` не нужен для работы тестов и не изменяется. Используется `noReset=True`: приложение и эмулятор не сбрасываются. Во время прогона не управлять тем же эмулятором вручную и не запускать вторую Mobile-сессию.

## Отчёты и локальные артефакты

При реальном запуске любого набора корневой conftest автоматически создаёт **новый** каталог `artifacts/<дата-время-Москва>_<uuid>/allure-results` и настраивает рядом `junit.xml`. В конце pytest печатает путь `Run reports`. Поэтому обычные команды запуска выше уже включают единую отчётность, а все 22 теста одного процесса попадут в один каталог. Collection через `--collect-only` каталог не создаёт.

Можно явно указать другой **новый или пустой** каталог, например:

```powershell
$runId = (Get-Date -Format 'yyyyMMdd_HHmmss') + '_' + [guid]::NewGuid().ToString('N')
$reportRoot = Join-Path 'artifacts' $runId
.\.venv\Scripts\python.exe -m pytest tests -v --alluredir="$reportRoot/allure-results" --junitxml="$reportRoot/junit.xml"
```

Для отдельного набора заменить `tests` на `tests/api`, `tests/ui` или `tests/mobile`. Allure CLI, если установлен отдельно, может открыть результаты командой `allure serve "$reportRoot/allure-results"`. Повторное использование непустого Allure-каталога, существующего JUnit-файла и `--clean-alluredir` отклоняется до запуска тестов, чтобы не смешивать и не удалять результаты.

Все тесты имеют epic, feature, story и title; общие API/UI/Mobile-действия записываются как шаги. При ошибках setup/call/teardown корневой hook пытается прикрепить PNG от зарегистрированного браузера/Android-сессии. Снимок делается только для уже созданной сессии; если сессия уже закрыта или снимок не получен, добавляется диагностический тип ошибки без подмены исходного падения. Для teardown после закрытия драйвера получение снимка не гарантируется.

API-вложения строятся по разрешённому списку: метод/маршрут, допустимый статус поиска, собственный синтетический Pet, число фото/тегов, размер бинарного тела, HTTP-код и время ответа. Cookies, заголовки, дополнительные произвольные поля, сырые изображения, чужие записи из поиска и свободный серверный текст не сохраняются. Автоматические stdout/stderr/log-вложения Allure отключены; обычный вывод pytest при этом сохраняется. Скриншоты и traceback всё равно требуют просмотра перед внешней публикацией.

Прежние API/UI-отчёты находятся в `artifacts/{api,ui}/run_01` и `run_02`; три раздельных Mobile-прогона зафиксированы в Markdown. Первый общий машинный отчёт на 22 passed — `artifacts/20261031_224029_f48c7c2cbb304cc0af433682f110f957/` (Allure, JUnit, консоль и сверка). Скриншоты Selene также могут сохраняться в pytest tmp_path/selene; полного HTML страницы в отчётах нет, чтобы не сохранять CSRF-токены.

`.gitignore` исключает окружение, bytecode, кэши, artifacts, отчёты, скриншоты, логи, временные файлы, ключи и локальные env. `mobile_sample.txt` и `se-metadata.json` исключены как локальные артефакты, но не удалены. Из `.vscode` разрешены только проверенные общие `settings.json` и `extensions.json`; в них нельзя помещать личные пути и секреты. Шаблоны `.env.example`/`.env.template` могут содержать только фиктивные значения. Не добавлять результаты или секреты через `git add -f`.

## Документация и ограничения

- [Аудит качества перед публикацией](docs/code_quality_audit.md).
- [Аудит и выполненный первый этап интеграции](docs/integration_audit.md).
- [Подготовка общей Allure-отчётности и проверка инфраструктуры](docs/integration_run_results.md).
- [Результаты API](docs/api_test_results.md).
- [Результаты Web UI](docs/ui_test_results.md).
- [Рефакторинг и три прогона Mobile](docs/mobile_refactoring_results.md).
- [Исторический PoC от 30 октября](docs/poc_results.md): описывает прежний lifecycle-тест, а не текущую архитектуру.

Публичные сервисы, реклама, изменения каталога, состояние эмулятора и подбор ChromeDriver остаются внешними зависимостями. Чистая установка с полным транзитивным lock, CI и повторяемость общих прогонов требуют отдельной проверки.
