# Автозапуск Jenkins: Poll SCM и XML 1.1

> **Текущее состояние:** Poll SCM настроен и проверен пользователем. После push
> Jenkins автоматически выполняет Pipeline: SUCCESS, 22 passed, JUnit и Allure.
> Повторная настройка существующего Job для обычной работы не нужна.
> Команды изменения/восстановления ниже предназначены для согласованного
> воспроизведения настройки; для чтения состояния использовать VerifyOnly.

Расписание `H/5 * * * *` проверяет новые коммиты main примерно каждые пять минут.
Это Poll SCM, не Build periodically. Изменение Job и commit/push требуют разрешения.

## Причина и безопасное решение

System.Xml.XmlDocument в используемом Windows PowerShell отвергает XML 1.1.
Замена версии на 1.0 небезопасна: различаются допустимые символы и обработка NEL/U+2028.

PowerShell-функция `Enable-JenkinsScmPolling` сохранена. Она вызывает
`ci/jenkins_polling.py` через существующую `.venv`; XML обрабатывается
`ci/JenkinsScmXml.java` стандартным парсером установленного JDK.
Java уже нужна Jenkins CLI, новые программы/пакеты не устанавливаются.
Требуется JDK 17+, локально проверен JDK 25.0.5.
**Декларация не подменяется:** XML 1.1 читается и сохраняется как 1.1,
XML 1.0 остаётся 1.0. DTD и внешние сущности запрещены.

Java helper не подключается к Jenkins. XML передаётся через stdin, ответ
захватывается в память. Полная конфигурация в терминал не выводится.
Перед записью выполняются сериализация, повторный разбор, проверка версии и
семантических отпечатков XML. Сохраняются значимые текст/CDATA, имена/атрибуты,
порядок узлов, комментарии и processing instructions. Разрешённое отличие —
SCMTrigger и необходимый ему контейнер. Проверяется неизменность остальных
настроек: SCM, Credentials ID, ветка, Script Path, параметры, другие триггеры.
Форматирование XML может измениться, значения настроек — нет.

## Авторизация и резервная копия

CLI сохраняет **`-http`** и **`%USERPROFILE%\.jenkins-cli\codex-ci-auth.txt`**
через `-auth @...`. Административный `auth.txt` не используется.
Файл токена читает только Java CLI; Python/PowerShell его не читают и не печатают.
Перед get-job проверяется who-am-i=codex-ci. Сырые ошибки CLI не выводятся.

Перед update-job обязательна точная UTF-8 копия полученного XML вне репозитория.
По умолчанию — существующая `%USERPROFILE%\.jenkins-cli`, файл
`qa-automation-project-before-polling-<uuid>.xml`. Каталог должен уже иметь
ограниченный ACL: только текущий пользователь, SYSTEM и локальные Administrators;
владелец также один из них. Null DACL, недоступный ACL, symlink/junction и
расположение внутри репозитория отклоняются. ACL нового файла проверяется
**до записи XML**, целостность копии — через SHA-256.

ACL не меняются; папка с автоматически назначенными правами не создаётся.
Если проверки не проходят, выберите уже защищённый каталог или отдельно
согласуйте его подготовку. Не повышайте права и не отключайте Sandbox.

Перед update-job конфигурация повторно запрашивается; при обнаружении
конкурентной правки запись отменяется. CLI не даёт атомарный compare-and-swap:
не редактируйте Configure одновременно с этой командой.
После записи выполняется readback и сравнение значимых настроек.
При ошибке ответа/сохранения состояние сервера может быть неизвестно:
выводится путь копии, автоматического отката нет.

Проверка ACL из Codex отклонила каталог по умолчанию `.jenkins-cli` как
недостаточно ограниченный. Реальная резервная копия не создавалась.
Не считайте этот каталог заранее подходящим: укажите другой уже защищённый
каталог вне репозитория. Скрипт повторно проверит его ACL в обычной сессии.
Если подходящего каталога нет, потребуется отдельно согласованная подготовка;
текущий скрипт не изменяет разрешения ради продолжения.

## Команды из обычного PowerShell

Сначала только проверить, без записи:

```powershell
Set-Location E:\Progects\qa-automation-project
. .\ci\enable-scm-polling.ps1
Enable-JenkinsScmPolling -VerifyOnly
```

VerifyOnly не создаёт копий и не вызывает update-job. Если Poll SCM ещё отсутствует,
сообщение об отсутствии ожидаемого триггера является ожидаемым результатом.

**После разрешения на изменение Job:**

```powershell
$backupDir = Read-Host 'Путь к существующему защищённому каталогу вне Git-репозитория'
Enable-JenkinsScmPolling -BackupDirectory $backupDir
Enable-JenkinsScmPolling -VerifyOnly
```

Если .ps1 запрещён политикой, эквивалентные команды без смены ExecutionPolicy:

```powershell
.\.venv\Scripts\python.exe ci\jenkins_polling.py --verify-only
# Только после разрешения на изменение Job:
$backupDir = Read-Host 'Путь к существующему защищённому каталогу вне Git-репозитория'
.\.venv\Scripts\python.exe ci\jenkins_polling.py --backup-directory $backupDir
.\.venv\Scripts\python.exe ci\jenkins_polling.py --verify-only
```

Ожидается `Verified: qa-automation-project Poll SCM = H/5 * * * *; one SCM trigger; other settings preserved.`
Changed=False означает уже настроенный триггер: повторной записи/копии нет.
Дубликаты SCMTrigger отклоняются. Legacy trigger переносится в
PipelineTriggersJobProperty, а не дублируется. Другие триггеры сохраняются,
их количество выводится отдельно. TimerTrigger не создаётся и не включается;
уже существующий таймер скрипт самовольно не удаляет.
Сборки не запускаются; Job, Credentials, агент и Планировщик не создаются и не меняются.

## Восстановление из копии

Только после отдельного разрешения: проверить принадлежность копии нужному Job
и отсутствие нужных новых правок с момента её создания. Команда ниже сначала
сохраняет текущее состояние в защищённый каталог, затем восстанавливает копию
без изменения версии XML и проверяет результат. Содержимое копий не выводить.

```powershell
$backup = Read-Host 'Абсолютный путь к нужной резервной копии config XML'
@'
from pathlib import Path
import sys
import re
sys.path.insert(0, 'ci')
from jenkins_polling import JenkinsCli, XmlTool, SecureBackup, JOB
cli, xml = JenkinsCli(), XmlTool()
if not re.search(r'^Authenticated as:\s*codex-ci\s*$', cli.invoke(['who-am-i']), re.M):
    raise SystemExit('Expected codex-ci; restore refused')
path = Path(sys.argv[1])
text = path.read_bytes().decode('utf-8')
expected = xml.inspect(text)
current_backup = SecureBackup(path.parent).create(cli.invoke(['get-job', JOB]))
cli.invoke(['update-job', JOB], text)
saved = xml.inspect(cli.invoke(['get-job', JOB]))
if saved['fullHash'] != expected['fullHash'] or saved['version'] != expected['version']:
    raise SystemExit('Restore readback differs; inspect Job; current-state backup: ' + str(current_backup))
print('Restore verified; current-state backup: ' + str(current_backup))
'@ | .\.venv\Scripts\python.exe - $backup
```

## Проверка автоматической сборки

До push подтвердить Poll SCM, записать последний номер сборки и HEAD, убедиться
в отсутствии уже ожидающей сборки. Минимальный тестовый diff README — ссылка
на эту инструкцию. Commit/push выполняются только после согласия.
Build Now и ручной вызов build/buildWithParameters не использовать.

После push дождаться SCM polling (около пяти минут плюс quiet period и очередь),
проверить SCM Polling Log, причину `Started by an SCM change` / SCMTriggerCause
и checkout SHA отправленного коммита. Затем проверить SUCCESS, JUnit 22 теста
(API 8/UI 8/Mobile 6), общий Allure и архив текущего запуска.
Следующий polling без новых коммитов не должен создавать новую сборку.
При других уже существующих триггерах отдельно проверить причину запуска.

## Локальные проверки

Ниже сохранены результаты этапа разработки инструмента настройки Poll SCM.
Утверждения о невыполненных операциях относятся к этому этапу и сессии Codex,
а не к последующей успешной настройке и сборкам пользователя.

`ci/tests/test_jenkins_polling.py` использует реальный JDK XML 1.1 parser;
Jenkins CLI и backup ACL заменены заглушками. Конфигурация синтетическая,
реальные токены/Job не читаются. Записей в Jenkins нет.

Последняя проверка: **32 passed за 21,55 с**, артефакты
`artifacts/polling-xml-tests-0ea46b6dd32a43afa95cb4b2ab3dbe31/`.
Проверены XML 1.0/1.1 (включая XML-1.1-only символы), отсутствие/наличие
SCMTrigger, идемпотентность, legacy trigger, другие триггеры, Credentials ID и
параметры, неверный XML/DTD, авторизация, ошибки backup/сохранения/readback,
конкурентные правки и небезопасный/null DACL. Проверки синтаксиса
PowerShell/Python, `git diff --check` и чтение метаданных Windows ACL прошли.
Реальный update-job, backup живой конфигурации и Jenkins-сборка не выполнялись.

```powershell
$run = 'artifacts/polling-xml-tests-' + [guid]::NewGuid().ToString('N')
.\.venv\Scripts\python.exe -m pytest ci/tests/test_jenkins_polling.py -q --tb=short `
  "--basetemp=$run/tmp" "--junitxml=$run/junit.xml" "--alluredir=$run/allure-results"
```

Источники: [XML 1.1](https://www.w3.org/TR/xml11/),
[System.Xml / XmlReader](https://learn.microsoft.com/en-us/dotnet/api/system.xml.xmlreader),
[Poll SCM](https://www.jenkins.io/doc/book/pipeline/syntax/#triggers).
