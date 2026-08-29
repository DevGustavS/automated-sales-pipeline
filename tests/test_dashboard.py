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
                desconto_valor DECIMAL(18,2),
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


def _create_analytical_database(database: Path) -> None:
    _create_empty_database(database)
    connection = duckdb.connect(str(database))
    try:
        connection.execute(
            """
            INSERT INTO fact_vendas VALUES
                (
                    'S1', '2025-01-10', 90.00, 100.00, 10.00, 10.0000,
                    'MARCA', 'Modelo 1', 'Centro', 'AM', 'Loja', 'À vista',
                    'Ana', '', 'vendas.csv', 2
                ),
                (
                    'S2', '2025-01-20', 950.00, 1000.00, 50.00, 5.0000,
                    'MARCA', 'Modelo 2', 'Centro', 'AM', 'Loja', 'À vista',
                    'Ana', '', 'vendas.csv', 3
                );
            INSERT INTO quality_report VALUES
                ('invalid_data_venda', 'error', 0, 'passed');
            INSERT INTO raw_vendas VALUES ('S1'), ('S2');
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


def test_dashboard_displays_weighted_discount(tmp_path: Path, monkeypatch) -> None:
    database = tmp_path / "analytical.duckdb"
    _create_analytical_database(database)
    monkeypatch.setenv("SALES_PIPELINE_DB_PATH", str(database))

    dashboard = Path(__file__).parents[1] / "dashboard.py"
    app = AppTest.from_file(str(dashboard), default_timeout=15).run()

    assert not app.exception
    kpi_grid = next(
        markdown.value
        for markdown in app.markdown
        if '<div class="kpi-grid">' in markdown.value
    )
    assert "Desconto ponderado" in kpi_grid
    assert "5.5%" in kpi_grid
    assert "7.5%" not in kpi_grid
