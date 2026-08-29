from __future__ import annotations

from pathlib import Path

import duckdb
from streamlit.testing.v1 import AppTest


def _create_empty_database(database: Path) -> None:
    connection = duckdb.connect(str(database))
    try:
        connection.execute(
            """
            CREATE TABLE fact_vendas (
                venda_id VARCHAR,
                data_venda TIMESTAMP,
                valor_venda DECIMAL(18,2),
                valor_referencia DECIMAL(18,2),
                desconto_percentual DECIMAL(9,4),
                marca VARCHAR,
                modelo VARCHAR,
                loja VARCHAR,
                uf VARCHAR,
                canal_origem VARCHAR,
                forma_pagamento VARCHAR,
                consultor VARCHAR,
                quality_issues VARCHAR,
                __source_file VARCHAR,
                __source_line BIGINT
            );
            CREATE TABLE quality_report (
                "check" VARCHAR,
                severity VARCHAR,
                failed_rows BIGINT,
                status VARCHAR
            );
            CREATE TABLE raw_vendas (venda_id VARCHAR);
            CREATE TABLE rejected_sales (venda_id VARCHAR);
            """
        )
    finally:
        connection.close()


def test_dashboard_handles_empty_fact_before_building_date_filter(
    tmp_path: Path, monkeypatch
) -> None:
    database = tmp_path / "empty.duckdb"
    _create_empty_database(database)
    monkeypatch.setenv("SALES_PIPELINE_DB_PATH", str(database))

    dashboard = Path(__file__).parents[1] / "dashboard.py"
    app = AppTest.from_file(str(dashboard), default_timeout=15).run()

    assert not app.exception
    assert [warning.value for warning in app.warning] == [
        "Nenhuma venda válida está disponível para exibição."
    ]
