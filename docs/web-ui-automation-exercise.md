# Возвращение Automation Exercise

Восемь активных Web UI-сценариев восстановлены из
`723f6df1b9cccfc92341c325712971ba6f18dfe9` (Jenkins #22).
Тела тестов, assertions, локаторы и `Storefront` сохранены.
ChromeOptions и таймауты остались прежними: 1440×1000,
`--disable-notifications`, `--headless=new` при HEADLESS=true,
page load 45 s и Selene 15 s. Новая сессия и временный профиль на каждый тест.

Текущий fixture сохраняет безопасную диагностику и lifecycle из современной
инфраструктуры. Автоматические HTML/скриншоты Selene отключены. При отказе
сохраняется JSON с разрешёнными URL/title и признаками проверки. Скриншоты
ограничены контейнером каталога, товара или корзины; Contact Us, password,
CAPTCHA и challenge исключены. Форма Contact Us не отправляется.

Набор: главная, Products, поиск, данные товара, добавление в корзину,
содержимое корзины, выбранное количество, TXT upload без отправки.
Неактивные SauceDemo Page Objects и их unit-проверки оставлены для сохранения
изолированных вспомогательных компонентов. Четыре модуля функциональных
SauceDemo-тестов убраны из collection. Предыдущая миграция описана в
[исторической инструкции](web-ui-saucedemo.md).

## Allure

- epic: `QA.Guru graduation project`;
- feature: `Web UI: Automation Exercise`;
- parentSuite: `Web UI`, suite: `Automation Exercise`;
- story: прежние сценарии Home page / Products navigation / Product search /
  Product details / Add to cart / Cart contents / Select product quantity /
  Attach TXT without submission;
- Web UI severity: 4 critical, 3 normal, 1 minor;
- весь проект: 12 critical, 9 normal, 1 minor.

SD-UI labels относятся к SauceDemo и в восстановленный набор не переносятся.
Прежние полные имена Automation Exercise восстанавливают их testCaseId/historyId.
Идентификаторы 14 API/Mobile-тестов должны совпадать с состоянием до замены.
История не переписывается: исторические SauceDemo-запуски остаются историческими.
Allure configuration и механизм постоянного хранения не меняются.

## WebDriver Monitor

В обычной локальной команде plugin не загружается автоматически.
В Web UI-стадии Jenkins изменена только одна строка:

```diff
- "QA_WEBDRIVER_DIAGNOSTICS=${env.REPORT_ROOT}/webdriver-diagnostics",
+ 'QA_WEBDRIVER_DIAGNOSTICS=',
```

Существующий `-p ci.diagnostics.webdriver_monitor` сохраняется, но пустое значение
не создаёт Monitor и не оборачивает WebDriver. Диагностические файлы не удаляются.
Это существующий механизм отключения, проверяемый unit-тестом для пустой строки.
Расписание Poll SCM, Credentials, stages и команды runner не меняются.

## Локальная проверка

Использовать существующую `.venv`, новые каталоги результатов и basetemp внутри
artifacts. `HEADLESS=true` задаётся только окружению процесса. Проверка:
collection всех tests (22), `ci/check_allure_metadata.py`, инфраструктурные
`ci/tests`, один `pytest tests/ui -v` с отдельными JUnit/Allure.
Повторных прогонов ради успеха и обхода антибот-защиты нет.

Локальный успех не является новым Jenkins SUCCESS. До публикации нужен обзор
изменений и отдельное согласование commit/push; Job вручную не запускается.
Доступность внешнего сайта может измениться, как уже происходило после #22.
