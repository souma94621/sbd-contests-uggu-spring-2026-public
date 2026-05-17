# Все команды Python — через Pipenv (pipenv run), без системного pip.
PIPENV ?= pipenv
RUN_ID ?= latest
SHARDS ?= 1
SHARD_INDEX ?= 0
JOBS ?= 2
ARTIFACTS_DIR ?= evaluation/report/runs/$(RUN_ID)
SHARD_PLAN ?= $(ARTIFACTS_DIR)/shard_plan.json
export PIPENV_VENV_IN_PROJECT=1

.PHONY: install tests-all tests-root tests-starting-point tests-solution tests-docker tests-full diagrams prepare-cert-bundle prepare-cert-bundle-solution certify-abu certify-abu-solution evaluate-score evaluate-participant-merge evaluate-all-participants evaluate-shard-plan evaluate-shard evaluate-distributed-aggregate evaluate-distributed-local docker-build docker-up docker-down

# Установка зависимостей из Pipfile (виртуальное окружение в .venv/)
install:
	$(PIPENV) install --dev

tests-all: tests-root tests-starting-point tests-solution	

tests-full: 
	make docker-up && SKIP_DOCKER_TESTS=0 make tests-all && make docker-down

tests-starting-point: install
	$(PIPENV) run pytest -q src_starting_point/tests

tests-root: install
	$(PIPENV) run pytest -q tests

tests-solution: install
	$(PIPENV) run pytest -q src_solution/tests

diagrams:
	JAVA_TOOL_OPTIONS=-Djava.awt.headless=true plantuml -tpng -o png docs/diagrams/context.puml docs/diagrams/sequence_mission.puml docs/diagrams/certification_pipeline.puml docs/diagrams/abu_v1_internal.puml docs/diagrams/tara_attack_numpy.puml docs/diagrams/tara_attack_api.puml docs/diagrams/tara_attack_pseudo_ai.puml docs/diagrams/tara_iso21434_overview.puml docs/diagrams/security_policies.puml src_solution/docs/diagrams/policy_architecture.puml src_solution/docs/diagrams/sequence_functional_domains.puml src_solution/docs/diagrams/system_ipc_components.puml

# Оценка текущего checkout (корень репозитория = CONTEST_REPO_ROOT по умолчанию).
evaluate-score: install
	$(PIPENV) run python scripts/evaluate_contest_score.py --with-certification

# Та же логика, что у жюри для evaluation/solution_<ID>: эталон из CONTEST_ORGANIZER_ROOT + только src_solution участника.
evaluate-participant-merge: install
	env -u CONTEST_REPO_ROOT CONTEST_ORGANIZER_ROOT=$(CURDIR) CONTEST_PARTICIPANT_SRC_SOLUTION=$(CURDIR)/src_solution $(PIPENV) run python scripts/evaluate_contest_score.py --with-certification

# Сводная оценка каталогов в evaluation/ → evaluation/report/summary.md (симлинк на дерево допустим).
evaluate-all-participants: install
	$(PIPENV) run python scripts/evaluate_all_participant_repos.py

# Сгенерировать JSON-файл распределения evaluation/solution_* по шардам.
evaluate-shard-plan: install
	$(PIPENV) run python scripts/evaluate_all_participant_repos.py --run-id $(RUN_ID) --shard-count $(SHARDS) --write-shard-plan $(SHARD_PLAN)

# Запустить один шард по заранее подготовленному SHARD_PLAN.
evaluate-shard: install
	$(PIPENV) run python scripts/evaluate_all_participant_repos.py --run-id $(RUN_ID) --artifacts-dir $(ARTIFACTS_DIR) --shard-plan $(SHARD_PLAN) --shard-index $(SHARD_INDEX) --jobs $(JOBS)

# Свести JSON-артефакты из ARTIFACTS_DIR в summary.md, summary.csv и summary.html.
evaluate-distributed-aggregate: install
	$(PIPENV) run python scripts/evaluate_all_participant_repos.py --aggregate $(ARTIFACTS_DIR)

# Локальная проверка распределённой оценки: план, все шарды и финальное сведение.
evaluate-distributed-local: evaluate-shard-plan
	for shard in $$(seq 0 $$(($(SHARDS) - 1))); do \
		$(PIPENV) run python scripts/evaluate_all_participant_repos.py --run-id $(RUN_ID) --artifacts-dir $(ARTIFACTS_DIR) --shard-plan $(SHARD_PLAN) --shard-index $$shard --jobs $(JOBS); \
	done
	$(PIPENV) run python scripts/evaluate_all_participant_repos.py --aggregate $(ARTIFACTS_DIR)

prepare-cert-bundle:
	bash scripts/prepare_certification_bundle.sh

prepare-cert-bundle-solution:
	bash scripts/prepare_certification_bundle_solution.sh

certify-abu: install prepare-cert-bundle
	$(PIPENV) run python scripts/run_certification.py

certify-abu-solution: install prepare-cert-bundle-solution
	$(PIPENV) run python scripts/run_certification.py

docker-build:
	bash scripts/docker_build.sh

docker-up:
	bash scripts/docker_up.sh

docker-down:
	bash scripts/docker_down.sh
