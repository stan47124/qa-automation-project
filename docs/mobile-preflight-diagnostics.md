# Appium preflight: исправление /sessions и диагностика TimeoutError

## Что установлено по реальным журналам

Изучены локально доступные артефакты Jenkins в
`E:\JenkinsAgent\workspace\qa-automation-project\artifacts`:

- **Сборка 14**, run `jenkins-14-3698ff74399f4fd191673016e247bf7c`:
  JUnit содержит `TimeoutError: timed out`. adb-tools.log подтверждает device,
  boot_completed=1, пакет, ожидаемую activity и проверку qa_guru.
  environment.log заканчивается сообщением о переиспользовании эмулятора;
  сообщения о переиспользовании/запуске Appium нет.
- **Сборка 15**, run `jenkins-15-5134016b05af4bc3a4f03ecb8b540c76`:
  Appium был переиспользован, JUnit содержит
  `RuntimeError: Appium endpoint /sessions returned HTTP 404`.
  Это отдельный дефект; он не доказывает причину тайм-аута сборки 14.

Предыдущий main сохранял только тип и сообщение ошибки, без полного traceback.
В артефактах этих запусков полного стека нет. Поэтому точная строка тайм-аута
сборки 14 не установлена. По порядку операций он локализован в начальной
Appium-проверке: HTTP open/body первого `/status`, либо последующий TCP probe,
если HTTP вернул недоступность. До ожидания ready и `/sessions` этот запуск
не дошёл. ADB/subprocess обычно дал бы другой тип (`TimeoutExpired`), а общий
deadline ожидания — другое сообщение (`Timed out waiting for ...`).

Во время текущей проверки read-only запросы из Python (без изменения процессов,
устройств или сессий) дали `/status ready=true` примерно за 0,021 с и
`/sessions` HTTP 404 как RuntimeError, `is_timeout=False`.
Первоначальный тайм-аут не воспроизвёлся. Журнал проверки:
`artifacts/appium-http-diagnostic-33e4d4422ff14f8c96617303fd22453a/environment.log`.
Jenkins lastFailedBuild API вернул HTTP 403; его конфигурация не изменялась.

## Исправление

prepare_appium проверяет только `/status`, не зависит от `/sessions` и не
перечисляет/удаляет сессии. Существующий сервер не останавливается.
Global mutex `QAGuru-emulator-5554` (DeviceLock) по-прежнему удерживается от
начала preflight до окончания тестов и очистки процессов. Занятость блокировки
останавливает runner до любых команд и обращений к Appium.
Все CI-клиенты данного устройства должны использовать этот механизм.
Ручные и другие клиенты без mutex им не координируются: во время CI их нельзя
запускать. ready=true подтверждает готовность сервера, не свободное устройство.

read_appium возвращает None только при ConnectionRefusedError внутри URLError.
Сетевые тайм-ауты, ошибки прав и остальные транспортные ошибки не маскируются
под отсутствие сервера и не провоцируют попытку запустить второй Appium.
HTTP 404 остаётся HTTP-ошибкой маршрута, а не тайм-аутом.

## Диагностика следующего сбоя

В environment.log для каждой операции пишутся UTC-время, START/END,
status, elapsed_s, exception. Раздельно отмечены:

- получение DeviceLock, обнаружение CLI, Android-проверки;
- каждый subprocess, его timeout и exit code;
- HTTP open и HTTP body для `/status` (socket timeout остаётся 2 с);
- TCP port probe (2 с), запуск собственного Appium;
- readiness wait (60 с) и каждый poll с ready/remaining_s;
- запуск pytest, ожидание (600 с), остановка собственного эмулятора и общий resource scope.

wait_until не принимает успешный ответ, полученный уже после deadline.
При TimeoutError, вложенном timeout в URLError или TimeoutExpired стек сохраняется
немедленно, до очистки, в `diagnostic-traceback.log`. Финальная ошибка main
также добавляет полный стек с цепочкой исключений. Это сохраняет первоначальный
тайм-аут, даже если cleanup затем выбросил другую ошибку.
TimeoutExpired дополнительно сохраняет частичные stdout/stderr subprocess
в adb-tools.log. Диагностический traceback архивируется и прикладывается в Allure.
Стек сохраняется без дампа локальных переменных, HTTP-body и секретов.

Следующий сбой нужно анализировать по первому `status=ERROR` и соответствующему
стеку, различая HTTP open, чтение ответа, TCP connect, readiness deadline,
subprocess и cleanup. Не увеличивать тайм-ауты и не менять процессы без этих данных.

## Проверки и ограничения

Модульные проверки покрывают работающий/недоступный Appium, отсутствующий маршрут,
занятое устройство, HTTP open/body timeout, обёрнутый URLError timeout,
TCP timeout, readiness deadline, TimeoutExpired и сохранение стека после
ошибки cleanup. Вызовы сети и запуска Appium в них заменены заглушками.
Две прежние интеграционные проверки с запуском синтетических дочерних процессов
исключены из данного прогона, чтобы не запускать процессы без согласования.

Последний фактический результат: **26 passed, 2 deselected за 1,50 с**.
Отчёты модульного прогона:
`artifacts/mobile-preflight-fix-8a66030a77b848db91be57ef084719f0/`.
Проверка DeviceLock при занятости выполнялась с подменённым Win32 kernel API,
без захвата реального устройства и без запуска дочерних процессов.
`git diff --check` прошёл; отсутствие изменений API/Web и Jenkinsfile подтверждено.

Команда воспроизведения модульного прогона из корня, с новыми путями:

```powershell
$checkRoot = 'artifacts/mobile-preflight-fix-' + [guid]::NewGuid().ToString('N')
.\.venv\Scripts\python.exe -m pytest ci/tests -q --tb=short `
  -k 'not test_job_closes_only_its_gated_process and not test_device_lock_rejects_a_second_process' `
  "--basetemp=$checkRoot/tmp" "--junitxml=$checkRoot/junit.xml" "--alluredir=$checkRoot/allure-results"
```

Полный Pipeline и Mobile-прогон в рамках исправления не запускались. API/Web UI,
Jenkinsfile, системные настройки и управление процессами не изменялись.
Commit/push требуют отдельного разрешения.
