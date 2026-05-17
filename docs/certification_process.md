# Процесс сертификации АБУ (прототип, пример `src_starting_point`)

## Когда читать

- **Обязательно:** по необходимости.
- **Когда:** если возникают ошибки на шагах `make prepare-cert-bundle*` и `make certify-abu*`.
- **Можно пропустить:** да, для первого прохода достаточно `quickstart_2days.md`.

Итоговая оценка работы по критериям C01--C25 (сумма raw) описана в [contest_regulations.md](contest_regulations.md) и считается скриптом `scripts/evaluate_contest_score.py` (часть критериев — экспертно).

## Предусловия

- Python 3.12+ (см. `[requires]` в [Pipfile](../Pipfile)); для классического `python3 -m venv` при необходимости — пакет `python3-venv` в Debian/Ubuntu.
- Зависимости **только в виртуальном окружении Pipenv** (см. [quality_requirements.md](quality_requirements.md)): `./scripts/bootstrap_pipenv.sh` или `make install` (создаёт `.venv/` через Pipenv и ставит пакеты из Pipfile). Не выполняйте `pip install` в системный Python.
- Для диаграмм (опционально): PlantUML с `JAVA_TOOL_OPTIONS=-Djava.awt.headless=true` при отсутствии дисплея.

## Шаг 1. Подготовка сертификационного пакета

Перед копированием вызывается **генерация** SBOM из манифеста [`src_starting_point/sbom/sbom_manifest.json`](../src_starting_point/sbom/sbom_manifest.json) (см. [sbom_guide.md](sbom_guide.md)). Поля **междоменных потоков** (`domain_ipc_*_boundary_edges`), а также при необходимости **`cost_domains_schema_version`**, **`security_cost_domains`**, **`ipc_policies_bundle_path`**, если заданы в манифесте SBOM на корне, подмешиваются скриптом [`write_cert_bundle_manifest.py`](../scripts/write_cert_bundle_manifest.py) в итоговый `cert_bundle/manifest.json`. Целевые CycloneDX лежат в **`src_starting_point/sbom/`** и копируются в **`cert_bundle/sbom/`** вместе с агрегатом `abu_sbom.cdx.json` как `sbom.cdx.json`. Затем скрипт копирует дерево `src_starting_point` в **`cert_bundle/source/`** (в том числе те же файлы внутри `source/sbom/`), примеры **SGA** (`docs/examples/sga.json` → `cert_bundle/security/sga.json`), и формирует `manifest.json`, затем создаёт архив `artifacts/abu_certification_bundle.tar.gz`.

Для **решения** (`prepare_certification_bundle_solution.sh`): при наличии `src_solution/requirements-other.txt` он кладётся в поставку; Регулятор устанавливает его **после** основного `requirements.txt` без учёта «тяжёлых» пакетов из этого файла в проверке ДВБ. В эталонное дерево входит единый файл политик IPC в каталоге `src_solution/abu/tcb/sys/` (копируется вместе с `abu/tcb`); референсный формат и смысл — в **[`references/secure_ipc/README.md`](../references/secure_ipc/README.md)** и JSON-схемах в [`schemas/`](schemas/).

Типичный цикл участника: развивать код от **[`src_starting_point/`](../src_starting_point/)** по референсам **`references/`**, не копируя текст эталона; итог — решение в каталоге `src_solution/` в репозитории участника.

```bash
make prepare-cert-bundle
```

Или напрямую:

```bash
./scripts/prepare_certification_bundle.sh
```

## Шаг 2. Запуск Регулятора и подача заявки

### Вариант A: цель Makefile

```bash
make certify-abu
```

В стандартный вывод выводятся:

- **результат** — успешно / неуспешно;
- **стоимость** — `estimated_cost`;
- **сертификат** — `certificate_id` (SHA-256 архива пакета).

### Вариант B: полный набор тестов (pytest)

```bash
make tests-all
```

Включает интеграционный тест полного цикла сертификации для того же пакета.

### Вариант C: ручной HTTP (локально)

Поднимите Регулятор (`uvicorn regulator.main:app`) и выполните `POST /api/v1/certification/requests` с полями:

- `bundle_path` — абсолютный путь к `artifacts/abu_certification_bundle.tar.gz` **на машине, где работает процесс Регулятора**;
- `developer_company` (опционально) — название компании-разработчика;
- `firmware_label` (опционально) — метка прошивки; если пусто, подставляется `package_name` из `manifest.json` пакета.

### Вариант D: Docker и загрузка архива

1. Сборка и запуск: `make docker-build`, затем `make docker-up` (или `./scripts/docker_build.sh`, `./scripts/docker_up.sh`). Сервисы: Регулятор — порт **8082**, ЦР — **8080**, АБУ — **8081**.
2. Загрузка пакета телом запроса (без общего диска с хостом): `POST /api/v1/certification/upload` — `multipart/form-data` с полем файла `bundle` (`.tar.gz`) и при необходимости полями формы `developer_company`, `firmware_label`.
3. Сводная таблица успешных сертификаций: `GET /api/v1/certification/summary` (компания, прошивка, стоимость, покрытие, время).
4. Примеры запросов для расширения REST Client: корневой файл [requests.rest](../requests.rest).

Интеграционные тесты по HTTP к Регулятору в Docker: поднять контейнер Регулятора, затем `pytest tests/test_docker_integration.py` (или полный `make tests-all` — тесты пропускаются, если сервис недоступен). Явный пропуск: `SKIP_DOCKER_TESTS=1`. URL Регулятора: переменная `REGULATOR_URL` (по умолчанию `http://127.0.0.1:8082`).

## Шаг 3. Ввод в эксплуатацию

1. Сохраните `certificate_id` из ответа.
2. Зарегистрируйте АБУ в ЦР, передав `certificate_id`.
3. Для строгого режима установите `CR_CERT_POLICY=strict`.

## Пример ожидаемого вывода `make certify-abu`

```
Результат сертификации: успешно
Стоимость (усл. ед.): 12345.67
Сертификат (SHA-256 пакета): abcd1234...ef
```

Точные числа зависят от размера SBOM, **метрик исходников ДВБ** (`tcb_lines_of_code`, `tcb_cyclomatic_sum`) и результатов `pytest`. Сумму строк и цикломатику Регулятор считает по дереву **`abu/tcb`**, **если** одновременно присутствуют каталоги **`abu/tcb`** и **`abu/other`** иначе для целей сертификации весь код **`abu/**/*.py`** считается частью ДВБ (нет структурной изоляции «доверенное / недоверенное» в дереве). Эти величины входят в расчёт `estimated_cost`. В ответе API указываются **покрытие TOTAL** (`coverage_percent`), раздельно **`coverage_tcb_percent`** и **`coverage_other_percent`** при наличии **`abu/tcb`** и **`abu/other`**; если разделения нет, покрытие считается по всему `abu` и отражается в **`coverage_tcb_percent`**, **`coverage_other_percent`** = 100% (см. модуль `regulator.sandbox`). Отдельно — **покрытие тестами безопасности** (`security_coverage_percent`). Сертификат **не выдаётся**, если после успешного прогона тестов покрытие ДВБ (`coverage_tcb_percent`) ниже порога **40%** (переопределение: переменная окружения `REGULATOR_TCB_COV_REQUIRED`). SGA пакета доступен по `GET /api/v1/certificates/{certificate_id}/sga` после успешной выдачи сертификата.

Оценка решения по регламенту: `make evaluate-score` ([contest_regulations.md](contest_regulations.md), [templates/evaluation_report.md](templates/evaluation_report.md)).

## Что читать дальше

- [sbom_guide.md](sbom_guide.md) — если нужно уточнить разделение SBOM и влияние на стоимость.
- [contest_regulations.md](contest_regulations.md) — как результат сертификации влияет на баллы.
- [quickstart_2days.md](quickstart_2days.md) — чтобы вернуться к практическому маршруту.
