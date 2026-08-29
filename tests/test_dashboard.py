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
                desconto_concedido DECIMAL(18,2),
                agio_referencia DECIMAL(18,2),
                variacao_liquida_referencia DECIMAL(18,2),
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
                    'S1', '2025-01-10', 90.00, 100.00,
                    10.00, 0.00, 10.00, 10.0000,
                    'MARCA', 'Modelo 1', 'Centro', 'AM', 'Loja', 'À vista',
                    'Ana', '', 'vendas.csv', 2
                ),
                (
                    'S2', '2025-01-20', 110.00, 100.00,
                    0.00, 10.00, -10.00, 0.0000,
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


def test_dashboard_displays_discount_without_offsetting_reference_premium(
    tmp_path: Path, monkeypatch
) -> None:
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
    assert "Desconto concedido" in kpi_grid
    assert "R$ 10,00" in kpi_grid
    assert "Desconto ponderado" not in kpi_grid
    assert "Aprovação de qualidade" not in kpi_grid

    quality_table, traceability_table = [dataframe.value for dataframe in app.dataframe]
    assert quality_table.columns.tolist() == [
        "Regra",
        "Severidade",
        "Registros afetados",
        "Status",
    ]
    assert quality_table.iloc[0].to_dict() == {
        "Regra": "invalid_data_venda",
        "Severidade": "Erro",
        "Registros afetados": 0,
        "Status": "Aprovada",
    }
    assert "Arquivo de origem" in traceability_table
    assert "Linha de origem" in traceability_table
    assert "Alertas de qualidade" in traceability_table


def test_dashboard_toggles_theme_without_changing_kpis_or_tables(
    tmp_path: Path, monkeypatch
) -> None:
    database = tmp_path / "analytical.duckdb"
    _create_analytical_database(database)
    monkeypatch.setenv("SALES_PIPELINE_DB_PATH", str(database))

    dashboard = Path(__file__).parents[1] / "dashboard.py"
    app = AppTest.from_file(str(dashboard), default_timeout=15).run()

    assert not app.exception
    assert app.toggle[0].label == "🌙 Modo escuro"
    assert app.toggle[0].value is False
    light_css = next(
        markdown.value
        for markdown in app.markdown
        if "--background-color:" in markdown.value
    )
    light_kpis = next(
        markdown.value
        for markdown in app.markdown
        if '<div class="kpi-grid">' in markdown.value
    )
    light_tables = [dataframe.value.copy() for dataframe in app.dataframe]
    assert "#F7F8FA" in light_css
    light_download_css = light_css.split(
        '[data-testid="stDownloadButton"] button {', maxsplit=1
    )[1].split("}", maxsplit=1)[0]
    assert "background-color: #FFFFFF !important;" in light_download_css
    assert "color: #2C2C2B !important;" in light_download_css

    app.toggle[0].set_value(True).run()

    assert not app.exception
    assert app.toggle[0].value is True
    dark_css = next(
        markdown.value
        for markdown in app.markdown
        if "--background-color:" in markdown.value
    )
    dark_kpis = next(
        markdown.value
        for markdown in app.markdown
        if '<div class="kpi-grid">' in markdown.value
    )
    assert "#0E1117" in dark_css
    dark_download_css = dark_css.split(
        '[data-testid="stDownloadButton"] button {', maxsplit=1
    )[1].split("}", maxsplit=1)[0]
    assert "background-color: #161B22 !important;" in dark_download_css
    assert "color: #F0F2F6 !important;" in dark_download_css
    assert dark_kpis == light_kpis
    for dark_table, light_table in zip(
        [dataframe.value for dataframe in app.dataframe], light_tables, strict=True
    ):
        assert dark_table.equals(light_table)

    app.toggle[0].set_value(False).run()

    assert not app.exception
    assert app.toggle[0].value is False
    restored_css = next(
        markdown.value
        for markdown in app.markdown
        if "--background-color:" in markdown.value
    )
    restored_kpis = next(
        markdown.value
        for markdown in app.markdown
        if '<div class="kpi-grid">' in markdown.value
    )
    assert "#F7F8FA" in restored_css
    assert restored_kpis == light_kpis
