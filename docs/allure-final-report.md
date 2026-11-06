# Финальный Allure: текущий запуск и историческое сравнение

## Что содержится в №29

В исходных результатах ровно **22 passed**: API: Swagger Petstore v3 — 8,
Web UI: Automation Exercise — 8, Mobile: Material Files — 6.
Ревизия — `bdc9e97ceba5755d77a6f7c30f213517fe1083ca`.
История исходного отчёта содержит семь запусков №23–29.

Активный набор установлен по AST файлов `tests/test_*.py` с обходом подкаталогов,
настройке `testpaths = tests` и существующим результатам №29. Новая pytest
collection для этой проверки не запускалась. Функциональных тестов SauceDemo
в этом наборе нет. Их Page Objects остаются на диске, используются отдельными
модульными проверками `ci/tests`, но не импортируются активными UI-тестами
или их fixtures. Удалять их для очистки графиков не требуется.

## Почему виден SauceDemo

В Allure **3.16.0** `coverageDiffTreeMapAccessor.js` сопоставляет текущие
`historyId` с предыдущей точкой истории. Он добавляет в дерево и отсутствующие
теперь результаты с признаком `deleted`. В №28 был SauceDemo; в №29 вернулся
Automation Exercise. Поэтому Coverage diff map показывает удалённые восемь
SauceDemo-сценариев рядом с актуальными тестами. Красный блок этого графика
обозначает изменение состава, а не восемь новых падений в №29.

Это сравнение состава тестового набора, а не измерение покрытия исходного кода.
Status dynamics и другие исторические графики также используют прежние запуски;
удаление Python-модулей не удаляет результаты из истории. Поведение подтверждено
установленным кодом Allure 3.16.0 и исходным `charts.json` отчёта №29.

## Два безопасных представления

1. **Исходный исторический отчёт №29.** Сохранить неизменным. Для Overview
   вручную снять только Current status, severity и Success rate distribution.
   Status dynamics публиковать из этого отчёта вместе с реальными ошибками
   прошлых запусков. Обрезка изображения не меняет статистику отчёта.
2. **Отдельный отчёт «Build 29 — только текущий запуск, без истории».** Передать
   генератору копии только трёх исходных каталогов `allure-results` №29.
   Использовать отдельную конфигурацию без `historyPath`, с `appendHistory: false`
   и только графиками текущего запуска. Исторические test IDs в такой отчёт
   не импортируются. Это новое представление существующих данных, не новая сборка.

Для README предпочтительны снимки исходного отчёта. Если Overview взят из
отдельной генерации, это нужно явно указать в подписи. Его нельзя называть
отчётом с историей №23–29 или использовать вместо исторического Status dynamics.
Фильтровать/переписывать историю для красивой диаграммы не требуется.

## Предлагаемая изолированная генерация

Следующие команды — **процедура для отдельного согласованного выполнения**.
При подготовке этой документации генератор не запускался. Используются уже
установленные Allure CLI **3.16.0** и Node.js **24.14.1**; установки не нужны.
Не вызываются pytest, Jenkins, helper постоянной истории или публикация отчёта.

В обычном PowerShell из корня проекта:

```powershell
$source = Read-Host 'Каталог исходных артефактов Jenkins №29 с api, web, mobile'
$nodeExe = Read-Host 'Путь к существующему node.exe версии 24.14.1'
$allureCli = Read-Host 'Путь к существующему allure/cli.js версии 3.16.0'
$root = Join-Path (Get-Location) ('artifacts/allure-build-29-current-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $root -ErrorAction Stop | Out-Null

$inputs = @()
foreach ($area in @('api', 'web', 'mobile')) {
    $original = Join-Path $source "$area/allure-results"
    if (-not (Test-Path -LiteralPath $original -PathType Container)) {
        throw "Missing results directory: $area"
    }
    $copy = Join-Path $root $area
    Copy-Item -LiteralPath $original -Destination $copy -Recurse -ErrorAction Stop
    $inputs += $copy
}

$config = Join-Path $root 'allurerc.mjs'
@'
export default {
  name: 'Build 29 — only current run, no history',
  appendHistory: false,
  plugins: {
    awesome: {
      options: {
        reportName: 'Build 29 — only current run, no history',
        groupBy: ['feature', 'story'],
        charts: [
          { type: 'currentStatus', title: 'Current status' },
          { type: 'testResultSeverities', title: 'Test results by severity', includeUnset: true },
          { type: 'successRateDistribution', title: 'Success rate distribution' },
        ],
      },
    },
  },
};
'@ | Set-Content -LiteralPath $config -Encoding UTF8

$output = Join-Path $root 'report'
& $nodeExe $allureCli generate @inputs --config $config -o $output
if ($LASTEXITCODE -ne 0) { throw 'Allure generation failed; preserve artifacts for analysis' }
& $nodeExe $allureCli open $output
```

Конфигурация передаётся явно и не читает `ALLURE_HISTORY_PATH`: даже если эта
переменная задана в терминале, она не подключает историю к данному конфигу.
Каталоги трёх направлений не смешиваются и не перезаписывают исходные файлы.
Внутри копий сохраняются все оригинальные JSON и вложения, без редактирования
ID, статусов или JUnit. Не передавайте путь к историческому snapshot как input.

Перед публикацией такого представления сравните SHA-256 копий с исходными,
проверьте 22 passed, severity 12/9/1, три текущие feature и отсутствие SauceDemo
в дереве результатов. В таком отчёте отсутствие Status dynamics ожидаемо:
история намеренно не входит в область данных. Оригинальный отчёт №29 и
постоянное хранилище №23–29 должны остаться неизменными.
