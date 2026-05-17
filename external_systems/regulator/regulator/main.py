"""REST API Регулятора (сертификация пакетов АБУ)."""

from __future__ import annotations

import json
import os
import shutil
import tarfile
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from regulator.cost_model import (
    apply_heavy_dep_multiplier,
    tcb_partition_verification_addon,
    total_estimated_cost,
)
from regulator.ipc_policy_parse import count_incoming_cross_domain_ipc_allows, load_ipc_policies
from regulator.hash_util import sha256_file
from regulator.sandbox import run_pytest_with_coverage, run_security_tests_coverage
from regulator.sbom_parse import count_sbom_metrics
from regulator.sga_validate import load_sga, sga_document_for_response

app = FastAPI(title="Регулятор (прототип)", version="0.1.0")

# Память: сертификат -> метаданные
_certificates: dict[str, dict] = {}
_jobs: dict[str, dict] = {}


class CertificationRequestIn(BaseModel):
    """Заявка на сертификацию."""

    bundle_path: str = Field(description="Абсолютный путь к abu_certification_bundle.tar.gz")
    developer_company: str = Field(
        default="",
        description="Название компании-разработчика",
    )
    firmware_label: str = Field(
        default="",
        description="Метка или название прошивки (если пусто — из manifest.json пакета)",
    )


class CertificationResultOut(BaseModel):
    """Результат обработки заявки."""

    success: bool
    estimated_cost: float
    certificate_id: str | None = Field(
        default=None,
        description="SHA-256 архива при успехе",
    )
    coverage_percent: float = Field(
        default=0.0,
        description="Суммарное покрытие по всем измеренным модулям (TOTAL в отчёте coverage)",
    )
    coverage_tcb_percent: float = Field(
        default=0.0,
        description="Покрытие строк в abu/tcb (ДВБ)",
    )
    coverage_other_percent: float = Field(
        default=0.0,
        description="Покрытие строк в abu/other (недоверенный код)",
    )
    security_coverage_percent: float = 0.0
    message: str = ""
    developer_company: str = ""
    firmware_label: str = ""
    tcb_lines_of_code: int = Field(
        default=0,
        description=(
            "Число строк *.py учтённое в стоимости как ДВБ: весь абу при отсутствии парных "
            "каталогов abu/tcb и abu/other; только abu/tcb при их наличии (см. compute_tcb_source_metrics)."
        ),
    )
    tcb_cyclomatic_sum: int = Field(
        default=0,
        description=(
            "Сумма цикломатических сложностей функций/методов по правилам "
            "`compute_tcb_source_metrics` (тот же объём кода, что и `tcb_lines_of_code`)."
        ),
    )
    domain_verification_breakdown: list[dict] | None = Field(
        default=None,
        description=(
            "Если объявлено разбиение `security_cost_domains` в manifest, вклад каждого домена "
            "и счётчик входящих ipc-политик (from≠to)."
        ),
    )


class CertificationSummaryRow(BaseModel):
    """Строка сводной таблицы сертифицированных прошивок."""

    certificate_id: str
    developer_company: str
    firmware_label: str
    estimated_cost: float
    coverage_percent: float
    certified_at: str


class SgaOut(BaseModel):
    """SGA (security goals and assumptions) по сертификату."""

    certificate_id: str
    security_goals: list
    security_assumptions: list


def _repo_root() -> Path:
    """Корень репозитория (для тестов)."""
    return Path(__file__).resolve().parents[3]


def process_certification(
    bundle_path: Path,
    *,
    developer_company: str = "",
    firmware_label: str = "",
) -> CertificationResultOut:
    """
    Полный цикл: хэш, SGA, SBOM_TCB/SBOM_OTHER, стоимость (SBOM + LOC/цикломатика abu), песочница pytest + security.

    :param bundle_path: путь к .tar.gz
    """
    if not bundle_path.is_file():
        return CertificationResultOut(
            success=False,
            estimated_cost=0.0,
            message="файл пакета не найден",
            developer_company=developer_company,
            firmware_label=firmware_label,
        )

    cert_hash = sha256_file(bundle_path)
    tmp = Path(tempfile.mkdtemp(prefix="cert_extract_"))
    try:
        with tarfile.open(bundle_path, "r:gz") as tf:
            tf.extractall(tmp)

        bundle_root = tmp / "cert_bundle"
        sga_path = bundle_root / "security" / "sga.json"
        sbom_tcb = bundle_root / "sbom" / "SBOM_TCB.cdx.json"
        sbom_other = bundle_root / "sbom" / "SBOM_OTHER.cdx.json"
        manifest_path = bundle_root / "manifest.json"
        source_dir = bundle_root / "source"

        ok_sga, sga_data, sga_msg = load_sga(sga_path)
        if not ok_sga or sga_data is None:
            return CertificationResultOut(
                success=False,
                estimated_cost=0.0,
                message=sga_msg,
                developer_company=developer_company,
                firmware_label=firmware_label,
            )

        if not sbom_tcb.is_file() or not sbom_other.is_file():
            return CertificationResultOut(
                success=False,
                estimated_cost=0.0,
                message="в пакете должны быть sbom/SBOM_TCB.cdx.json и sbom/SBOM_OTHER.cdx.json",
                developer_company=developer_company,
                firmware_label=firmware_label,
            )

        manifest: dict = {}
        if manifest_path.is_file():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        ipc_ut = max(0, int(manifest.get("domain_ipc_untrusted_boundary_edges", 0)))
        ipc_td = max(0, int(manifest.get("domain_ipc_trusted_boundary_edges", 0)))

        n_tcb, e_tcb = count_sbom_metrics(sbom_tcb)
        n_other, e_other = count_sbom_metrics(sbom_other)
        tcb_loc, tcb_cc = 0, 0
        domain_verification_breakdown: list[dict] | None = None
        addon_override: float | None = None

        if source_dir.is_dir():
            abu_pkg = source_dir / "abu"
            if abu_pkg.is_dir():
                from regulator.tcb_metrics import (
                    abu_has_security_domain_split,
                    compute_tcb_source_metrics,
                    partition_tcb_into_domains,
                )

                tcb_loc, tcb_cc = compute_tcb_source_metrics(abu_pkg)

                sd_spec = manifest.get("security_cost_domains")
                ver_raw = manifest.get("cost_domains_schema_version")
                try:
                    ver_num = int(ver_raw)
                except (TypeError, ValueError):
                    ver_num = 0

                use_partition = bool(
                    isinstance(sd_spec, dict) and sd_spec.get("domains") and ver_num >= 1
                )
                if use_partition:
                    metrics_root = abu_pkg / "tcb" if abu_has_security_domain_split(abu_pkg) else abu_pkg
                    dom_rows, _part_warn = partition_tcb_into_domains(metrics_root, sd_spec)
                    ipc_rel = str(
                        manifest.get("ipc_policies_bundle_path") or "source/abu/tcb/sys/ipc_policies.json"
                    )
                    ipc_abs = bundle_root / ipc_rel.replace("\\", "/")
                    pol_doc = load_ipc_policies(ipc_abs)
                    pcounts = count_incoming_cross_domain_ipc_allows(pol_doc)
                    addon_override, domain_verification_breakdown = (
                        tcb_partition_verification_addon(dom_rows, pcounts)
                    )

        cost = total_estimated_cost(
            n_tcb,
            e_tcb,
            n_other,
            e_other,
            tcb_loc=tcb_loc,
            tcb_cyclomatic_sum=tcb_cc,
            ipc_untrusted_boundary_edges=ipc_ut,
            ipc_trusted_boundary_edges=ipc_td,
            tcb_source_verification_addon=addon_override,
        )
        req_path = source_dir / "requirements.txt"
        cost = apply_heavy_dep_multiplier(cost, sbom_tcb, req_path)

        if not source_dir.is_dir():
            return CertificationResultOut(
                success=False,
                estimated_cost=cost,
                message="в пакете нет source/",
                developer_company=developer_company,
                firmware_label=firmware_label,
                tcb_lines_of_code=tcb_loc,
                tcb_cyclomatic_sum=tcb_cc,
                domain_verification_breakdown=domain_verification_breakdown,
            )

        fw_label = firmware_label.strip() or str(manifest.get("package_name", ""))
        tests_root = str(manifest.get("tests_root", "tests"))

        ignore_sec: list[str] = []
        tr_norm = tests_root.replace("\\", "/").strip("/")
        if tr_norm and (source_dir / tr_norm / "security").is_dir():
            ignore_sec.append(f"--ignore={tr_norm}/security")

        cov_main = run_pytest_with_coverage(
            source_dir,
            tests_subdir=tests_root,
            cov_fail_under=None,
            extra_pytest_args=ignore_sec or None,
        )

        if not cov_main.ok:
            return CertificationResultOut(
                success=False,
                estimated_cost=cost,
                certificate_id=None,
                coverage_percent=cov_main.coverage_total,
                coverage_tcb_percent=cov_main.coverage_tcb,
                coverage_other_percent=cov_main.coverage_other,
                message=(
                    cov_main.log[-2000:] if cov_main.log else "pytest failed"
                ),
                developer_company=developer_company,
                firmware_label=fw_label,
                tcb_lines_of_code=tcb_loc,
                tcb_cyclomatic_sum=tcb_cc,
                domain_verification_breakdown=domain_verification_breakdown,
            )

        tcb_need = float(os.environ.get("REGULATOR_TCB_COV_REQUIRED", "40"))
        if cov_main.coverage_tcb < tcb_need - 1e-9:
            return CertificationResultOut(
                success=False,
                estimated_cost=cost,
                certificate_id=None,
                coverage_percent=cov_main.coverage_total,
                coverage_tcb_percent=cov_main.coverage_tcb,
                coverage_other_percent=cov_main.coverage_other,
                message=(
                    f"покрытие ДВБ (abu.tcb) {cov_main.coverage_tcb:.2f}% "
                    f"ниже требуемого {tcb_need:g}% "
                    f"(переменная REGULATOR_TCB_COV_REQUIRED)"
                ),
                developer_company=developer_company,
                firmware_label=fw_label,
                tcb_lines_of_code=tcb_loc,
                tcb_cyclomatic_sum=tcb_cc,
                domain_verification_breakdown=domain_verification_breakdown,
            )

        sec_res = run_security_tests_coverage(source_dir)
        if not sec_res.ok:
            return CertificationResultOut(
                success=False,
                estimated_cost=cost,
                certificate_id=None,
                coverage_percent=cov_main.coverage_total,
                coverage_tcb_percent=cov_main.coverage_tcb,
                coverage_other_percent=cov_main.coverage_other,
                security_coverage_percent=sec_res.coverage_total,
                message=(
                    sec_res.log[-1500:] if sec_res.log else "security pytest failed"
                ),
                developer_company=developer_company,
                firmware_label=fw_label,
                tcb_lines_of_code=tcb_loc,
                tcb_cyclomatic_sum=tcb_cc,
                domain_verification_breakdown=domain_verification_breakdown,
            )

        certified_at = datetime.now(timezone.utc).isoformat()
        sga_snapshot = sga_document_for_response(sga_data)
        _certificates[cert_hash] = {
            "valid": True,
            "estimated_cost": cost,
            "coverage_percent": cov_main.coverage_total,
            "coverage_tcb_percent": cov_main.coverage_tcb,
            "coverage_other_percent": cov_main.coverage_other,
            "security_coverage_percent": sec_res.coverage_total,
            "developer_company": developer_company.strip(),
            "firmware_label": fw_label,
            "certified_at": certified_at,
            "sga": sga_snapshot,
            "tcb_lines_of_code": tcb_loc,
            "tcb_cyclomatic_sum": tcb_cc,
            "domain_verification_breakdown": domain_verification_breakdown,
        }
        return CertificationResultOut(
            success=True,
            estimated_cost=cost,
            certificate_id=cert_hash,
            coverage_percent=cov_main.coverage_total,
            coverage_tcb_percent=cov_main.coverage_tcb,
            coverage_other_percent=cov_main.coverage_other,
            security_coverage_percent=sec_res.coverage_total,
            message="ok",
            developer_company=developer_company.strip(),
            firmware_label=fw_label,
            tcb_lines_of_code=tcb_loc,
            tcb_cyclomatic_sum=tcb_cc,
            domain_verification_breakdown=domain_verification_breakdown,
        )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


@app.get("/api/v1/health")
def health() -> dict[str, str]:
    """Проверка работоспособности."""
    return {"status": "ok", "service": "regulator"}


@app.post("/api/v1/certification/requests", response_model=CertificationResultOut)
def submit_certification(body: CertificationRequestIn) -> CertificationResultOut:
    """Принять заявку и выполнить сертификацию (синхронно), путь к архиву на диске сервера."""
    try:
        path = Path(body.bundle_path).resolve()
        return process_certification(
            path,
            developer_company=body.developer_company,
            firmware_label=body.firmware_label,
        )
    except OSError as exc:
        return CertificationResultOut(
            success=False,
            estimated_cost=0.0,
            message=str(exc),
            developer_company=body.developer_company,
            firmware_label=body.firmware_label,
        )


@app.post("/api/v1/certification/upload", response_model=CertificationResultOut)
async def upload_certification(
    bundle: UploadFile = File(..., description="Архив abu_certification_bundle.tar.gz"),
    developer_company: str = Form("", description="Название компании-разработчика"),
    firmware_label: str = Form("", description="Метка прошивки"),
) -> CertificationResultOut:
    """Загрузить сертификационный пакет телом запроса и вернуть результат сертификации."""
    data = await bundle.read()
    if not data:
        raise HTTPException(status_code=400, detail="пустой файл")
    if not data.startswith(b"\x1f\x8b"):
        raise HTTPException(
            status_code=400,
            detail="ожидается gzip-сжатый архив (.tar.gz)",
        )

    tmp_dir = Path(tempfile.mkdtemp(prefix="upload_bundle_"))
    tmp_path = tmp_dir / "abu_certification_bundle.tar.gz"
    try:
        tmp_path.write_bytes(data)
        return process_certification(
            tmp_path,
            developer_company=developer_company,
            firmware_label=firmware_label,
        )
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@app.get("/api/v1/certification/summary", response_model=list[CertificationSummaryRow])
def certification_summary() -> list[CertificationSummaryRow]:
    """Сводная таблица сертифицированных прошивок, разработчиков и стоимости."""
    rows: list[CertificationSummaryRow] = []
    for cert_id, row in _certificates.items():
        if not row.get("valid"):
            continue
        rows.append(
            CertificationSummaryRow(
                certificate_id=cert_id,
                developer_company=str(row.get("developer_company", "")),
                firmware_label=str(row.get("firmware_label", "")),
                estimated_cost=float(row.get("estimated_cost", 0.0)),
                coverage_percent=float(row.get("coverage_percent", 0.0)),
                certified_at=str(row.get("certified_at", "")),
            )
        )
    return rows


@app.get("/api/v1/certificates/{certificate_id}/sga", response_model=SgaOut)
def get_sga(certificate_id: str) -> SgaOut:
    """Выдача SGA (целей и предположений безопасности) по сертификату."""
    row = _certificates.get(certificate_id)
    if not row or not row.get("valid"):
        raise HTTPException(status_code=404, detail="сертификат не найден")
    sga = row.get("sga") or {}
    return SgaOut(
        certificate_id=certificate_id,
        security_goals=list(sga.get("security_goals", [])),
        security_assumptions=list(sga.get("security_assumptions", [])),
    )


@app.get("/api/v1/certificates/{certificate_id}")
def get_certificate(certificate_id: str) -> dict:
    """Проверка действительности сертификата (хэш пакета)."""
    if certificate_id in _certificates:
        row = _certificates[certificate_id]
        return {
            "valid": True,
            "certificate_id": certificate_id,
            "estimated_cost": row.get("estimated_cost"),
            "developer_company": row.get("developer_company"),
            "firmware_label": row.get("firmware_label"),
            "coverage_percent": row.get("coverage_percent"),
            "coverage_tcb_percent": row.get("coverage_tcb_percent"),
            "coverage_other_percent": row.get("coverage_other_percent"),
            "security_coverage_percent": row.get("security_coverage_percent"),
            "has_sga": bool(row.get("sga")),
            "tcb_lines_of_code": row.get("tcb_lines_of_code"),
            "tcb_cyclomatic_sum": row.get("tcb_cyclomatic_sum"),
            "domain_verification_breakdown": row.get("domain_verification_breakdown"),
        }
    return {"valid": False, "certificate_id": certificate_id}


@app.post("/api/v1/certification/requests/async", response_model=dict)
def submit_async(body: CertificationRequestIn) -> dict:
    """Заглушка асинхронной заявки: возвращает job_id (тот же синхронный путь в прототипе)."""
    jid = str(uuid.uuid4())
    path = Path(body.bundle_path).resolve()
    result = process_certification(
        path,
        developer_company=body.developer_company,
        firmware_label=body.firmware_label,
    )
    _jobs[jid] = result.model_dump()
    return {"job_id": jid, "result": result.model_dump()}
