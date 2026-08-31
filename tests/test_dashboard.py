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
                    'Bruno', 'orphan_consultor_id', 'vendas.csv', 3
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
                    'Diego', 'veiculo_multiple_sales', 'vendas.csv', 5
                ),
                (
                    'S5', '2025-03-20', 150.00, 150.00,
                    0.00, 0.00, 0.00, 0.0000,
                    'NISSAN', 'Modelo 5', 'Manaus', 'AM', NULL, NULL,
                    NULL, '', 'vendas.csv', 6
                );
            INSERT INTO quality_report VALUES
                ('duplicate_venda_id', 'error', 2, 'failed'),
                ('future_data_venda', 'warning', 1, 'warning'),
                ('invalid_data_venda', 'error', 0, 'passed'),
                ('missing_venda_id', 'error', 0, 'passed'),
                ('custom_unmapped_rule', 'warning', 0, 'passed');
            INSERT INTO raw_vendas VALUES
                ('S1'), ('S2'), ('S3'), ('S4'), ('S5'), ('S6');
            INSERT INTO rejected_sales VALUES ('S6');
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


def _traceability_table(app: AppTest):
    return app.tabs[2].dataframe[0].value


def _traceability_sales(app: AppTest) -> set[str]:
    return set(_traceability_table(app)["Venda"].tolist())


def _chart_specs(app: AppTest) -> tuple[str, ...]:
    return tuple(element.proto.spec for element in app.get("plotly_chart"))


def _sidebar_markdown(app: AppTest) -> list[str]:
    return [markdown.value for markdown in app.sidebar.markdown]


def _quality_kpi_grid(app: AppTest, class_name: str) -> str:
    return next(
        markdown.value
        for markdown in app.markdown
        if f'<div class="kpi-grid {class_name}">' in markdown.value
    )


def _quality_table(app: AppTest):
    return app.tabs[1].dataframe[0].value


def _traceability_kpi_grid(app: AppTest) -> str:
    return next(
        markdown.value
        for markdown in app.markdown
        if '<div class="kpi-grid traceability-kpis">' in markdown.value
    )


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
    invalid_date = quality_table.loc[
        quality_table["Regra"].eq("Data de venda inválida")
    ].iloc[0]
    assert invalid_date.to_dict() == {
        "Regra": "Data de venda inválida",
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


def test_quality_tab_displays_volume_rule_kpis_and_friendly_context(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = tmp_path / "quality-kpis.duckdb"
    _create_analytical_database(database)
    app = _run_dashboard(database, monkeypatch)

    assert not app.exception
    volume_kpis = _quality_kpi_grid(app, "quality-volume-kpis")
    assert '<div class="kpi-label">Recebidos</div>' in volume_kpis
    assert '<div class="kpi-value">6</div>' in volume_kpis
    assert '<div class="kpi-label">Válidos</div>' in volume_kpis
    assert '<div class="kpi-value">5</div>' in volume_kpis
    assert '<div class="kpi-label">Rejeitados</div>' in volume_kpis
    assert '<div class="kpi-value">1</div>' in volume_kpis
    assert '<div class="kpi-label">Taxa de aprovação</div>' in volume_kpis
    assert '<div class="kpi-value">83,33%</div>' in volume_kpis

    rules_kpis = _quality_kpi_grid(app, "quality-rules-kpis")
    assert '<div class="kpi-label">Regras executadas</div>' in rules_kpis
    assert '<div class="kpi-value">5</div>' in rules_kpis
    assert '<div class="kpi-label">Aprovadas</div>' in rules_kpis
    assert '<div class="kpi-value">3</div>' in rules_kpis
    assert '<div class="kpi-label">Falhas</div>' in rules_kpis
    assert '<div class="kpi-value">1</div>' in rules_kpis
    assert '<div class="kpi-label">Avisos</div>' in rules_kpis
    assert '<div class="kpi-value">1</div>' in rules_kpis

    markdown_values = [markdown.value for markdown in app.markdown]
    assert any("Qualidade dos dados" in value for value in markdown_values)
    assert any("5</b> de <b>6" in value for value in markdown_values)
    captions = [caption.value for caption in app.caption]
    assert any("regras de venda podem enviar registros" in value for value in captions)
    assert any("Aviso mantém a venda válida" in value for value in captions)


def test_quality_approval_rate_handles_zero_received_without_invalid_number(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = tmp_path / "quality-zero-received.duckdb"
    _create_analytical_database(database)
    connection = duckdb.connect(str(database))
    try:
        connection.execute("DELETE FROM raw_vendas")
    finally:
        connection.close()

    app = _run_dashboard(database, monkeypatch)

    assert not app.exception
    volume_kpis = _quality_kpi_grid(app, "quality-volume-kpis")
    assert '<div class="kpi-label">Recebidos</div>' in volume_kpis
    assert '<div class="kpi-value">0</div>' in volume_kpis
    assert '<div class="kpi-value">0,00%</div>' in volume_kpis
    assert "NaN" not in volume_kpis
    assert "inf" not in volume_kpis.lower()


def test_quality_local_severity_filter_only_changes_quality_detail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = tmp_path / "quality-severity.duckdb"
    _create_analytical_database(database)
    app = _run_dashboard(database, monkeypatch)
    overview_kpis = _kpi_grid(app)
    traceability_sales = _traceability_sales(app)

    app.selectbox("quality_severity_filter").set_value("Aviso").run()

    assert not app.exception
    quality_table = _quality_table(app)
    assert set(quality_table["Severidade"]) == {"Aviso"}
    assert set(quality_table["Regra"]) == {
        "Data de venda futura",
        "Custom Unmapped Rule",
    }
    assert _kpi_grid(app) == overview_kpis
    assert _traceability_sales(app) == traceability_sales


def test_quality_local_status_filter_and_fallback_rule_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = tmp_path / "quality-status.duckdb"
    _create_analytical_database(database)
    app = _run_dashboard(database, monkeypatch)

    assert "Custom Unmapped Rule" in set(_quality_table(app)["Regra"])

    app.selectbox("quality_status_filter").set_value("Falhou").run()

    assert not app.exception
    quality_table = _quality_table(app)
    assert quality_table["Status"].tolist() == ["Falhou"]
    assert quality_table["Regra"].tolist() == ["Venda duplicada"]


def test_quality_local_filters_handle_empty_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = tmp_path / "quality-empty-filter.duckdb"
    _create_analytical_database(database)
    app = _run_dashboard(database, monkeypatch)

    app.selectbox("quality_severity_filter").set_value("Erro")
    app.selectbox("quality_status_filter").set_value("Aviso")
    app.run()

    assert not app.exception
    assert _quality_table(app).empty
    assert "Nenhuma regra corresponde aos filtros locais selecionados." in [
        info.value for info in app.info
    ]


def test_quality_chart_uses_friendly_names_and_only_affected_rules(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = tmp_path / "quality-chart.duckdb"
    _create_analytical_database(database)
    app = _run_dashboard(database, monkeypatch)

    assert not app.exception
    quality_chart = _chart_specs(app)[-1]
    assert "Venda duplicada" in quality_chart
    assert "Data de venda futura" in quality_chart
    assert "Data de venda inválida" not in quality_chart
    assert "Custom Unmapped Rule" not in quality_chart


def test_quality_exports_the_locally_filtered_report_as_csv(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = tmp_path / "quality-export.duckdb"
    _create_analytical_database(database)
    app = _run_dashboard(database, monkeypatch)

    app.selectbox("quality_status_filter").set_value("Falhou").run()

    assert not app.exception
    quality_download = next(
        button
        for button in app.get("download_button")
        if button.label == "Baixar relatório de qualidade"
    )
    assert quality_download.url.endswith(".csv")
    assert _quality_table(app)["Regra"].tolist() == ["Venda duplicada"]


def test_traceability_displays_summary_lineage_and_null_alerts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = tmp_path / "traceability-summary.duckdb"
    _create_analytical_database(database)
    app = _run_dashboard(database, monkeypatch)

    assert not app.exception
    traceability_kpis = _traceability_kpi_grid(app)
    assert '<div class="kpi-label">Registros rastreáveis</div>' in traceability_kpis
    assert '<div class="kpi-value">5</div>' in traceability_kpis
    assert '<div class="kpi-label">Registros com alertas</div>' in traceability_kpis
    assert '<div class="kpi-value">2</div>' in traceability_kpis

    traceability = _traceability_table(app)
    assert traceability.columns.tolist() == [
        "Venda",
        "Data",
        "Alertas de qualidade",
        "Marca",
        "Modelo",
        "Loja",
        "UF",
        "Consultor",
        "Valor da venda",
        "Valor de referência",
        "Desconto (%)",
        "Arquivo de origem",
        "Linha de origem",
    ]
    alerts_by_sale = traceability.set_index("Venda")["Alertas de qualidade"]
    assert alerts_by_sale["S5"] == "Sem alertas"
    assert alerts_by_sale["S1"] == "Sem alertas"
    assert alerts_by_sale["S2"] == "orphan_consultor_id"
    assert any(
        "Cada venda preserva o arquivo e a linha de origem" in caption.value
        for caption in app.caption
    )


@pytest.mark.parametrize(
    ("query", "expected_sales"),
    [
        ("s2", {"S2"}),
        ("bRuNo", {"S2"}),
        ("centro", {"S1", "S3"}),
        ("modelo 4", {"S4"}),
    ],
)
def test_traceability_searches_business_fields_case_insensitively(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    query: str,
    expected_sales: set[str],
) -> None:
    database = tmp_path / f"traceability-search-{query.replace(' ', '-')}.duckdb"
    _create_analytical_database(database)
    app = _run_dashboard(database, monkeypatch)

    app.text_input("traceability_search").set_value(query).run()

    assert not app.exception
    assert _traceability_sales(app) == expected_sales
    count = len(expected_sales)
    label = "registro rastreável" if count == 1 else "registros rastreáveis"
    assert f"**{count} {label}**" in [markdown.value for markdown in app.markdown]


def test_traceability_search_handles_no_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = tmp_path / "traceability-no-result.duckdb"
    _create_analytical_database(database)
    app = _run_dashboard(database, monkeypatch)

    app.text_input("traceability_search").set_value("venda inexistente").run()

    assert not app.exception
    assert _traceability_table(app).empty
    assert "**0 registros rastreáveis**" in [
        markdown.value for markdown in app.markdown
    ]
    assert "Nenhuma venda corresponde aos critérios de investigação." in [
        info.value for info in app.info
    ]


@pytest.mark.parametrize(
    ("quality_filter", "expected_sales"),
    [
        ("Com alerta", {"S2", "S4"}),
        ("Sem alerta", {"S1", "S3", "S5"}),
    ],
)
def test_traceability_filters_records_by_alert_presence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    quality_filter: str,
    expected_sales: set[str],
) -> None:
    database = tmp_path / f"traceability-{quality_filter.replace(' ', '-')}.duckdb"
    _create_analytical_database(database)
    app = _run_dashboard(database, monkeypatch)

    app.selectbox("traceability_quality_filter").set_value(quality_filter).run()

    assert not app.exception
    assert _traceability_sales(app) == expected_sales
    assert _quality_table(app)["Regra"].nunique() == 5


@pytest.mark.parametrize(
    ("sort_option", "expected_order"),
    [
        ("Data mais recente", ["S5", "S4", "S3", "S2", "S1"]),
        ("Data mais antiga", ["S1", "S2", "S3", "S4", "S5"]),
        ("Maior valor de venda", ["S4", "S3", "S5", "S2", "S1"]),
        ("Menor valor de venda", ["S1", "S2", "S5", "S3", "S4"]),
    ],
)
def test_traceability_sorts_the_investigated_records(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    sort_option: str,
    expected_order: list[str],
) -> None:
    database = tmp_path / f"traceability-sort-{sort_option.replace(' ', '-')}.duckdb"
    _create_analytical_database(database)
    app = _run_dashboard(database, monkeypatch)

    app.selectbox("traceability_sort").set_value(sort_option).run()

    assert not app.exception
    assert _traceability_table(app)["Venda"].tolist() == expected_order


def test_traceability_export_reflects_the_current_investigation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = tmp_path / "traceability-export.duckdb"
    _create_analytical_database(database)
    app = _run_dashboard(database, monkeypatch)
    initial_download = next(
        button
        for button in app.get("download_button")
        if button.label == "Baixar dados investigados"
    )

    app.text_input("traceability_search").set_value("S2")
    app.selectbox("traceability_quality_filter").set_value("Com alerta")
    app.run()

    assert not app.exception
    filtered_download = next(
        button
        for button in app.get("download_button")
        if button.label == "Baixar dados investigados"
    )
    assert _traceability_table(app)["Venda"].tolist() == ["S2"]
    assert filtered_download.url.endswith(".csv")
    assert filtered_download.url != initial_download.url


def test_traceability_filters_persist_in_dark_mode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = tmp_path / "traceability-dark.duckdb"
    _create_analytical_database(database)
    app = _run_dashboard(database, monkeypatch)

    app.text_input("traceability_search").set_value("s2")
    app.selectbox("traceability_quality_filter").set_value("Com alerta")
    app.selectbox("traceability_sort").set_value("Menor valor de venda")
    app.run()
    light_traceability = _traceability_table(app).copy()

    app.sidebar.toggle("dark_mode").set_value(True).run()

    assert not app.exception
    assert app.text_input("traceability_search").value == "s2"
    assert app.selectbox("traceability_quality_filter").value == "Com alerta"
    assert app.selectbox("traceability_sort").value == "Menor valor de venda"
    assert _traceability_table(app).equals(light_traceability)


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
