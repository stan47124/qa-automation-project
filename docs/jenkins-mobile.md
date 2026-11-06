# Jenkins: API + Web UI + Mobile

Текущий Pipeline: Checkout → Prepare API environment → API tests → Prepare Web UI
environment → Web UI tests → Prepare Mobile environment → Mobile tests → Publish results.
Сохранены агент `windows-api`, параметр `PYTHON_EXE`, API/Web helpers и их стадии.
По подтверждённым пользователем результатам: **SUCCESS, 22 passed** —
8 API + 8 Web UI + 6 Mobile, JUnit и общий Allure опубликованы. Poll SCM,
автозапуск существующего AVD Pixel_4 и Appium проверены реальной сборкой
при изначально выключенном эмуляторе. Последняя подтверждённая сборка — **№29** (ревизия `bdc9e97`),
Web UI — Automation Exercise, WebDriver Monitor отключён.
[Проверенные версии инструментов](environment.md).
См. также [общую инструкцию](../README.md#jenkins-ci).

Разделы настройки ниже описывают рабочую реализацию. Далее отдельно сохранена
история диагностики; прежние неудачные проверки и ограничения песочницы
не отменяют подтверждённый результат Jenkins.

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

При отсутствии устройства Pipeline автоматически запускает **существующий** AVD
из параметра `ANDROID_AVD` (по умолчанию `Pixel_4`). Устаревший opt-in параметр
Jenkins `START_ANDROID_EMULATOR` удалён из Jenkinsfile; в Mobile-этап передаётся
`START_ANDROID_EMULATOR=true` независимо от сохранённого ранее значения false.
Runner также включает автозапуск по умолчанию; локально можно явно передать
`START_ANDROID_EMULATOR=false`. `Check` никогда не запускает устройство.
Runner проверяет AVD через `-list-avds`,
запускает с `-port 5554 -no-window -no-snapshot-save`. Нет wipe-data, factory reset,
создания AVD, установки image или сброса приложения. Готовность определяется
по состоянию device, `sys.boot_completed=1` и успешному `pm path android`
с непустым ответом `package:`. Для обнаружения, запуска, загрузки и проверок
приложения действует единый срок 180 с; timeout каждой команды ограничен
оставшимся временем и 20 с. Тайм-ауты shell во время загрузки повторяются,
`offline` и отсутствие устройства ожидаются, `unauthorized` немедленно требуют
ручной авторизации без сбросов данных. Проверяются пакет Material Files,
activity и существующая `/sdcard/Download/qa_guru`.

Перед запуском эксклюзивным bind проверяются порты 5554/5555, без listen и
остановки их владельцев. DeviceLock защищает сотрудничающие CI-прогоны;
нативная блокировка AVD защищает от повторного открытия того же AVD другим
клиентом. При гонке запуска runner сообщает ошибку, не очищая lock-файлы AVD.

Собственный эмулятор после сборки завершается закрытием Windows Job Object,
включающего только собственное дерево процессов. Команда `adb emu kill` не
используется, чтобы не затронуть другой процесс при повторном использовании
серийного номера. `-no-snapshot-save` запрещает запись снимка; пользовательские
данные AVD не очищаются. Следующая сборка запускает тот же AVD заново. Чужой эмулятор и
общий ADB server не останавливаются. Запуск эмулятора в интерактивной сессии
Jenkins-агента требует отдельного подтверждения фактической проверкой, не только
наличия AVD на диске.

### Appium и очистка

Проверяются CLI и установленный UiAutomator2. Затем `/status` на
`http://127.0.0.1:4723`: существующий сервер переиспользуется без остановки
или изменения логов. Если сервера нет, runner проверяет свободный порт и запускает
собственный Appium на 127.0.0.1:4723, base path `/`, с логом `appium.log`.
Повреждённый HTTP-ответ или занятый порт не приводят к остановке чужого процесса.
На обнаружение, автоматический запуск и ожидание готовности выделен общий срок
60 с. `GET /status` повторяется с интервалом до 1 с и socket timeout до 2 с
(ограниченным оставшимся временем). Готовность подтверждает только `ready=True`.
TCP timeout сам по себе не прерывает запуск: runner проверяет возможность
эксклюзивного bind на `127.0.0.1:4723`, не вызывая listen. На Windows используется
`SO_EXCLUSIVEADDRUSE`. Если порт свободен, запускается собственный Appium;
если занят, runner повторяет `/status` существующего сервера, не запускает дубль
и не завершает чужой процесс. Ошибка прав на bind останавливает подготовку.
Порт освобождается сразу после проверки; если его успел занять другой процесс,
ошибка старта собственного Appium сохраняется в `appium.log` и завершает подготовку.
Тайм-ауты соединения/чтения повторяются; HTTP 404, некорректный JSON и ошибки
доступа требуют исправления окружения и не считаются отсутствием сервера.
Раннее завершение собственного Appium обнаруживается без ожидания полного срока.
`Check` только повторяет проверки готовности, никогда не запускает сервер.

Запрос `/sessions` не используется:
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
$sdk = Join-Path $env:LOCALAPPDATA 'Android\Sdk'
& "$sdk\emulator\emulator.exe" -list-avds
& "$sdk\platform-tools\adb.exe" devices -l
& "$sdk\platform-tools\adb.exe" -s emulator-5554 shell getprop sys.boot_completed
& "$sdk\platform-tools\adb.exe" -s emulator-5554 shell cmd package resolve-activity --brief --user current -a android.intent.action.MAIN -c android.intent.category.LAUNCHER -p me.zhanghai.android.files
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
`$env:ANDROID_AVD='Pixel_4'`. Автозапуск отсутствующего эмулятора уже включён.
Для проверки Jenkins дождаться автоматической сборки после согласованного push,
не запускать Job вручную. Проверить 22 passed, JUnit, общий Allure и текущий архив.

### Проверка автозапуска Android

SDK и `emulator -list-avds` проверены локально: SDK
`%LOCALAPPDATA%\Android\Sdk`, AVD `Pixel_4` существует.
Реальная проверка `adb devices -l` из песочницы завершилась ошибкой
`Cannot mkdir '\.android': Permission denied`; права и HOME не менялись.
Это ограничение проверки в Codex, а не доказательство ошибки ADB под агентом.
На Windows агент должен работать в интерактивной сессии пользователя, которому
принадлежат SDK/AVD. Запуск остаётся `-no-window`; ускорение виртуализации,
графический драйвер и доступность AVD под пользователем агента подтверждаются
реальным стартом. Права, виртуализация и задача Планировщика не меняются.

После согласования commit/push проверить сборку с причиной SCM change и нужным
SHA. Для сценария автозапуска перед push эмулятор должен быть выключен самим
пользователем вне выполняющихся тестов. Ожидаются `Started an owned emulator`,
`Android emulator-5554 ready for Mobile tests`, затем готовность Appium и
6 Mobile passed. Проверить SUCCESS, API 8 + Web UI 8 + Mobile 6 = 22 passed,
JUnit, Allure и архив `emulator.log`, `environment.log`, `adb-tools.log`.
При ошибке используется `diagnostic-traceback.log` и один инфраструктурный testcase.
Проверить вторую автоматическую сборку: собственный эмулятор стартует заново;
если эмулятор запущен пользователем, он переиспользуется и остаётся работать.

## История: первоначальные проверки в Codex

Сведения ниже зафиксированы при разработке Mobile CI до успешной сборки.
Результаты относятся к тому моменту и окружению Codex; текущий статус указан
в начале документа. Исторические отчёты сохранены.

- Подтверждены: Java Temurin 25.0.5, Node.js 26.13.0, Appium 3.9.0,
  UiAutomator2 8.7.3, Python Client 6.0.12, Emulator 37.2.13.0.
  ANDROID_HOME указывает на `%LOCALAPPDATA%\Android\Sdk`,
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

## История: исправление автозапуска Appium после сборки №17

В сборке №17 Android прошёл подготовку, но начальный TCP connect к Appium
завершился тайм-аутом. Предыдущая логика запускала сервер только после
ConnectionRefusedError, поэтому ветка автозапуска не выполнялась. Последующая
проверка пользователя показала недоступность порта; ручной запуск восстановил
`/status ready=True`. Наиболее вероятная причина — отсутствие запущенного
Appium в момент сборки вместе с необработанным вариантом ошибки соединения.

Исправление затрагивает только Mobile runner и его отдельные CI-тесты.
Jenkinsfile уже вызывает `ci/run-mobile.cmd Test`, поэтому менять Pipeline,
Poll SCM или API/Web helpers не требуется. DeviceLock и Windows Job Object
продолжают действовать на весь Mobile-прогон; собственный Appium завершается
после тестов, а следующий прогон при необходимости запускает новый.

После согласованного commit/push в main дождаться Poll SCM, не нажимая Build Now.
Проверить SHA и причину SCM change. При готовом Android и отсутствии Appium
до сборки `environment.log` должен содержать `Started an owned Appium server`,
затем `Owned Appium ready`; `appium.log` должен присутствовать в архиве.
Если Appium уже работает, ожидается `Reusing existing Appium` без его остановки.
Для проверки сценария автозапуска пользователь может заранее завершить только
свой вручную запущенный Appium в его терминале, вне выполняющейся сборки.
Runner не останавливает чужие серверы ради этой проверки.

Критерий полной проверки: SUCCESS, API 8 + Web UI 8 + Mobile 6 = 22 passed,
JUnit и общий Allure с результатами всех трёх направлений. При ошибке проверить
`environment.log`, `appium.log`, `diagnostic-traceback.log` в архиве и Allure.
Модульные проверки не заменяют подтверждение этого результата реальной сборкой.

## Material Files: пакет, launcher Activity и запуск

Описанная ниже проверка входит в рабочий runner. Диагностика прежнего отказа
и план следующего прогона сохранены как история подготовки исправления.
Последующий успешный прогон всех 22 тестов подтверждён пользователем.

`pm path` подтверждает наличие APK, но не успешное разрешение launcher intent
и не запуск Activity. В диагностируемой сборке пакет был установлен, а
`resolve-activity` вернул `No activity found`. Причина этого конкретного ответа
на устройстве пока не подтверждена. В Android 13 позиционный аргумент с именем
пакета уже подразумевает MAIN/LAUNCHER, а resolve-activity по умолчанию использует
текущего пользователя. Поэтому одни лишь явные флаги не доказывают исправления.
Возможна временная неготовность launcher resolution после холодной загрузки,
но это гипотеза, которую должны подтвердить журналы следующей сборки.

Проверки разделены:

1. `am get-current-user` определяет числовой ID; `pm path --user <ID> <package>`
   проверяет установку именно для этого пользователя. Логируются ID и число APK.
2. `cmd package resolve-activity --brief --user <ID> -a android.intent.action.MAIN
   -c android.intent.category.LAUNCHER -p <package>` получает launcher из
   установленного приложения. При отсутствии результата запрос повторяется до
   30 секунд, в пределах общего бюджета Android 180 секунд. Ошибки PM/прав
   не маскируются под отсутствие пакета. Отсутствующая launcher Activity остаётся
   причиной отказа; проверка не отключена.
3. Компонент разбирается отдельной строкой и нормализуется: короткое
   `.filelist.FileListActivity` и полное имя класса эквивалентны. Если launcher
   отличается от Appium APP_ACTIVITY (например, alias), дополнительный explicit
   resolve подтверждает настроенную Activity. Имена не заменяются предположениями.
4. В режиме Test `am start -W --user <ID> -a android.intent.action.MAIN
   -c android.intent.category.LAUNCHER -n <подтверждённый компонент Appium>`
   проверяет возможность запуска. Требуется `Status: ok`, одного exit code 0
   недостаточно. Ошибки прав/отсутствующего компонента отклоняются. Нет force-stop,
   очистки данных или переустановки. Check подтверждает пакет и Activity без запуска.

Официальный манифест Material Files объявляет
`me.zhanghai.android.files.filelist.FileListActivity` с MAIN/LAUNCHER. Это
совпадает с существующим APP_ACTIVITY, который оставлен без изменений. Манифест
upstream не подтверждает версию APK на эмуляторе: runtime resolve на агенте
проверяет фактическую установку перед тестами. В Codex эта проверка заблокирована
ошибкой ADB `Cannot mkdir '\.android': Permission denied`; обход не выполнялся.

Перед следующим согласованным push оставить AVD выключенным. Дождаться Poll SCM
без Build Now, проверить SHA и SCM change. В `environment.log` проверить
`installed=True`, числовой user, `launcher=...`, `Appium component confirmed=...`
и `launch verified Status=ok`, затем готовность Appium. При отказе изучить фазу,
exit code/категорию причины в environment.log и stdout/stderr конкретных команд
в adb-tools.log; полный traceback сохранён в diagnostic-traceback.log. Проверить
SUCCESS, 8 API + 8 Web UI + 6 Mobile, JUnit и общий Allure. Успех полного прогона
после этого исправления пока не подтверждён.

## Источники

- [Android Emulator CLI](https://developer.android.com/studio/run/emulator-commandline)
- [Appium server CLI](https://appium.io/docs/en/3.7/reference/cli/server/)
- [Windows Job Objects](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects)
- [Material Files AndroidManifest](https://github.com/zhanghai/MaterialFiles/blob/master/app/src/main/AndroidManifest.xml)
- [Android 13 Intent command arguments](https://raw.githubusercontent.com/aosp-mirror/platform_frameworks_base/android13-release/core/java/android/content/Intent.java)
- [Android 13 Package Manager shell](https://raw.githubusercontent.com/aosp-mirror/platform_frameworks_base/android13-release/services/core/java/com/android/server/pm/PackageManagerShellCommand.java)
