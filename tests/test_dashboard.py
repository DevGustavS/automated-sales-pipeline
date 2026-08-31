from __future__ import annotations

from datetime import date
from pathlib import Path

import duckdb
import pytest
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
                    'TOYOTA', 'Modelo 1', 'Centro', 'AM', 'Loja', 'À vista',
                    'Ana', '', 'vendas.csv', 2
                ),
                (
                    'S2', '2025-01-20', 110.00, 100.00,
                    0.00, 10.00, -10.00, 0.0000,
                    'TOYOTA', 'Modelo 2', 'Norte', 'AM', 'Site', 'Pix',
                    'Bruno', '', 'vendas.csv', 3
                ),
                (
                    'S3', '2025-02-15', 200.00, 200.00,
                    0.00, 0.00, 0.00, 0.0000,
                    'HONDA', 'Modelo 3', 'Centro', 'SP', 'Marketplace',
                    'Financiamento', 'Carla', '', 'vendas.csv', 4
                ),
                (
                    'S4', '2025-03-05', 300.00, 300.00,
                    0.00, 0.00, 0.00, 0.0000,
                    'FORD', 'Modelo 4', 'Sul', 'RJ', 'Telefone', 'Cartão',
                    'Diego', '', 'vendas.csv', 5
                ),
                (
                    'S5', '2025-03-20', 150.00, 150.00,
                    0.00, 0.00, 0.00, 0.0000,
                    'NISSAN', 'Modelo 5', 'Manaus', 'AM', NULL, NULL,
                    NULL, '', 'vendas.csv', 6
                );
            INSERT INTO quality_report VALUES
                ('invalid_data_venda', 'error', 0, 'passed');
            INSERT INTO raw_vendas VALUES ('S1'), ('S2'), ('S3'), ('S4'), ('S5');
            """
        )
    finally:
        connection.close()


def _run_dashboard(database: Path, monkeypatch: pytest.MonkeyPatch) -> AppTest:
    monkeypatch.setenv("SALES_PIPELINE_DB_PATH", str(database))
    dashboard = Path(__file__).parents[1] / "dashboard.py"
    return AppTest.from_file(str(dashboard), default_timeout=15).run()


def _kpi_grid(app: AppTest) -> str:
    return next(
        markdown.value
        for markdown in app.markdown
        if '<div class="kpi-grid">' in markdown.value
    )


def _traceability_sales(app: AppTest) -> set[str]:
    traceability = app.tabs[2].dataframe[0].value
    return set(traceability["Venda"].tolist())


def _chart_specs(app: AppTest) -> tuple[str, ...]:
    return tuple(element.proto.spec for element in app.get("plotly_chart"))


def _sidebar_markdown(app: AppTest) -> list[str]:
    return [markdown.value for markdown in app.sidebar.markdown]


def test_dashboard_handles_empty_fact_before_building_date_filter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = tmp_path / "empty.duckdb"
    _create_empty_database(database)
    app = _run_dashboard(database, monkeypatch)

    assert not app.exception
    assert [warning.value for warning in app.warning] == [
        "Nenhuma venda válida está disponível para exibição."
    ]


def test_dashboard_displays_discount_without_offsetting_reference_premium(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = tmp_path / "analytical.duckdb"
    _create_analytical_database(database)
    app = _run_dashboard(database, monkeypatch)

    assert not app.exception
    kpi_grid = _kpi_grid(app)
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
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = tmp_path / "analytical.duckdb"
    _create_analytical_database(database)
    app = _run_dashboard(database, monkeypatch)

    app.sidebar.multiselect("filter_channels").set_value(["Site"]).run()

    assert not app.exception
    assert app.sidebar.toggle("dark_mode").label == "🌙 Modo escuro"
    assert app.sidebar.toggle("dark_mode").value is False
    assert _traceability_sales(app) == {"S2"}
    assert app.sidebar.multiselect("filter_channels").value == ["Site"]
    light_css = next(
        markdown.value
        for markdown in app.markdown
        if "--background-color:" in markdown.value
    )
    light_kpis = _kpi_grid(app)
    light_tables = [dataframe.value.copy() for dataframe in app.dataframe]
    assert len(_chart_specs(app)) == 6
    assert "#F7F8FA" in light_css
    light_download_css = light_css.split(
        '[data-testid="stDownloadButton"] button {', maxsplit=1
    )[1].split("}", maxsplit=1)[0]
    assert "background-color: #FFFFFF !important;" in light_download_css
    assert "color: #2C2C2B !important;" in light_download_css

    app.sidebar.toggle("dark_mode").set_value(True).run()

    assert not app.exception
    assert app.sidebar.toggle("dark_mode").value is True
    assert app.sidebar.multiselect("filter_channels").value == ["Site"]
    assert _traceability_sales(app) == {"S2"}
    dark_css = next(
        markdown.value
        for markdown in app.markdown
        if "--background-color:" in markdown.value
    )
    dark_kpis = _kpi_grid(app)
    assert "#0E1117" in dark_css
    dark_download_css = dark_css.split(
        '[data-testid="stDownloadButton"] button {', maxsplit=1
    )[1].split("}", maxsplit=1)[0]
    assert "background-color: #161B22 !important;" in dark_download_css
    assert "color: #F0F2F6 !important;" in dark_download_css
    assert dark_kpis == light_kpis
    assert len(_chart_specs(app)) == 6
    for dark_table, light_table in zip(
        [dataframe.value for dataframe in app.dataframe], light_tables, strict=True
    ):
        assert dark_table.equals(light_table)

    app.sidebar.toggle("dark_mode").set_value(False).run()

    assert not app.exception
    assert app.sidebar.toggle("dark_mode").value is False
    assert app.sidebar.multiselect("filter_channels").value == ["Site"]
    assert _traceability_sales(app) == {"S2"}
    restored_css = next(
        markdown.value
        for markdown in app.markdown
        if "--background-color:" in markdown.value
    )
    restored_kpis = _kpi_grid(app)
    assert "#F7F8FA" in restored_css
    assert restored_kpis == light_kpis


def test_dashboard_starts_with_dynamic_filter_options_and_all_sales(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = tmp_path / "filters.duckdb"
    _create_analytical_database(database)
    app = _run_dashboard(database, monkeypatch)

    assert not app.exception
    assert tuple(app.sidebar.date_input("filter_period").value) == (
        date(2025, 1, 10),
        date(2025, 3, 20),
    )
    expected_options = {
        "filter_brands": {"FORD", "HONDA", "NISSAN", "TOYOTA"},
        "filter_stores": {"Centro", "Manaus", "Norte", "Sul"},
        "filter_states": {"AM", "RJ", "SP"},
        "filter_channels": {"Loja", "Marketplace", "Site", "Telefone"},
        "filter_payment_methods": {"Cartão", "Financiamento", "Pix", "À vista"},
        "filter_consultants": {"Ana", "Bruno", "Carla", "Diego"},
    }
    assert len(app.sidebar.multiselect) == len(expected_options)
    for key, options in expected_options.items():
        widget = app.sidebar.multiselect(key)
        assert set(widget.options) == options
        assert widget.value == []
        assert None not in widget.options

    assert app.sidebar.caption.values == ["Nenhum filtro ativo"]
    assert "**5 vendas encontradas**" in _sidebar_markdown(app)
    assert _traceability_sales(app) == {"S1", "S2", "S3", "S4", "S5"}
    assert len(_chart_specs(app)) == 6


@pytest.mark.parametrize(
    ("filter_key", "selected_value", "expected_sale"),
    [
        ("filter_channels", "Site", "S2"),
        ("filter_payment_methods", "Financiamento", "S3"),
        ("filter_consultants", "Diego", "S4"),
    ],
)
def test_dashboard_filters_each_new_dimension(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    filter_key: str,
    selected_value: str,
    expected_sale: str,
) -> None:
    database = tmp_path / f"{filter_key}.duckdb"
    _create_analytical_database(database)
    app = _run_dashboard(database, monkeypatch)

    app.sidebar.multiselect(filter_key).set_value([selected_value]).run()

    assert not app.exception
    assert _traceability_sales(app) == {expected_sale}
    assert "**● Filtros ativos**" in _sidebar_markdown(app)
    assert "**1 venda encontrada**" in _sidebar_markdown(app)


def test_dashboard_combines_existing_and_new_filters(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = tmp_path / "combined.duckdb"
    _create_analytical_database(database)
    app = _run_dashboard(database, monkeypatch)
    baseline_kpis = _kpi_grid(app)
    baseline_charts = _chart_specs(app)

    app.sidebar.multiselect("filter_brands").set_value(["TOYOTA"]).run()

    assert not app.exception
    assert _traceability_sales(app) == {"S1", "S2"}
    assert "**2 vendas encontradas**" in _sidebar_markdown(app)
    assert _kpi_grid(app) != baseline_kpis
    assert _chart_specs(app) != baseline_charts

    app.sidebar.multiselect("filter_stores").set_value(["Centro"])
    app.sidebar.multiselect("filter_states").set_value(["AM"])
    app.run()

    assert not app.exception
    assert _traceability_sales(app) == {"S1"}
    assert "**1 venda encontrada**" in _sidebar_markdown(app)

    app.sidebar.date_input("filter_period").set_value(
        (date(2025, 1, 10), date(2025, 1, 15))
    )
    app.sidebar.multiselect("filter_channels").set_value(["Loja"])
    app.sidebar.multiselect("filter_payment_methods").set_value(["À vista"])
    app.sidebar.multiselect("filter_consultants").set_value(["Ana"])
    app.run()

    assert not app.exception
    assert _traceability_sales(app) == {"S1"}
    assert "**● Filtros ativos**" in _sidebar_markdown(app)
    assert "**1 venda encontrada**" in _sidebar_markdown(app)
    assert '<div class="kpi-label">Vendas</div><div class="kpi-value">1</div>' in (
        _kpi_grid(app)
    )
    assert _kpi_grid(app) != baseline_kpis
    assert _chart_specs(app) != baseline_charts


def test_dashboard_handles_filter_combination_without_results(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = tmp_path / "empty-filter.duckdb"
    _create_analytical_database(database)
    app = _run_dashboard(database, monkeypatch)

    app.sidebar.multiselect("filter_brands").set_value(["TOYOTA"])
    app.sidebar.multiselect("filter_channels").set_value(["Site"])
    app.sidebar.multiselect("filter_consultants").set_value(["Ana"])
    app.run()

    assert not app.exception
    assert [warning.value for warning in app.warning] == [
        (
            "Nenhuma venda corresponde aos filtros selecionados. "
            "Ajuste ou limpe os filtros para continuar."
        )
    ]
    assert "**● Filtros ativos**" in _sidebar_markdown(app)
    assert "**0 vendas encontradas**" in _sidebar_markdown(app)


def test_dashboard_clear_filters_restores_the_complete_default_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = tmp_path / "clear.duckdb"
    _create_analytical_database(database)
    app = _run_dashboard(database, monkeypatch)
    baseline_kpis = _kpi_grid(app)
    baseline_charts = _chart_specs(app)

    app.sidebar.date_input("filter_period").set_value(
        (date(2025, 1, 10), date(2025, 1, 15))
    )
    app.sidebar.multiselect("filter_brands").set_value(["TOYOTA"])
    app.sidebar.multiselect("filter_stores").set_value(["Centro"])
    app.sidebar.multiselect("filter_states").set_value(["AM"])
    app.sidebar.multiselect("filter_channels").set_value(["Loja"])
    app.sidebar.multiselect("filter_payment_methods").set_value(["À vista"])
    app.sidebar.multiselect("filter_consultants").set_value(["Ana"])
    app.run()
    assert _traceability_sales(app) == {"S1"}

    app.sidebar.button("clear_filters").click().run()

    assert not app.exception
    assert tuple(app.sidebar.date_input("filter_period").value) == (
        date(2025, 1, 10),
        date(2025, 3, 20),
    )
    assert all(widget.value == [] for widget in app.sidebar.multiselect)
    assert app.sidebar.caption.values == ["Nenhum filtro ativo"]
    assert "**5 vendas encontradas**" in _sidebar_markdown(app)
    assert _traceability_sales(app) == {"S1", "S2", "S3", "S4", "S5"}
    assert _kpi_grid(app) == baseline_kpis
    assert _chart_specs(app) == baseline_charts
