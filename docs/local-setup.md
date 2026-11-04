# Локальная подготовка Android и Appium

Команды выполняются в Windows PowerShell из корня проекта. Python-зависимости
устанавливаются по [README](../README.md#локальный-запуск). Ни pytest, ни CI runner
не устанавливают Android SDK, AVD, Appium Server, UiAutomator2 или Material Files.

## Предварительная настройка

1. Установите Android SDK с platform-tools и emulator, например через Android
   Studio; создайте AVD `Pixel_4`. Проект использует порт 5554 и `emulator-5554`.
2. Установите Node.js, Appium Server и драйвер UiAutomator2. Проверенное окружение
   проекта: Appium 3.9.0, UiAutomator2 8.7.3. Для runner также нужна Java в PATH.
3. Установите [Material Files](https://github.com/zhanghai/MaterialFiles),
   предоставьте доступ к общей памяти и используйте английский интерфейс.
4. Настройте `ANDROID_HOME` на каталог SDK. Если задан `ANDROID_SDK_ROOT`,
   он должен указывать на тот же SDK.

Для стандартного расположения SDK пример настройки текущего терминала:

```powershell
$env:ANDROID_HOME = Join-Path $env:LOCALAPPDATA 'Android\Sdk'
$env:PATH = "$env:ANDROID_HOME\platform-tools;$env:ANDROID_HOME\emulator;$env:PATH"
```

Если SDK установлен иначе, используйте его фактическое расположение.
Существующие данные эмулятора и приложения сохраняются.

## Прямой запуск pytest

Если AVD ещё не запущен, откройте его в Android Studio или выполните:

```powershell
& "$env:ANDROID_HOME\emulator\emulator.exe" -avd Pixel_4 -port 5554
```

В отдельном терминале запустите установленный Appium:

```powershell
appium --address 127.0.0.1 --port 4723
```

Проверьте готовность перед тестами:

```powershell
adb devices -l
adb -s emulator-5554 shell getprop sys.boot_completed
adb -s emulator-5554 shell pm path android
adb -s emulator-5554 shell cmd package resolve-activity --brief --user current -a android.intent.action.MAIN -c android.intent.category.LAUNCHER -p me.zhanghai.android.files
adb -s emulator-5554 shell ls -ld /sdcard/Download/qa_guru
Invoke-RestMethod http://127.0.0.1:4723/status
```

Ожидаются `emulator-5554` в состоянии `device`, boot_completed `1`, строка
`package:` от Package Manager, launcher Activity
`me.zhanghai.android.files/.filelist.FileListActivity`, существующий `qa_guru`
и `value.ready=True` от Appium. При другой форме вывода launcher убедитесь,
что указан тот же пакет и класс Activity.

При первичной подготовке отсутствующую базовую папку можно создать:

```powershell
adb -s emulator-5554 shell mkdir -p /sdcard/Download/qa_guru
.\.venv\Scripts\python.exe -m pytest tests/mobile -v
```

Фикстуры создают собственные `test_<uuid>/sample.txt` и удаляют только свои
каталоги. Уже существующий `qa_guru/sample.txt` тестам не нужен. `noReset=True`
сохраняет данные приложения. Не управляйте этим же устройством вручную во время
прогона и не запускайте несколько Mobile-сессий одновременно.

## Автоматическая подготовка через CI runner

В отличие от прямого pytest, runner может запустить существующий AVD и Appium,
дождаться готовности и запустить приложение. Он не создаёт AVD и базовый каталог.

```powershell
$env:REPORT_ROOT = 'artifacts/mobile-local-' + [guid]::NewGuid().ToString('N') + '/mobile'
$env:START_ANDROID_EMULATOR = 'true'
$env:ANDROID_AVD = 'Pixel_4'
cmd /d /c ci\run-mobile.cmd Test
```

Для проверки уже запущенного окружения без старта процессов, приложения и тестов:

```powershell
$env:REPORT_ROOT = 'artifacts/mobile-check-' + [guid]::NewGuid().ToString('N')
cmd /d /c ci\run-mobile.cmd Check
```

Каждый вызов требует нового, ещё не существующего `REPORT_ROOT`. Ранее запущенные
пользователем Appium и эмулятор не завершаются runner. Подробности управления
ресурсами и диагностики: [Mobile CI](jenkins-mobile.md).

## Отдельные проверки CI-инструментов

Они не входят в 22 теста приложений. Нужен JDK 17+ с `java` и `javac` в PATH;
Jenkins и настоящие Android/Appium не требуются. Windows-проверки управления
процессами создают собственные синтетические дочерние процессы.

```powershell
$ciRun = 'artifacts/ci-check-' + [guid]::NewGuid().ToString('N')
.\.venv\Scripts\python.exe -m pytest ci/tests -q --basetemp="$ciRun/tmp" --junitxml="$ciRun/junit.xml" --alluredir="$ciRun/allure-results"
```
