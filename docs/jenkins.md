# Jenkins: API Pipeline на Windows

> **Исторический документ: первоначальный API-этап.** По подтверждённым
> пользователем результатам текущий Pipeline автоматически запускается через
> Poll SCM и выполняет 22 теста (8 API + 8 Web UI + 6 Mobile), SUCCESS;
> JUnit и Allure опубликованы. Актуальная точка входа —
> [README](../README.md#jenkins-ci) и [Mobile CI](jenkins-mobile.md).
> Ниже сохранены прежние команды и результаты, включая ограничения песочницы.
> Они не требуют повторного создания Job или изменения действующей конфигурации.

> Этот документ описывает первоначальную подготовку API Pipeline и прошлые проверки.
> Текущий Jenkinsfile расширен до API + Web UI + Mobile:
> [актуальная инструкция](jenkins-mobile.md), [этап подключения Web UI](jenkins-web.md).
> По последним данным пользователя агент запускается Планировщиком в сессии
> `<HOST>\<USER>`, API-сборки и Allure 3 работают. Повторно создавать Job,
> устанавливать Allure или менять автозапуск для подключения Web UI не требуется.

В корне добавлен `Jenkinsfile`; команды подготовки и запуска вынесены в
`ci/run-api.cmd`. Pipeline запускает только `tests/api` и устанавливает только
`requirements/api.txt` (pytest, requests, allure-pytest с общими constraints).
UI/Mobile не собираются и не запускаются. Полного транзитивного lock-файла пока нет.
По актуальным данным пользователя установлены Pipeline, Git, GitHub, JUnit и
Allure; Allure Commandline настроен с именем `allure`. Pipeline явно выбирает
этот инструмент через `commandline: 'allure'` и публикует отчёт автоматически.

## Первый запуск

1. После согласованного commit/push разместить эти файлы в Git-репозитории,
   доступном Jenkins. Локальные незакоммиченные файлы Pipeline from SCM не увидит.
2. Выбрать Windows-агент с меткой `windows-api`. Если подходящей метки ещё нет,
   её назначает администратор. Предпочтителен отдельный агент для тестов.
3. Проверить окружение именно под Windows-учётной записью агента. По последним
   данным агент `windows-api` работает под `<HOST>\<USER>`, его remote root —
   `<AGENT_ROOT>`; это отдельный процесс от службы контроллера Jenkins.
   доступ к Git, cmd.exe, Python 3.14 (локально проверена 3.14.3), запись
   в собственный Jenkins workspace и временный каталог, HTTPS-доступ к Git-хостингу,
   PyPI/хранилищу зависимостей и `petstore3.swagger.io`.
   Пользовательские PATH, Python launcher, `.venv` и профиль разработчика
   службе автоматически не доступны. Не использовать `<PROJECT_ROOT>`
   как custom workspace и не копировать локальную `.venv`.
4. Создать задачу **Pipeline → Pipeline script from SCM → Git**: URL репозитория,
   нужная ветка (например `*/main`), Script Path `Jenkinsfile`.
   Для закрытого репозитория выбрать отдельные read-only SCM credentials в Jenkins;
   не записывать их в URL или Jenkinsfile. Для публичного репозитория они обычно не нужны.
5. Значение `PYTHON_EXE` по умолчанию —
   `<PYTHON_EXE>`. Этот путь локально проверен:
   Python 3.14.3, фактический executable в `pythoncore-3.14-64`, не WindowsApps.
   Jenkinsfile явно передаёт параметр в `ci/run-api.cmd Prepare` через `withEnv`.
   `ci/check-python.py` проверяет выбранный интерпретатор и соответствие ему
   существующей `.venv`. При несовпадении сборка останавливается без замены окружения.
   Значение — один executable, без аргументов. На другом агенте его нужно изменить.
6. Выполнить **Build with Parameters** (у новой задачи первый запуск может
   отображаться как **Build Now**). Проверить Checkout, Prepare API environment,
   API tests, Test Result, Allure Report и Archived Artifacts.

Pipeline создаёт собственную `.venv` в workspace и повторно проверяет зависимости
при каждой сборке. При смене базового Python существующую `.venv` автоматически
не заменяет: нужен новый workspace или отдельное согласованное обслуживание.
Внутри одной задачи параллельные сборки запрещены; общий лимит — 20 минут.
Каждая сборка использует `artifacts/jenkins-<BUILD_NUMBER>-<uuid>`: старые отчёты
не удаляются и не смешиваются с новыми. Для повторного прогона запускать новую
сборку целиком, включая подготовку каталога отчётов.
Политику хранения сборок и workspace следует отдельно согласовать с администратором.

pytest exit 0 означает успех, exit 1 — UNSTABLE с результатами тестов;
остальные коды означают FAILURE. JUnit и Allure публикуются в `post/always`
стадии тестов, включая падения pytest. Allure использует `reportBuildPolicy: 'ALWAYS'`;
его вызов находится в `finally`, поэтому ошибка JUnit не мешает попытке публикации
Allure. Отсутствие XML считается ошибкой. Если Allure-каталог не создан, выводится
диагностика: отчёт без результатов не генерируется. Если подготовка
окружения не завершилась, тестовая стадия и её публикация не выполняются.
Архивируется только каталог текущего запуска, включая сырые Allure-результаты;
токены Jenkins и файл CLI-авторизации сборке не нужны.

## Доступ к настроенному Allure

Повторная установка плагина и инструмента не требуется. Перед первой сборкой
проверить, что настроенный **Manage Jenkins → Tools → Allure Commandline → allure**
доступен выбранному агенту и его Windows-пользователю, а для Allure 2 доступна
совместимая Java. Python-пакет `allure-pytest` сохраняет результаты, HTML генерирует
Jenkins-плагин с этим инструментом. Полное подключение будет подтверждено после
первой сборки со ссылкой Allure Report. Настройки безопасности и ACL не менять.

## Последующее подключение UI и Mobile

- UI: отдельная стадия/задача на подготовленном Windows-агенте, профиль
  `requirements/ui.txt`, команда `.\.venv\Scripts\python.exe -m pytest tests/ui -v`
  с собственными путями JUnit/Allure. Chrome, драйвер и кэш Selenium должны быть
  доступны именно служебной учётной записи. Текущая fixture уже использует headless.
- Mobile: отдельный агент в подходящей пользовательской сессии с Android SDK,
  ADB, Appium Server, UiAutomator2, существующим эмулятором и Material Files.
  Профиль `requirements/mobile.txt`, команда pytest для `tests/mobile`.
  Перед запуском — проверки из README. Адрес `127.0.0.1:4723` относится к машине
  агента; текущие настройки устройства жёстко заданы в `mobile_config.py`.
  Не рассчитывать на доступ Windows-службы к эмулятору разработчика. Один агент/
  эмулятор должен обслуживать одну mobile-сборку; `disableConcurrentBuilds()`
  защищает только одну задачу, не все задачи Jenkins. Сброс данных не требуется.
- Каждому набору выделить отдельные каталоги результатов; публикацию JUnit и
  Allure разместить в `post/always`. Эти стадии пока не добавлены в исполняемый
  Pipeline, чтобы их нельзя было случайно запустить без готовой инфраструктуры.

## Доступ Codex и проверка Jenkinsfile

Доступ Codex к Jenkins и окружение службы сборки — разные подключения.
Не переносить CLI-файл авторизации в репозиторий, workspace, артефакты или логи.
Для постоянного подключения использовать `codex-ci` с правами только на нужную
задачу (чтение/запуск и просмотр результатов), без Administer и Script Console.
Точные разрешения чтения списка плагинов и вызова linter администратор проверяет
отдельно; если они требуют избыточных прав, диагностику выполняет сам администратор.
Windows Sandbox Codex не является Jenkins Groovy Sandbox.

При заблокированном файле авторизации не менять ACL/песочницу. Администратор или
пользователь может выполнить из обычного PowerShell (команда не выводит секрет):

```powershell
$cli = Join-Path ([IO.Path]::GetTempPath()) 'jenkins-cli.jar'
$auth = Join-Path $env:USERPROFILE '.jenkins-cli\auth.txt'
java -jar $cli -s http://127.0.0.1:8080/ -auth "@$auth" who-am-i
java -jar $cli -s http://127.0.0.1:8080/ -auth "@$auth" list-plugins
Get-Content -Raw -Encoding UTF8 Jenkinsfile |
    java -jar $cli -s http://127.0.0.1:8080/ -auth "@$auth" declarative-linter
```

Без действующего доступа Jenkins linter локальный запуск CMD и успешный
pytest не подтверждают валидность Declarative DSL и доступность Jenkins steps.

## Предыдущая диагностика 1 ноября 2026 года (до текущей настройки Allure)

- `GET /login` без авторизации: HTTP 200, `X-Jenkins: 2.580.2`.
- `GET /api/json`, `/pluginManager/api/json` и `/computer/api/json` с ограниченным
  списком полей: HTTP 403. `/whoAmI/api/json` показывает `name=anonymous`.
  Права `codex-ci`, агенты и конфигурация службы не подтверждены.
- `POST /pipeline-model-converter/validate` с подготовленным Jenkinsfile:
  HTTP 403. Серверная проверка Declarative Pipeline не выполнена.
  Ранее CLI не смог прочитать файл авторизации (`AccessDeniedException`);
  повторное чтение, расширение разрешений и административный токен не применялись.
- Pipeline, Git, GitHub и JUnit установлены по данным пользователя; независимо
  проверить список плагинов не удалось. Статус Allure остаётся неподтверждённым.
- `.\.venv\Scripts\python.exe -m pip check`: `No broken requirements found`.
- `.\.venv\Scripts\python.exe -m pytest tests/api --collect-only -q`:
  **8 tests collected**, exit 0.
- При `REPORT_ROOT=artifacts/jenkins-local-3763e6bd560f415ba6ffc119a84132b7`
  выполнено `cmd.exe /d /c ci\run-api.cmd Test`. Фактическая команда внутри:
  `.venv\Scripts\python.exe -m pytest tests/api -v --alluredir="%REPORT_ROOT%/allure-results" --junitxml="%REPORT_ROOT%/junit.xml"`.
  Результат: **8 errors**, exit 1, без passed/skipped; все ошибки в setup,
  исходящие соединения к Petstore запрещены (`WinError 10013`).
  JUnit разобран как XML: tests=8, errors=8, failures=0, skipped=0.
  Созданы 8 Allure `*-result.json`. Это проверка формирования отчётов при сбое,
  а не успешный API-прогон или проверка их публикации в Jenkins.
- `git diff --check`: exit 0. Подготовка новой `.venv` и установка зависимостей
  под служебной учётной записью не выполнялись. Использовано существующее
  локальное окружение; UI/Mobile не запускались.
- Первоначальный PowerShell helper был заменён на CMD, поскольку запуск `.ps1`
  запрещён текущей политикой выполнения. Политика и настройки Windows не менялись.

## Проверки текущего Pipeline с включённым Allure

- `.\.venv\Scripts\python.exe -m pip check`: exit 0, зависимости согласованы.
- `.\.venv\Scripts\python.exe -m pytest tests/api --collect-only -q`:
  8 tests collected, exit 0.
- `cmd.exe /d /c ci\run-api.cmd Test` с
  `REPORT_ROOT=artifacts/jenkins-check-63774f623cc045f4819ff8df1211686e`,
  `PYTHONUTF8=1`, `PYTEST_ADDOPTS=--tb=short`: 8 errors за 1,40 с, exit 1.
  Все ошибки — setup, `WinError 10013` при соединении с Petstore.
  JUnit XML: tests=8, errors=8, failures=0, skipped=0; 8 Allure result JSON.
- `git diff --check`: exit 0.
- POST нового Jenkinsfile в `/pipeline-model-converter/validate`: HTTP 403.
  Groovy CLI локально не найден. Серверная проверка DSL, доступность инструмента
  `allure` под пользователем `jenkins` и публикация HTML не подтверждены.
  Сам Jenkins Job не создавался и не запускался.
- Исполняемый CMD helper не изменён относительно предыдущей подготовки;
  автотесты, requirements и pytest.ini не менялись. Новая установка зависимостей
  и запуск под пользователем `jenkins` не выполнялись.

## Создание задания qa-automation-project при недоступности CLI из Codex

CLI `who-am-i` из Codex повторно получил `AccessDeniedException` на файле
авторизации (exit -1). Анонимные запросы к Job и агентам получают HTTP 403.
Поэтому задание из Codex не создано; его наличие также не подтверждено.
Задание `qa-env-check` не запрашивалось и не восстанавливалось.

Подготовлен `ci/jenkins-job.xml.example`: Pipeline from SCM, приватный репозиторий
`https://github.com/stan47124/qa-automation-project.git`, ветка `*/main`,
Script Path `Jenkinsfile`, lightweight checkout и параметр Python для первого запуска.
`SET_GITHUB_CREDENTIALS_ID` — обязательная заглушка. Нужен ID существующих
Jenkins credentials для HTTPS-доступа к этому репозиторию (Username with password,
где пароль — GitHub token с доступом на чтение данного репозитория).
Это отдельные credentials от авторизации пользователя Jenkins `codex-ci`.
Значения секретов в XML не записывать. Job создаётся без автоматического запуска.

После уточнения ID и публикации CI-файлов в `main` пользователь может выполнить
из обычного PowerShell в корне проекта:

```powershell
$credentialId = Read-Host 'Jenkins GitHub credential ID (not a token)'
if ([string]::IsNullOrWhiteSpace($credentialId)) { throw 'Credential ID is required' }
[xml]$jobConfig = Get-Content -Raw -Encoding UTF8 ci/jenkins-job.xml.example
$jobConfig.SelectSingleNode('//credentialsId').InnerText = $credentialId
$cli = Join-Path ([IO.Path]::GetTempPath()) 'jenkins-cli.jar'
$auth = Join-Path $env:USERPROFILE '.jenkins-cli\auth.txt'
$jobConfig.OuterXml |
    java -jar $cli -s http://127.0.0.1:8080/ -auth "@$auth" create-job qa-automation-project
if ($LASTEXITCODE -ne 0) { throw 'Job creation failed; inspect the error before continuing' }
```

Команда требует разрешения создания заданий у `codex-ci`. Если задание уже есть,
`create-job` завершится ошибкой; не заменять его через `update-job` без проверки.
При отказе в разрешении создание выполняет уполномоченный пользователь; Codex
не меняет права и не применяет административный токен.
Ту же конфигурацию можно ввести через **New Item → qa-automation-project → Pipeline**
по шагам выше. Не задавать custom workspace: Jenkins создаст workspace внутри
`<AGENT_ROOT>` на агенте. Для lightweight checkout контроллеру тоже нужен
доступ к приватному репозиторию через выбранные credentials.

Перед первой сборкой выполнить CLI linter из обычного PowerShell (см. выше),
затем **Build with Parameters**, проверить `PYTHON_EXE` и запустить только API.
Новые файлы пока не закоммичены и не отправлены: SCM не сможет использовать
локальную подготовку до отдельного согласованного commit/push.

Проверки после выбора конкретного Python: запуск
`<PYTHON_EXE> ci/check-python.py` прошёл,
существующая локальная `.venv` соответствует выбранной установке. XML-шаблон
успешно разобран; definition, ветка, scriptPath и заглушка credentials проверены.
`pip check` прошёл, `pytest tests/api --collect-only -q` собрал 8 тестов, exit 0;
`git diff --check` прошёл. В этом этапе реальные API/UI/Mobile-тесты не запускались,
Prepare с установкой зависимостей также не выполнялся. Проверка под пользователем
агента и запуск Job остаются невыполненными.

Дополнительно проверено реальное создание виртуального окружения:
`<PYTHON_EXE> -m venv artifacts/python-venv-probe-85b8c791ec684702b3b672841af190da`
завершилось с exit 0. Python внутри окружения подтвердил `sys.prefix != sys.base_prefix`,
`-m pip --version` отработал (pip 25.3). Проверочное окружение осталось в игнорируемом
`artifacts`, зависимости проекта в него не устанавливались.

Это исторический путь одноразовой проверки venv. Пробное окружение удалено
при согласованной точечной очистке 2 ноября 2026 года; рабочая `.venv` сохранена.

Повторные запросы Job API, Credentials API (только id/displayName) и Declarative
linter вернули HTTP 403; `/login` — HTTP 200. Подходящий credential ID и доступ
именно Jenkins к приватному GitHub не подтверждены. Минимальное действие
уполномоченного администратора: выбрать существующие read-only GitHub credentials
или создать их для данного репозитория, сообщить только ID, проверить доступ
через SCM-конфигурацию Job. Создание/изменение Job требует отдельного подтверждения
пользователя и выполняется в доступной авторизованной сессии, без изменения
ACL, матрицы разрешений или Sandbox.

Источники: [Allure Pipeline step и параметры](https://www.jenkins.io/doc/pipeline/steps/allure-jenkins-plugin/),
[Jenkins Pipeline linter](https://www.jenkins.io/doc/book/pipeline/development/),
[JUnit step](https://www.jenkins.io/doc/pipeline/steps/junit/),
[Allure Jenkins integration](https://allurereport.org/docs/integrations-jenkins/).
