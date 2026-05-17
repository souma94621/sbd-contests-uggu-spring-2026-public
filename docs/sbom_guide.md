# SBOM для ДВБ (SBOM_TCB) и некритичного кода (SBOM_OTHER)

## Когда читать

- **Обязательно:** нет.
- **Когда:** если нужно доработать SBOM, манифест и оценку по C06/C14/C23–C25.
- **Можно пропустить:** да, при первом проходе по `quickstart_2days.md`.

В сертификационном пакете АБУ Регулятор ожидает **два** файла CycloneDX 1.5:

| Файл в пакете | Смысл |
|---------------|--------|
| `sbom/SBOM_TCB.cdx.json` | Компоненты **доверенной вычислительной базы (ДВБ)** — код и библиотеки, компрометация которых **критична** для целей безопасности (SG) из SGA. |
| `sbom/SBOM_OTHER.cdx.json` | Остальные зависимости (например HTTP-стек), если вы **явно** выносите их из ДВБ и обосновываете в архитектуре. |

Без согласованного разделения вся поставка может считаться ДВБ при анализе рисков; разделение должно быть согласовано с **SGA**, тестами безопасности и фактическим кодом.

## Что делает Регулятор с SBOM

Из каждого JSON извлекаются:

- **N** — число элементов в `components`;
- **C** — число рёбер: сумма длин списков `dependsOn` в массиве `dependencies`.

Стоимость сертификации: полная полиномиальная оценка по **SBOM_TCB**, плюс вклад **SBOM_OTHER**, делённый на **100** (см. `SBOM_OTHER_COST_DIVISOR` в коде Регулятора), плюс **междоменные потоки** по полям manifest (ниже).

Если в **SBOM_TCB** или в основном **`source/requirements.txt`** поставки указаны «тяжёлые» зависимости ДВБ (например **numpy**), к сумме перед множителем применяется **умножение на 2**. Путь `requirements-other.txt` (если есть в поставке), устанавливаемый Регулятором **дополнительно** к основному `requirements.txt`, **не** участвует в этой проверке — туда переносят зависимости только для недоверенного кода (`abu/other`), чтобы не раздувать оценку ДВБ.

Подробнее о пакете: [certification_process.md](certification_process.md).

## Междоменные коммуникации (manifest)

В `manifest.json` архива (генерируется при сборке пакета, часть полей может подмешиваться из `sbom_manifest.json`, см. `scripts/write_cert_bundle_manifest.py`) могут быть целые неотрицательные поля:

- `domain_ipc_untrusted_boundary_edges` — учётные рёбра потоков на границе с **недоверенной** зоной;
- `domain_ipc_trusted_boundary_edges` — рёбра на границе **доверенных** доменов безопасности (входящие/исходящие потоки в контуре ДВБ).

Вклад в стоимость: линейный штраф по рёбрам; рёбра доверенной зоны учитываются **вдвое дороже** недоверенной (см. `estimate_domain_ipc_communication_cost` в `regulator/cost_model.py`).

## Разбиение ДВБ по доменам верификации и IPC-политики (manifest)

При необходимости участник может задать:

- `cost_domains_schema_version` — целое **`>= 1`** включает режим **суммы по объявленным доменам** безопасности над метриковым корнем **`abu/tcb`** (или всем `abu`, если деревьев `tcb/other` нет в поставке).
- `security_cost_domains` — объект списка доменов с полями `id` и массивом строковых `globs` относительно этого корня; каждый файл учитывается только у первого совпавшего домена, остальное — домен `_residual`. Схема JSON — [`docs/schemas/security_cost_domains.schema.json`](schemas/security_cost_domains.schema.json).
- `ipc_policies_bundle_path` — относительный путь к **`ipc_policies.json`** внутри пакета (по умолчанию участник может положить его рядом с политиками монитора как `source/abu/tcb/sys/ipc_policies.json`). Регулятор подсчитывает для каждого домена **`d`** число правил Белого Списка с **`from≠to`** и **`to=d`**, см. задачу; на это накладывается полиномиальное слагаемое к вкладу верификации. Схема — [`docs/schemas/ipc_policies.schema.json`](schemas/ipc_policies.schema.json). Каноническое текстовое описание — каталог **[`references/secure_ipc`](../references/secure_ipc/README.md)**.

Без указанной разумной связки ключей действует прежний режим: единое ведро метрик **`tcb_loc`/`tcb_cyclomatic_sum`** (как `compute_tcb_source_metrics`). Референсы по изоляции — [`references/isolation`](../references/isolation/README.md).

## Минимальный формат CycloneDX (прототип)

Обязательно для совместимости с парсером:

- `bomFormat`: `"CycloneDX"`, `specVersion`: `"1.5"`;
- `metadata.component` — корневой компонент BOM;
- у каждого элемента в `components` уникальный `bom-ref`;
- `dependencies`: для каждого `ref`, фигурирующего в графе, блок `{ "ref": "...", "dependsOn": [ ... ] }` (может быть пустым).

Имена пакетов в примерах: `pkg:pypi/<name>@<version>` для библиотек PyPI.

## Практические шаги для конкурсантов

1. Зафиксировать **цели безопасности** и границу ДВБ (см. [context.md](context.md), [tara_abu.md](tara_abu.md)).
2. Составить инвентаризацию: `requirements.txt` (в т.ч. опционально `requirements-other.txt` для кода `abu/other`), модули исходников, что исполняется в контуре критичных решений.
3. Решить, что попадает в **TCB** (SBOM_TCB), что остаётся в **OTHER** — и почему это не нарушает SG при модели угроз.
4. Отредактировать манифест [`sbom_manifest.json`](../src_starting_point/sbom/sbom_manifest.json) под вашу архитектуру (решение: свой каталог **`src_solution/sbom/sbom_manifest.json`**).
5. Сгенерировать CycloneDX: `pipenv run python scripts/generate_sbom_cdx.py` — по умолчанию записывает в [`src_starting_point/sbom/SBOM_TCB.cdx.json`](../src_starting_point/sbom/SBOM_TCB.cdx.json) и [`SBOM_OTHER.cdx.json`](../src_starting_point/sbom/SBOM_OTHER.cdx.json). Для решения укажите `--manifest`, `--out-tcb`, `--out-other` на файлы в `src_solution/sbom/` (как делает `prepare_certification_bundle_solution.sh`).
6. Проверить согласованность с реальной поставкой и при необходимости повторить сертификацию (`make prepare-cert-bundle`, `make certify-abu`).

**Важно:** манифест в репозитории — **модель заготовки**. Участники обязаны согласовать SBOM с фактическими зависимостями и архитектурой; иначе SBOM не будет отражать реальную поверхность атаки.

Для **оценки решения** (критерий **C14**) в каталоге решения используются два файла CycloneDX в `src_solution/sbom/` — декларация, в том числе положения **numpy** относительно ДВБ (см. [contest_regulations.md](contest_regulations.md)).

## Скрипт и примеры

- Манифест заготовки: [`src_starting_point/sbom/sbom_manifest.json`](../src_starting_point/sbom/sbom_manifest.json)
- Генератор: [../scripts/generate_sbom_cdx.py](../scripts/generate_sbom_cdx.py) (вызывается из [../scripts/prepare_certification_bundle.sh](../scripts/prepare_certification_bundle.sh) и [prepare_certification_bundle_solution.sh](../scripts/prepare_certification_bundle_solution.sh) перед сборкой архива)
- Файлы CycloneDX заготовки хранятся в [`src_starting_point/sbom/`](../src_starting_point/sbom/), а не в `docs/examples/`.

## Что читать дальше

- [certification_process.md](certification_process.md) — как SBOM попадает в пакет сертификации.
- [criteria_rubric.md](criteria_rubric.md) — как оцениваются C06, C14, C23–C25.
- [quickstart_2days.md](quickstart_2days.md) — чтобы продолжить практический маршрут.
