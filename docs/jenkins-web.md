# Jenkins: API + Web UI

> Этап подключения первых 16 тестов. Теперь Jenkinsfile включает также Mobile;
> [текущая конфигурация и проверки](jenkins-mobile.md). Ниже сохранены подробности
> подключения Web UI и фактические результаты его первоначальной проверки.

Jenkinsfile выполняет последовательно Checkout → Prepare API environment →
API tests → Prepare Web UI environment → Web UI tests → Publish results.
Агент `windows-api`, `checkout scm`, параметр `PYTHON_EXE` и API helper сохранены.
Используется одна workspace `.venv`; Web Prepare устанавливает профиль
`requirements/ui.txt`, затем выполняет `pip check`. Mobile не устанавливается
и не запускается. Параллельного выполнения нет, общий лимит остаётся 20 минут.
Ожидается 8 API + 8 UI = 16 тестов. Подтверждения успешной Jenkins-сборкой пока нет.

## Браузер

Фактический путь тестов — `tests/ui`, не `tests/web`. Используется Chrome через
`webdriver.Chrome(options=options)` без заданного пути к драйверу. Selenium Manager
сам подбирает ChromeDriver; ему нужны сеть и доступ к кэшу пользовательской сессии.
Chrome и драйверы не устанавливаются системно скриптом CI.

Fixture проверяет `HEADLESS`: значения `true`, `1`, `yes` (без учёта регистра)
включают `--headless=new`. Без переменной или при `HEADLESS=false` открывается
обычное окно. Jenkins задаёт `HEADLESS=true` только для Web UI-стадии.
Сохраняются размер окна 1440×1000, отключение уведомлений, отдельный временный
профиль Chrome для каждой сессии и `driver.quit()` в `finally`, включая ошибки
настройки после создания WebDriver. Личный профиль Chrome не используется.
Загрузка TXT создаёт синтетический файл через `tmp_path`, абсолютного личного
пути нет. Форма Contact Us не отправляется. Ожидания, локаторы, Allure steps,
labels и attachments не менялись; `sleep` не добавлялся.

## Результаты

На каждой сборке создаётся новый `artifacts/jenkins-<BUILD_NUMBER>-<uuid>`:

```text
<run>/api/junit.xml
<run>/api/allure-results/
<run>/web/junit.xml
<run>/web/allure-results/
<run>/web/pytest-tmp/
```

API получает `REPORT_ROOT=<run>/api`, UI — `<run>/web`. API helper не изменён;
пути передаются через `withEnv`. Web helper использует существующую `.venv`,
запускает только `tests/ui` и возвращает exit code pytest. Для `tmp_path` задаётся
`--basetemp=<run>/web/pytest-tmp`: общий pytest-каталог пользователя не используется.
Всегда нужен новый run: корневой conftest запрещает повторное использование
Allure/JUnit, а pytest может очищать свой basetemp. Запускайте сборку целиком,
не перезапускайте только тестовую стадию с прежним каталогом.

JUnit читает `<run>/*/junit.xml`, объединяя оба набора в Jenkins Test Result.
Перед обычной стадией публикации проверяется наличие XML обоих наборов.
Allure вызывается **один раз**, с `commandline: 'allure'`, политикой `ALWAYS`
и двумя отдельными путями results. Не нужно объединять файлы вручную или
писать оба процесса pytest в один непустой Allure-каталог.

pytest exit 1 даёт UNSTABLE и позволяет перейти ко второму набору и публикации;
exit 0 — успех, остальные коды — FAILURE. Если стадия подготовки/тестов оборвала
Pipeline, `post/always` публикует имеющиеся результаты через ту же функцию.
Ошибка JUnit не мешает попытке Allure (`finally`); архивирование текущего run
также выполняется через `finally`, включая ошибку публикации. Флаг исключает
повторную генерацию отчёта, если публикация в обычной стадии уже была начата.
Если тесты не успели создать ни одного XML, это ошибка, а не успешная пустая сборка.
Предыдущие каталоги не удаляются и не попадают в glob текущей сборки.

## Локальный запуск в условиях CI

В обычном PowerShell из корня проекта, после проверки существующей `.venv`:

```powershell
$env:PYTHON_EXE = 'C:\Users\user\AppData\Local\Python\bin\python.exe'
cmd /d /c ci\run-api.cmd Prepare
if ($LASTEXITCODE -ne 0) { throw 'API Prepare failed' }
$run = 'artifacts/local-ci-' + [guid]::NewGuid().ToString('N')
$env:REPORT_ROOT = "$run/api"
cmd /d /c ci\run-api.cmd Test
$apiExit = $LASTEXITCODE
cmd /d /c ci\run-web.cmd Prepare
if ($LASTEXITCODE -ne 0) { throw 'Web Prepare failed' }
$env:HEADLESS = 'true'
$env:REPORT_ROOT = "$run/web"
cmd /d /c ci\run-web.cmd Test
$webExit = $LASTEXITCODE
Write-Output "API exit=$apiExit; Web exit=$webExit; reports=$run"
```

Для UI collection: `.\.venv\Scripts\python.exe -m pytest tests/ui --collect-only -q`.
Для запуска с окном: `$env:HEADLESS='false'`, затем обычный pytest для `tests/ui`.

## Фактические проверки при подготовке

- Chrome найден: `C:\Program Files\Google\Chrome\Application\chrome.exe`,
  версия 156.0.8078.76. Selenium 4.52.0, Selene 2.0.0rc10, Selenium Manager найден;
  в кэше есть ChromeDriver 156.0.8078.73 и 156.0.8078.80. Наличие кэша само по
  себе не подтвердило получение драйвера или запуск браузера.
- `cmd /d /c ci\run-web.cmd Prepare`: exit 0, зависимости уже установлены,
  `pip check` — No broken requirements found. Pip сообщил о новой версии;
  обновление не выполнялось.
- `.venv\Scripts\python.exe -m pytest tests/ui --collect-only -q`: 8 collected.
- Первый Web запуск: 8 setup errors из-за WinError 5 в общем `%TEMP%/pytest-of-user`.
  Web helper после этого получил отдельный basetemp текущего запуска.
- Повторный `cmd /d /c ci\run-web.cmd Test` с `HEADLESS=true`,
  `PYTEST_ADDOPTS=--tb=short`, `PYTHONUTF8=1`, `SE_TIMEOUT=10`:
  **8 errors**, exit 1. Selenium Manager exit 65: сеть к метаданным
  `googlechromelabs.github.io` запрещена, WinError 10013. Браузер не создан;
  это ограничение проверки в песочнице, а не подтверждённый дефект тестов.
- `Invoke-WebRequest https://automationexercise.com`: соединение недоступно
  из песочницы. Доступ именно из процесса Jenkins-агента пока не проверен.
- API collection: 8 collected. `cmd /d /c ci\run-api.cmd Test` в том же новом
  run, подкаталог api: **8 errors**, exit 1, сеть к Petstore запрещена,
  WinError 10013. Успешный регрессионный API-прогон здесь не подтверждён.
- Последний локальный run:
  `artifacts/jenkins-ui-check-15609f5b107743aa856971b5d1d0cea2/`.
  Отчёты и console logs сохранены там, прежние API-отчёты не изменены.
- XML обоих наборов разобран: по 8 tests / 8 errors / 0 failures / 0 skipped;
  суммарно 16 tests / 16 errors. В двух Allure-каталогах 16 result JSON с
  различными UUID, все со статусом broken. Проверена структура входных данных
  для объединения, но HTML-отчёт Allure 3 из Jenkins здесь не генерировался.
- `.venv\Scripts\python.exe -m pytest tests/api tests/ui --collect-only -q`:
  16 collected, без Mobile. Синтаксис изменённой Python fixture и
  `git diff --check` проверены успешно.
- POST изменённого Jenkinsfile в `/pipeline-model-converter/validate`:
  HTTP 403. Groovy CLI не найден, поэтому полная проверка Declarative DSL
  недоступна. Jenkins-сборка не запускалась, Pipeline SUCCESS не подтверждён.

## Первый запуск в Jenkins

После отдельного согласования commit/push отправить изменения в `main`.
Существующий Job должен по-прежнему читать `Jenkinsfile` через Pipeline from SCM.
На агенте под `WIN-1DRM97P1O7A\user` проверить Chrome, запись в workspace,
временные каталоги/кэш Selenium и доступ к Automation Exercise, Petstore,
PyPI и адресам Chrome for Testing. Не менять права и не останавливать агент.
Проверить Jenkinsfile через штатный Declarative linter из авторизованной сессии.
Затем запустить новую сборку с прежним `PYTHON_EXE`.

Убедиться, что выполнены все шесть стадий, Test Result показывает 16 тестов,
Allure Report содержит API и Web UI с общим числом 16, опубликован только текущий
run, а итоговый статус SUCCESS. При ошибках смотреть Console Output и отчёты;
не включать Mobile и не маскировать ошибки повторами или `allowEmptyResults=true`.

Источники: [Selenium Manager](https://www.selenium.dev/documentation/selenium_manager/),
[Allure Pipeline step](https://www.jenkins.io/doc/pipeline/steps/allure-jenkins-plugin/).
