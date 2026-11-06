# Web UI: SauceDemo

> **Историческая реализация, не текущий Web UI.** SauceDemo использовался
> в сборках №26–28. Начиная с ревизии `bdc9e97` активен
> [Automation Exercise](web-ui-automation-exercise.md), подтверждённый №29.
> Указанные ниже тестовые модули удалены из текущего дерева; их исходники
> доступны в [ревизии SauceDemo](https://github.com/stan47124/qa-automation-project/tree/81bb1e2adc2b36c431c039ce50d8ef7b97ceee03/tests/ui).
> Команды, SD-UI IDs и распределение 12/10/0 ниже относятся к тому этапу.

Набор заменяет восемь сценариев Automation Exercise восемью сценариями SauceDemo.
API/Mobile, Jenkinsfile, ci/run-web.cmd, зависимости и постоянная история не меняются.
Реализация подготовлена в отдельном worktree; публикация требует отдельного разрешения.

| ID | Модуль и тест | Story | Severity |
|---|---|---|---|
| SD-UI-001 | test_authentication.py / test_successful_login | Authentication | critical |
| SD-UI-002 | test_authentication.py / test_invalid_credentials | Authentication | normal |
| SD-UI-003 | test_authentication.py / test_locked_out_user | Authentication | normal |
| SD-UI-004 | test_inventory.py / test_sort_products_by_price | Inventory | normal |
| SD-UI-005 | test_cart.py / test_add_product_to_cart | Cart | critical |
| SD-UI-006 | test_cart.py / test_remove_product_from_cart | Cart | critical |
| SD-UI-007 | test_checkout.py / test_complete_checkout | Checkout | critical |
| SD-UI-008 | test_checkout.py / test_checkout_required_fields | Checkout | normal |

Epic: QA.Guru graduation project; feature: Web UI: SauceDemo; parentSuite: Web UI;
suite: SauceDemo. Общие severity: 12 critical, 10 normal, 0 minor.

## Структура и изоляция

tests/ui/saucedemo содержит LoginPage, InventoryPage, CartPage, CheckoutPage,
неизменяемые демонстрационные данные и денежные helpers на Decimal. Сортировка
сверяет все цены и состав товаров, а не отдельную позицию. Checkout проверяет
товар, subtotal, tax, total, подтверждение и пустую корзину после завершения.
Каждый обязательный checkout field проверяется с корректными остальными полями.
Форма полностью восстанавливается вводом с клавиатуры, включая пустые значения
в React. Три проверки входят в один тест, поэтому collection остаётся 22.

ChromeDriver создаёт временный профиль на каждый тест. Login выполняется через
UI; cookies/localStorage не переносятся. HEADLESS, размеры окна, уведомления,
тайм-ауты 45/15 секунд и finally/quit сохранены. Ретраев и sleep нет.

## Безопасность диагностики

Сырые PNG от общего hook для Web UI и автоматические screenshots/HTML Selene
не используются. Callback перед teardown сохраняет только очищенное состояние
и PNG известного контейнера каталога/корзины/checkout. Login, неизвестные страницы,
challenge/CAPTCHA и страницы с полем пароля не снимаются. Полный viewport не
сохраняется: Login содержит опубликованный учебный пароль даже вне input.
Не читаются cookies и содержимое личного профиля. Из URL исключены query,
fragment, userinfo и неизвестные пути. Неизвестные titles скрываются.

Объект демонстрационного пользователя исключает username/password из repr.
Заполнение авторизации не использует пароль-bearing Selene-команды или Allure
параметры. Исключение ввода сохраняет тип без исходного сообщения и цепочки,
которая могла содержать отправленное значение. Diagnostic errors не подменяют
исходную ошибку. JSON session lifecycle фиксирует результат закрытия драйвера.

## Локальный запуск

Из корня рабочего дерева с доступной существующей .venv:

```powershell
.\.venv\Scripts\python.exe -m pytest ci/tests -q
.\.venv\Scripts\python.exe -m pytest tests --collect-only -q
$env:HEADLESS='false'
.\.venv\Scripts\python.exe -m pytest tests/ui -v
$env:HEADLESS='true'
.\.venv\Scripts\python.exe -m pytest tests/ui -v
```

В изолированном worktree можно использовать абсолютный путь к Python основной
.venv, ничего не устанавливая. Каждому прогону нужны новые basetemp/alluredir/
junitxml; отчёты остаются в игнорируемом artifacts. Локальные прогоны pytest
не обновляют постоянную историю. Авторизацию, платежи и доставку вне учебного
приложения не выполнять; данные checkout синтетические.

## IDs и переход истории

SD-UI-* — идентификаторы сценариев. Allure testCaseId/historyId вычисляются из
полного имени и параметров; allure.id не подменяет эти hashes. Имена новых модулей
и функций фиксированы. Данные fixture не параметризованы случайными значениями.

Для сравнения с реальным старым launch из 22 результатов:

```powershell
.\.venv\Scripts\python.exe ci/check_allure_metadata.py --baseline <копия-реальных-allure-results> --allow-web-replacement
```

Флаг явно разрешает ровно 8 новых UI identities, несовпадающих со старыми, и
обязательно сравнивает оба идентификатора остальных 14 тестов. Без этого флага
аудит требует совпадения всех 22 identities. После первого принятого нового
реального полного прогона использовать его baseline в обычном строгом режиме.
Нельзя собирать фиктивный launch из прежних API/Mobile и новых UI результатов.

История Automation Exercise сохраняется. Восьми новым сценариям соответствует
новая история; появление новых тестов/feature в графиках ожидаемо. allurerc.mjs,
history helper и постоянные snapshot-файлы менять или очищать не требуется.

## Публикация и ограничения

До публикации main сохраняет старый набор. Для main нужны только согласованные
файлы этой замены; посторонние staged-изменения и локальные artifacts не включать.
После отдельного разрешения на commit/push существующий Poll SCM должен запустить
Pipeline без изменения Job. Проверить SHA, SUCCESS/22 passed, JUnit/Allure,
реальную запись истории, API/Mobile IDs и закрытие восьми Web-сессий.

Локально подтверждены 8 passed headed и 8 passed headless с первой попытки.
Контекст Windows-службы агента после миграции ещё не проверен. Внешний сайт может
менять DOM, цены, доступность и политики; фиксированные проверки не ослабляются.
Pytest cache warning о WinError 183 наблюдался локально и не является падением
сценария. ACL и конфигурация Windows не изменялись.
