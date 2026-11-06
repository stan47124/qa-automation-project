# Проверенное окружение

Актуальный baseline — Jenkins №29, ревизия
`bdc9e97ceba5755d77a6f7c30f213517fe1083ca`: API 8, Web UI 8 и Mobile 6 passed.
Это описание проверенной Windows-конфигурации, а не гарантия совместимости
со всеми версиями. Новые установки и обновления при подготовке документации
не выполнялись.

## Версии и источники подтверждения

| Компонент | Подтверждённая версия | Основание |
| --- | --- | --- |
| Python | 3.14.3 | Заголовок Mobile pytest-console.log №29 |
| pytest | 9.2.0 | Тот же журнал; constraints |
| requests | 2.34.2 | requirements/constraints.txt |
| Selenium | 4.52.0 | requirements/constraints.txt |
| Selene | 2.0.0rc10 | requirements/constraints.txt |
| Appium Python Client | 6.0.12 | requirements/constraints.txt |
| allure-pytest | 2.16.2 | requirements/constraints.txt |
| Chrome | 156.0.8078.81 | Восемь Web UI lifecycle-вложений №29 |
| ChromeDriver | 156.0.8078.80 | Те же вложения |
| Node.js для Appium | 26.13.0 | adb-tools.log №29, node --version |
| Appium Server | 3.9.0 | adb-tools.log и appium.log №29 |
| UiAutomator2 | 8.7.3 | driver list и шесть созданных сессий №29 |
| Android Emulator | 37.2.13.0, build 16740729 | emulator.log №29 |
| Android system image | API 33, extension 5, Google Play, x86_64 | systemPath в emulator.log №29; source.properties образа |
| SDK platform-tools | 37.0.1 | source.properties установленного SDK на момент аудита; отдельного adb --version в №29 нет |
| Java | Temurin OpenJDK 25.0.5 | java -version в adb-tools.log №29 |
| Allure Report CLI | 3.16.0 | Установленный инструмент Jenkins и готовый отчёт №29 |
| Node.js для Allure | 24.14.1 | Отдельный runtime, явно выбранный launcher инструмента Jenkins |
| Allure Jenkins Plugin | 3.0.0 | Ранее проверенный JAR агента и совместимость configPath |

Python-пакеты закреплены в [constraints](../requirements/constraints.txt);
Pipeline устанавливает соответствующие профили и выполняет `pip check`.
Это не полный транзитивный lock-файл. Для Material Files подтверждены пакет
`me.zhanghai.android.files` и Activity `.filelist.FileListActivity`; точная версия
приложения в рассмотренных артефактах №29 не зафиксирована.

SDK не имеет одной общей версии: отдельно учитываются emulator, platform-tools
и system image. AVD называется `Pixel_4`, серийный номер — `emulator-5554`.
Node.js Appium и Node.js генератора Allure — разные runtime.

## Что требуется каждому набору

| Набор | Python-профиль | Дополнительные инструменты |
| --- | --- | --- |
| API | requirements/api.txt | Интернет и доступ к Swagger Petstore v3 |
| Web UI | requirements/ui.txt | Chrome; ChromeDriver через Selenium Manager, доступ к сайту и кэшу драйверов |
| Mobile | requirements/mobile.txt | Android SDK/platform-tools/emulator, подготовленный AVD и Material Files, Java, Node.js, Appium Server и UiAutomator2 |
| Все три | requirements.txt | Все перечисленные инструменты |
| Просмотр Allure | Python-адаптер создаёт results | Отдельно установленный Allure CLI; в Jenkins используется CLI 3.16.0 с Node.js 24.14.1 |

Команды установки Python-профилей и запуска: [README](../README.md#локальный-запуск).
Ручная подготовка Android: [local-setup.md](local-setup.md).
Не запускайте установку поверх работающего CI без согласованного обслуживания.
Каталоги SDK и Python выбираются для своей машины.
