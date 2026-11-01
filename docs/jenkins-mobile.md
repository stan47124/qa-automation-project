# Jenkins: API + Web UI + Mobile

Текущий Pipeline: Checkout → Prepare API environment → API tests → Prepare Web UI
environment → Web UI tests → Prepare Mobile environment → Mobile tests → Publish results.
Сохранены агент `windows-api`, параметр `PYTHON_EXE`, API/Web helpers и их стадии.
Добавлены Mobile-стадии и третий путь при публикации. Ожидается 8 + 8 + 6 = 22
теста. Успешная сборка всех 22 в Jenkins пока не подтверждена.

## Настройка и запуск

`ci/run-mobile.cmd Prepare` устанавливает только Python-профиль
`requirements/mobile.txt` в существующую `.venv`, проверяет `pip check`.
Новых системных установок нет. `Test` вызывает `ci/mobile_ci.py`.
`Check` выполняет preflight, не запускает Appium, эмулятор и тесты.
Каждому вызову Test/Check нужен отдельный новый `REPORT_ROOT`.

SDK выбирается из `ANDROID_HOME`, затем `ANDROID_SDK_ROOT`, затем
`%LOCALAPPDATA%\Android\Sdk`. Противоречащие значения отклоняются. SDK-переменные
и PATH дополняются только для дочерних процессов, глобальные настройки не меняются.
ADB вызывается из platform-tools; этот путь добавляется в PATH для существующих
pytest-фикстур. Java, Node.js и npm-установка `appium.cmd` должны быть доступны
пользователю агента. CLI Appium разрешается через bin из установленного npm
package.json и запускается напрямую Node.js, без PowerShell shim и смены ExecutionPolicy.
Необычная установка Appium, отличная от стандартного глобального npm shim,
завершается понятной ошибкой, а не угадыванием пути.

### Android Emulator

Runner проверяет `adb devices -l`. Готовый `emulator-5554` переиспользуется;
его процесс после сборки не останавливается. Для offline-устройства runner
ждёт готовности, не запускает дубль. Unauthorized и другие состояния требуют
ручного действия. Если вместо него найден другой эмулятор, второй не запускается.

При отсутствии устройства по умолчанию сборка прекращается. Параметр Jenkins
`START_ANDROID_EMULATOR=true` разрешает старт **существующего** AVD из параметра
`ANDROID_AVD` (по умолчанию `Pixel_4`). Runner проверяет AVD через `-list-avds`,
запускает с `-port 5554 -no-window -no-snapshot-save`. Нет wipe-data, factory reset,
создания AVD, установки image или сброса приложения. Готовность определяется
по состоянию device и `sys.boot_completed=1`, с ограниченным ожиданием 180 с.
Проверяются пакет, activity и существующая `/sdcard/Download/qa_guru`.

Собственный эмулятор при штатном выходе получает `adb -s emulator-5554 emu kill`;
при сбоях действует очистка собственного дерева процессов. Чужой эмулятор и
общий ADB server не останавливаются. Запуск эмулятора в интерактивной сессии
Jenkins-агента требует отдельного подтверждения фактической проверкой, не только
наличия AVD на диске.

### Appium и очистка

Проверяются CLI и установленный UiAutomator2. Затем `/status` на
`http://127.0.0.1:4723`: существующий сервер переиспользуется без остановки
или изменения логов. Если сервера нет, runner проверяет свободный порт и запускает
собственный Appium на 127.0.0.1:4723, base path `/`, с логом `appium.log`.
Повреждённый HTTP-ответ или занятый порт не приводят к остановке чужого процесса.
Готовность ожидается через `/status` не более 60 с. Запрос `/sessions` не используется:
Appium 3.9.0 в проверенном окружении отвечает на него HTTP 404. Этот ответ не
считается неисправностью готового сервера. Конкурентные запуски CI координируются
через DeviceLock. [Диагностика исправления и тайм-аутов](mobile-preflight-diagnostics.md).

Readiness — ограниченные проверки состояния с интервалом, а не фиксированный
`sleep` вместо проверки. Каждая ADB-команда имеет timeout (обычно 20 с), список
драйверов — 45 с, pytest — 600 с. Mobile-стадия ограничена 16 минутами; общий
Pipeline сохраняет лимит 20 минут, включая API/Web и публикацию.

Для координации нескольких workspace/задач используется Windows mutex
`Global\QAGuru-emulator-5554` на весь Mobile-прогон. При занятости или отказе в
доступе runner завершается без запуска тестов. Все автоматические Mobile-запуски
должны использовать этот runner; ручное управление тем же устройством во время
сборки запрещено. Блокировка не обнаруживает клиентов, которые не используют
тот же mutex, и `/status ready=true` не означает отсутствие чужой сессии.

Собственные emulator/Appium/pytest находятся в отдельном Windows Job Object
с KILL_ON_JOB_CLOSE. Сначала запускается Python gate, который ждёт разрешения;
реальная команда стартует только после включения gate в Job. Поэтому ошибка
привязки не оставляет сервер без владельца. Закрытие Job или завершение runner
останавливает его дочернее дерево. PID-поиск, taskkill по имени, изменение ACL,
breakaway от Jenkins Job и административные права не используются. Если Windows
запрещает Job Object, runner останавливается. При потере узла/выключении Windows
публикация отчётов не гарантируется. При аварийном прекращении pytest сессия на
чужом Appium может остаться активной; её состояние проверяется пользователем
перед следующим прогоном. Автоматически удалять чужие сессии runner не будет.

## Тесты и результаты

Шесть существующих Mobile-тестов и capabilities не изменены: noReset=True,
Material Files, activity `.filelist.FileListActivity`, устройство emulator-5554.
Фикстуры завершают WebDriver в finally. Каждому тесту с данными создаётся
собственный `test_<uuid>` внутри qa_guru; cleanup ограничен этой папкой.
Скриншоты зарегистрированной Android-сессии при ошибках прикрепляет корневой
conftest в Allure; существующие steps/labels сохранены.

В `artifacts/<run>/mobile` сохраняются JUnit, Allure results, pytest-console.log,
environment.log, adb-tools.log и логи собственных Appium/Emulator, если они запускались.
Каждая проверка журналируется с START/END, временем UTC, длительностью и типом
исключения. Тайм-ауты и финальные ошибки сохраняют полный стек в
`diagnostic-traceback.log`, который также прикладывается к ошибкам в Allure.
ADB-лог содержит только команды подготовки/готовности; полный пользовательский
logcat не копируется. При failed/broken лог-файлы текущего runner добавляются
в Allure attachments; существующие steps, labels и скриншоты сохраняются.
Логи переиспользуемого чужого Appium не копируются.
Пути api/web не меняются и их результаты не перезаписываются.
JUnit читает `<run>/*/junit.xml`; Allure получает три отдельных results-пути одним
вызовом инструмента `allure`. Существующая публикация через post/always и
архивирование при ошибках сохранены. Устаревшие run не входят в публикацию.

При ошибке preflight создаётся **один** диагностический testcase infrastructure
с JUnit error и Allure broken; runner возвращает 2, Jenkins FAILURE. Это не
запуск шести тестов. После pytest сохраняется его exit code: 0 — успех,
1 — UNSTABLE, остальные — FAILURE. Существующий JUnit при поздней ошибке
не перезаписывается. Диагностический отчёт не маскирует отсутствие прогона.

## Подготовка Android вручную

Из обычного PowerShell в сессии пользователя агента (без повышения прав):

```powershell
$sdk = 'C:\Users\user\AppData\Local\Android\Sdk'
& "$sdk\emulator\emulator.exe" -list-avds
& "$sdk\platform-tools\adb.exe" devices -l
& "$sdk\platform-tools\adb.exe" -s emulator-5554 shell getprop sys.boot_completed
& "$sdk\platform-tools\adb.exe" -s emulator-5554 shell cmd package resolve-activity --brief me.zhanghai.android.files
& "$sdk\platform-tools\adb.exe" -s emulator-5554 shell ls -ld /sdcard/Download/qa_guru
cmd /d /c appium driver list --installed --json
```

Если AVD отсутствует, создание AVD/system image — отдельная согласованная установка.
Если приложение отсутствует, после согласования взять доверенный APK Material Files
фиксированной версии и SHA-256, проверить `Get-FileHash <apk> -Algorithm SHA256`,
затем выполнить `adb -s emulator-5554 install -r <apk>`. APK не включать в Git.
Один раз открыть приложение и выдать доступ к общей памяти; локаторы проверены
в английском интерфейсе. Если qa_guru отсутствует, можно отдельно создать только
эту папку через `adb -s emulator-5554 shell mkdir -p /sdcard/Download/qa_guru`.
Существующие файлы, разрешения Android и данные приложения не очищать.

## Первый запуск на агенте

После согласованного commit/push проверить Jenkinsfile через авторизованный linter.
Не менять существующий Job, агент или Планировщик. Для ручного preflight из корня:

```powershell
cmd /d /c ci\run-mobile.cmd Prepare
if ($LASTEXITCODE -ne 0) { throw 'Mobile Prepare failed' }
$env:REPORT_ROOT = 'artifacts/mobile-preflight-' + [guid]::NewGuid().ToString('N') + '/mobile'
cmd /d /c ci\run-mobile.cmd Check
```

Check требует уже работающих устройства и Appium, не запускает их сам.
Для полноценного Mobile-прогона задать **новый** REPORT_ROOT и вызвать
`cmd /d /c ci\run-mobile.cmd Test`. При необходимости установить только для процесса
`$env:START_ANDROID_EMULATOR='true'` и `$env:ANDROID_AVD='Pixel_4'`.
В Jenkins запустить сборку целиком: с готовым устройством оставить параметр false,
для его автоматического старта включить true. Проверить 8 стадий, 22 passed,
JUnit, общий Allure и текущий архив. Запуск всех 22 из Jenkins пока не выполнен.

## Фактическая проверка в Codex

- Подтверждены: Java Temurin 25.0.5, Node.js 26.13.0, Appium 3.9.0,
  UiAutomator2 8.7.3, Python Client 6.0.12, Emulator 37.2.13.0.
  ANDROID_HOME указывает на `C:\Users\user\AppData\Local\Android\Sdk`,
  ANDROID_SDK_ROOT не задан, JAVA_HOME — Temurin; adb доступен в PATH,
  emulator/sdkmanager найдены внутри SDK, в PATH не найдены.
- `emulator -list-avds`: Pixel_4. Найдены platform-tools, emulator,
  cmdline-tools и установленный image android-33-ext5 / API 33 / x86_64,
  revision 2. `sdkmanager --version` вернул exit 0, но сообщает `unknown (Android CLI)`
  и предупреждение об устаревшем sdkmanager. Установки и обновления не выполнялись.
- ADB `version` и `devices -l` завершаются с отказом доступа при обращении
  к `\.android`; runner зафиксировал exit 3221226505. Значение HOME и
  права не менялись ради обхода. Список устройств, boot_completed, наличие APK,
  activity, папки и возможность запуска эмулятора на агенте не подтверждены.
- `GET http://127.0.0.1:4723/status`: соединение из песочницы недоступно.
  Это не доказывает отсутствие сервера в обычной пользовательской сессии.
- `cmd /d /c ci\run-mobile.cmd Prepare`: exit 0; зависимости уже установлены,
  pip check — No broken requirements found. Pip сообщил о новой версии,
  обновление не выполнялось.
- `.venv\Scripts\python.exe -m pytest tests/mobile --collect-only -q`:
  6 collected. Collection API + UI + Mobile: 22 collected.
- `cmd /d /c ci\run-mobile.cmd Test` с новым REPORT_ROOT:
  `artifacts/mobile-ci-final-d7062f1f15c04a239bf0f33d2b2ed81a/mobile`.
  Exit 2 на ADB, **до** запуска эмулятора, Appium и pytest. XML разобран:
  1 infrastructure test / 1 error, Allure — 1 broken result с двумя
  диагностическими вложениями; файлы вложений проверены. Mobile-тесты
  не выполнялись; чужие устройства, файлы Android и процессы не затронуты.
- `.venv\Scripts\python.exe -m pytest ci/tests -q --tb=short` с отдельными
  basetemp/JUnit/Allure: **16 passed**. Это отдельные проверки CI, не дополнительные
  автотесты приложения; pytest.ini по умолчанию собирает только `tests/` (22).
  Проверены повторный запуск, busy Appium, отказ gate, таймауты, честный
  infrastructure report и очистка при ошибке. Windows Job Object и mutex также
  проверены на реальных синтетических дочерних процессах без Android/Appium.
- API/Web helpers повторно запущены последовательно: по **8 errors**, exit 1,
  WinError 10013 (Petstore / метаданные Selenium Manager). Артефакты:
  `artifacts/mobile-ci-regression-420d95a2c01d41e48929ebcb36685400/`.
  Это ограничения сети; успешное выполнение API/UI здесь не подтверждено.
- POST Jenkinsfile в `/pipeline-model-converter/validate`: HTTP 403.
  Проверка серверного Declarative DSL и реальная Jenkins-сборка не выполнены.
  API/Web helpers и тесты всех трёх направлений не изменены.

## Источники

- [Android Emulator CLI](https://developer.android.com/studio/run/emulator-commandline)
- [Appium server CLI](https://appium.io/docs/en/3.7/reference/cli/server/)
- [Windows Job Objects](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects)
