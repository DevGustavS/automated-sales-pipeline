from __future__ import annotations

import hashlib
from decimal import Decimal
from pathlib import Path

import duckdb
import pandas as pd
import pytest

import build_pipeline
import pipeline


def _frame(schema: str, rows: list[dict[str, object]], source: str) -> pd.DataFrame:
    frame = pd.DataFrame(rows, columns=pipeline.EXPECTED_SCHEMAS[schema])
    frame["__source_file"] = source
    frame["__source_line"] = range(2, len(frame) + 2)
    return frame


def _raw_frames(
    sales: list[dict[str, object]],
    *,
    consultants: list[dict[str, object]] | None = None,
    stores: list[dict[str, object]] | None = None,
    vehicles: list[dict[str, object]] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    consultants = consultants or [
        {
            "consultor_id": "C1",
            "consultor": "Ana",
            "loja_id": "L1",
            "equipe": "A",
            "data_admissao": "2020-01-01",
        },
        {
            "consultor_id": "C2",
            "consultor": "Bruno",
            "loja_id": "L2",
            "equipe": "B",
            "data_admissao": "2021-02-02",
        },
    ]
    stores = stores or [
        {
            "loja_id": "L1",
            "loja": "Centro",
            "cidade": "Manaus",
            "uf": "AM",
            "cluster": "A",
        },
        {
            "loja_id": "L2",
            "loja": "Norte",
            "cidade": "Manaus",
            "uf": "AM",
            "cluster": "B",
        },
    ]
    vehicles = vehicles or [
        {
            "veiculo_id": vehicle_id,
            "ano_modelo": "2024",
            "marca": "Marca",
            "modelo": f"Modelo {vehicle_id}",
            "versao": "Base",
            "carroceria": "SUV",
            "cambio": "Auto",
            "combustivel": "Flex",
            "tipo_veiculo": "Novo",
            "quilometragem": "0",
            "cor_externa": "Preto",
            "cor_interna": "Preto",
            "score_avaliacao": "9.5",
        }
        for vehicle_id in ("V1", "V2", "V3", "V4")
    ]
    return (
        _frame("vendas", sales, "vendas_2025.csv"),
        _frame("consultores", consultants, "dim_consultores.csv"),
        _frame("lojas", stores, "dim_lojas.csv"),
        _frame("veiculos", vehicles, "dim_veiculos.csv"),
    )


def _sale(
    venda_id: str,
    *,
    date: str = "2025-01-15",
    vehicle_id: str = "V1",
    store_id: str = "L1",
    consultant_id: str = "C1",
    reference: str = "100.00",
    amount: str = "90.00",
) -> dict[str, object]:
    return {
        "venda_id": venda_id,
        "data_venda": date,
        "veiculo_id": vehicle_id,
        "loja_id": store_id,
        "consultor_id": consultant_id,
        "canal_origem": "Loja",
        "forma_pagamento": "À vista",
        "valor_referencia": reference,
        "valor_venda": amount,
    }


def _normalize_and_validate(
    sales: list[dict[str, object]],
    **dimensions: list[dict[str, object]],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    normalized = build_pipeline.normalize(*_raw_frames(sales, **dimensions))
    return build_pipeline.validate(*normalized)


def _report_count(report: pd.DataFrame, check: str) -> int:
    return int(report.loc[report["check"].eq(check), "failed_rows"].iloc[0])


def test_quality_catalog_is_complete_unique_and_exposed_in_report() -> None:
    required_fields = {
        "rule_id",
        "description",
        "severity",
        "dataset",
        "condition",
        "treatment",
        "reason",
        "invalidates_sale",
    }
    rule_ids = [rule["rule_id"] for rule in build_pipeline.QUALITY_RULES]

    assert len(rule_ids) == len(set(rule_ids)) == 18
    assert all(required_fields <= rule.keys() for rule in build_pipeline.QUALITY_RULES)
    assert {rule["severity"] for rule in build_pipeline.QUALITY_RULES} == {
        "error",
        "warning",
    }

    _, _, report = _normalize_and_validate([_sale("S1")])
    assert set(report["rule_id"]) == set(rule_ids)
    assert report["check"].equals(report["rule_id"])
    for rule in build_pipeline.QUALITY_RULES:
        row = report.loc[report["rule_id"].eq(rule["rule_id"])].iloc[0]
        for field in required_fields - {"rule_id"}:
            assert row[field] == rule[field]


def test_date_parser_accepts_known_formats_and_rejects_invalid_dates() -> None:
    parsed = build_pipeline.parse_date(
        pd.Series(["2025-01-31", "2025/01/31", "31/01/2025", "2025-02-30"])
    )

    assert parsed.notna().tolist() == [True, True, True, False]
    assert parsed.iloc[:3].tolist() == [pd.Timestamp("2025-01-31")] * 3


def test_money_parser_and_calculations_preserve_cents_exactly() -> None:
    fact, rejected, _ = _normalize_and_validate(
        [
            _sale("S1", reference="R$ 100,10", amount="90,05"),
            _sale("S2", vehicle_id="V2", reference="200.20", amount="150.15"),
        ]
    )

    assert rejected.empty
    assert fact["valor_venda"].tolist() == [Decimal("90.05"), Decimal("150.15")]
    assert fact["desconto_valor"].tolist() == [Decimal("10.05"), Decimal("50.05")]
    assert fact["valor_venda"].sum() == Decimal("240.20")
    assert fact["valor_venda"].sum() / Decimal(len(fact)) == Decimal("120.10")


def test_money_parser_rejects_non_cent_precision() -> None:
    parsed = build_pipeline.parse_money(pd.Series(["10", "10,50", "10.555", "x"]))

    assert parsed.iloc[:2].tolist() == [Decimal("10.00"), Decimal("10.50")]
    assert parsed.iloc[2:].isna().tolist() == [True, True]


def test_duplicate_sale_is_rejected_and_reused_vehicle_is_a_warning() -> None:
    fact, rejected, report = _normalize_and_validate([_sale("S1"), _sale("S1")])

    assert fact["venda_id"].tolist() == ["S1"]
    assert rejected["venda_id"].tolist() == ["S1"]
    assert _report_count(report, "duplicate_venda_id") == 1
    assert _report_count(report, "veiculo_multiple_sales") == 2
    assert "veiculo_multiple_sales" in fact.iloc[0]["quality_issues"]
    assert "duplicate_venda_id" in rejected.iloc[0]["quality_issues"]


def test_duplicate_dimension_is_reported_and_first_record_is_used() -> None:
    stores = [
        {
            "loja_id": "L1",
            "loja": "Primeira",
            "cidade": "Manaus",
            "uf": "AM",
            "cluster": "A",
        },
        {
            "loja_id": "L1",
            "loja": "Segunda",
            "cidade": "Manaus",
            "uf": "AM",
            "cluster": "B",
        },
    ]

    fact, rejected, report = _normalize_and_validate([_sale("S1")], stores=stores)

    assert rejected.empty
    assert fact.iloc[0]["loja"] == "Primeira"
    assert _report_count(report, "duplicate_loja_id") == 2


def test_reference_errors_reject_and_consultant_warnings_do_not() -> None:
    fact, rejected, report = _normalize_and_validate(
        [
            _sale("S1", consultant_id="C404"),
            _sale("S2", vehicle_id="V404"),
            _sale("S3", vehicle_id="V2", store_id="L404"),
            _sale("S4", vehicle_id="V3", store_id="L1", consultant_id="C2"),
        ]
    )

    assert set(fact["venda_id"]) == {"S1", "S4"}
    assert set(rejected["venda_id"]) == {"S2", "S3"}
    assert _report_count(report, "orphan_consultor_id") == 1
    assert _report_count(report, "orphan_veiculo_id") == 1
    assert _report_count(report, "orphan_loja_id") == 1
    assert _report_count(report, "consultor_loja_mismatch") == 2


def _write_input_directory(input_dir: Path) -> None:
    sales, consultants, stores, vehicles = _raw_frames(
        [_sale("S1"), _sale("S2", vehicle_id="V2", amount="80.50")]
    )
    input_dir.mkdir()
    for name, frame in {
        "vendas_2025.csv": sales,
        "dim_consultores.csv": consultants,
        "dim_lojas.csv": stores,
        "dim_veiculos.csv": vehicles,
    }.items():
        frame.drop(columns=list(pipeline.TRACE_COLUMNS)).to_csv(
            input_dir / name, index=False, encoding="utf-8", sep=";"
        )


def _logical_output(output_dir: Path, quarantine_dir: Path) -> tuple[object, ...]:
    connection = duckdb.connect(
        str(output_dir / "sales_pipeline.duckdb"), read_only=True
    )
    try:
        counts = connection.execute(
            """
            SELECT
                (SELECT COUNT(*) FROM raw_vendas),
                (SELECT COUNT(*) FROM fact_vendas),
                (SELECT COUNT(*) FROM rejected_sales),
                (SELECT SUM(valor_venda) FROM fact_vendas)
            """
        ).fetchone()
    finally:
        connection.close()

    generated_files = (
        output_dir / "fact_sales_pipeline.parquet",
        output_dir / "quality_report.csv",
        quarantine_dir / "rejected_sales.csv",
    )
    file_hashes = tuple(
        hashlib.sha256(path.read_bytes()).hexdigest() for path in generated_files
    )
    return *counts, *file_hashes


def test_pipeline_reexecution_is_logically_idempotent(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    quarantine_dir = tmp_path / "quarantine"
    _write_input_directory(input_dir)

    first_result = build_pipeline.run(input_dir, output_dir, quarantine_dir)
    first_output = _logical_output(output_dir, quarantine_dir)
    second_result = build_pipeline.run(input_dir, output_dir, quarantine_dir)
    second_output = _logical_output(output_dir, quarantine_dir)

    assert first_result["sales_received"] == second_result["sales_received"] == 2
    assert first_result["valid_sales"] == second_result["valid_sales"] == 2
    assert first_output == second_output
    assert first_result["quarantine"] == str(quarantine_dir.resolve())
    assert (quarantine_dir / "rejected_sales.csv").exists()
    assert not (output_dir / "rejected_sales.csv").exists()

    connection = duckdb.connect(
        str(output_dir / "sales_pipeline.duckdb"), read_only=True
    )
    try:
        fact_types = dict(
            connection.execute(
                "SELECT column_name, column_type FROM (DESCRIBE fact_vendas)"
            ).fetchall()
        )
        mart_types = dict(
            connection.execute(
                "SELECT column_name, column_type FROM (DESCRIBE mart_vendas_mensal)"
            ).fetchall()
        )
        parquet_types = dict(
            connection.execute(
                """
                SELECT column_name, column_type
                FROM (DESCRIBE SELECT * FROM read_parquet(?))
                """,
                [str(output_dir / "fact_sales_pipeline.parquet")],
            ).fetchall()
        )
        revenue = connection.execute(
            "SELECT SUM(valor_venda) FROM fact_vendas"
        ).fetchone()[0]
    finally:
        connection.close()

    assert fact_types["valor_venda"] == "DECIMAL(18,2)"
    assert fact_types["desconto_valor"] == "DECIMAL(18,2)"
    assert mart_types["receita"] == "DECIMAL(18,2)"
    assert mart_types["ticket_medio"] == "DECIMAL(18,2)"
    assert parquet_types["valor_venda"] == "DECIMAL(18,2)"
    assert revenue == Decimal("170.50")


def test_output_publication_rolls_back_all_files_on_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output_dir = tmp_path / "output"
    quarantine_dir = tmp_path / "quarantine"
    output_dir.mkdir()
    quarantine_dir.mkdir()
    original_files = {
        output_dir / "quality_report.csv": b"old quality",
        output_dir / "sales_pipeline.duckdb": b"old database",
        output_dir / "fact_sales_pipeline.parquet": b"old parquet",
        quarantine_dir / "rejected_sales.csv": b"old rejected",
    }
    for path, content in original_files.items():
        path.write_bytes(content)

    raw_frames = _raw_frames([_sale("S1")])
    normalized = build_pipeline.normalize(*raw_frames)
    fact, rejected, report = build_pipeline.validate(*normalized)
    real_replace = build_pipeline.os.replace
    injected_failure = False

    def fail_during_publication(source: Path, target: Path) -> None:
        nonlocal injected_failure
        if not injected_failure and Path(target).name == "fact_sales_pipeline.parquet":
            injected_failure = True
            raise OSError("injected publication failure")
        real_replace(source, target)

    monkeypatch.setattr(build_pipeline.os, "replace", fail_during_publication)

    with pytest.raises(OSError, match="injected publication failure"):
        build_pipeline.save(
            output_dir,
            quarantine_dir,
            raw_frames[0],
            fact,
            rejected,
            report,
            normalized[1],
            normalized[2],
            normalized[3],
        )

    assert {path: path.read_bytes() for path in original_files} == original_files
    assert not list(output_dir.glob(".*.bak"))
    assert not list(quarantine_dir.glob(".*.bak"))
