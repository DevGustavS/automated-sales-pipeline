from __future__ import annotations

import os
from datetime import date
from pathlib import Path

import duckdb
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

DB_PATH = Path(
    os.environ.get("SALES_PIPELINE_DB_PATH", "data/output/sales_pipeline.duckdb")
)
CSV_PATH = Path("data/output/fact_sales_pipeline.csv")

COLORS = {
    "blue": "#2783DE",
    "blue_soft": "#E5F2FC",
    "green": "#46A171",
    "orange": "#D5803B",
    "red": "#E56458",
}
PALETTE = ["#5E9FE8", "#EAC26B", "#72BC8F", "#BF8EDA", "#DE9255", "#DF84A8"]
FILTER_MULTISELECT_KEYS = (
    "filter_brands",
    "filter_stores",
    "filter_states",
    "filter_channels",
    "filter_payment_methods",
    "filter_consultants",
)

THEMES = {
    "light": {
        "app": "#F7F8FA",
        "surface": "#FFFFFF",
        "text": "#2C2C2B",
        "muted": "#7D7A75",
        "border": "#E6E5E3",
        "grid": "#EFEFED",
        "shadow": "rgba(0, 0, 0, .03)",
        "hover_bg": "#202020",
        "hover_text": "#FFFFFF",
        "quality_bg": "#E8F1EC",
        "quality_text": "#2E6849",
        "quality_border": "#CDE3D6",
        "dataframe_filter": "none",
    },
    "dark": {
        "app": "#0E1117",
        "surface": "#161B22",
        "text": "#F0F2F6",
        "muted": "#A8B0BC",
        "border": "#30363D",
        "grid": "#30363D",
        "shadow": "rgba(0, 0, 0, .24)",
        "hover_bg": "#F0F2F6",
        "hover_text": "#0E1117",
        "quality_bg": "#17271F",
        "quality_text": "#8BD5A8",
        "quality_border": "#2F6848",
        "dataframe_filter": "invert(.9) hue-rotate(180deg)",
    },
}

st.set_page_config(
    page_title="Sales Performance",
    page_icon="🚘",
    layout="wide",
    initial_sidebar_state="expanded",
)

dark_mode = st.sidebar.toggle("🌙 Modo escuro", value=False, key="dark_mode")
THEME = THEMES["dark" if dark_mode else "light"]

st.markdown(
    f"""
    <style>
    .stApp {{
        background: {THEME["app"]};
        color: {THEME["text"]};
        --background-color: {THEME["app"]};
        --secondary-background-color: {THEME["surface"]};
        --text-color: {THEME["text"]};
    }}
    .block-container {{
        max-width: 1440px;
        padding-top: 4.25rem !important;
        padding-bottom: 3rem;
    }}
    [data-testid="stSidebar"] {{
        background: {THEME["surface"]};
        border-right: 1px solid {THEME["border"]};
    }}
    [data-testid="stHeader"] {{ background: {THEME["app"]}; }}
    [data-testid="stSidebar"] p,
    [data-testid="stSidebar"] label,
    [data-testid="stSidebar"] [data-testid="stMarkdownContainer"],
    [data-testid="stCaptionContainer"] {{ color: {THEME["muted"]}; }}
    [data-testid="stSidebar"] [data-baseweb="select"] > div,
    [data-testid="stSidebar"] [data-baseweb="input"] > div {{
        background-color: {THEME["surface"]};
        color: {THEME["text"]};
        border-color: {THEME["border"]};
    }}
    [data-testid="stMultiSelect"] [role="group"],
    [data-testid="stDateInputField"] {{
        background-color: {THEME["surface"]};
        color: {THEME["text"]};
        border-color: {THEME["border"]};
    }}
    [data-testid="stMultiSelect"] input,
    [data-testid="stDateInputField"] [role="spinbutton"] {{
        color: {THEME["text"]};
    }}
    [data-testid="stMultiSelect"] input::placeholder {{
        color: {THEME["muted"]};
        opacity: 1;
    }}
    .kpi-grid {{
        display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
        gap: 12px; margin: 0 0 18px;
    }}
    .kpi-card {{
        min-width: 0; background: {THEME["surface"]}; border: 1px solid {THEME["border"]};
        border-radius: 12px; padding: 17px 18px;
        box-shadow: 0 1px 2px {THEME["shadow"]};
    }}
    .kpi-label {{
        color: {THEME["muted"]}; font-size: .78rem; font-weight: 700;
        letter-spacing: .01em; margin-bottom: 7px;
    }}
    .kpi-value {{
        color: {THEME["text"]}; font-size: clamp(1.25rem, 1.75vw, 1.65rem);
        line-height: 1.15; font-weight: 760; white-space: nowrap;
    }}
    [data-testid="stPlotlyChart"] {{
        background: {THEME["surface"]}; border: 1px solid {THEME["border"]}; border-radius: 12px;
        padding: 8px; box-shadow: 0 1px 2px {THEME["shadow"]};
    }}
    .dashboard-kicker {{
        display: block; min-height: 24px; padding-top: 2px;
        color: #2783DE; font-size: .82rem; line-height: 1.45;
        font-weight: 750; letter-spacing: .08em; text-transform: uppercase;
    }}
    .dashboard-title {{ font-size: 2rem; font-weight: 760; margin: .2rem 0 0; color: {THEME["text"]}; }}
    .dashboard-subtitle {{ color: {THEME["muted"]}; margin: .35rem 0 1.4rem; }}
    .section-title {{ font-size: 1.05rem; font-weight: 700; margin: 1.25rem 0 .65rem; color: {THEME["text"]}; }}
    .quality-note {{
        background: {THEME["quality_bg"]}; color: {THEME["quality_text"]};
        border: 1px solid {THEME["quality_border"]}; border-radius: 10px; padding: 12px 14px;
    }}
    div[data-baseweb="tab-list"] {{ gap: 10px; border-bottom-color: {THEME["border"]}; }}
    [data-testid="stTab"] {{
        border-radius: 8px; padding-left: 16px; padding-right: 16px;
        color: {THEME["muted"]};
    }}
    [data-testid="stTab"] p {{ color: inherit; }}
    [data-testid="stTab"][aria-selected="true"] {{ color: #2783DE; }}
    [data-testid="stDataFrame"],
    [data-testid="stDataFrameResizable"] {{
        background: {THEME["surface"]};
        border-color: {THEME["border"]};
        color: {THEME["text"]};
    }}
    [data-testid="stDataFrame"] .stDataFrameGlideDataEditor {{
        --gdg-text-dark: {THEME["text"]} !important;
        --gdg-text-medium: {THEME["muted"]} !important;
        --gdg-text-light: {THEME["muted"]} !important;
        --gdg-text-bubble: {THEME["muted"]} !important;
        --gdg-bg-icon-header: {THEME["muted"]} !important;
        --gdg-fg-icon-header: {THEME["surface"]} !important;
        --gdg-text-header: {THEME["muted"]} !important;
        --gdg-text-group-header: {THEME["muted"]} !important;
        --gdg-bg-group-header: {THEME["surface"]} !important;
        --gdg-bg-group-header-hovered: {THEME["border"]} !important;
        --gdg-bg-cell: {THEME["app"]} !important;
        --gdg-bg-cell-medium: {THEME["app"]} !important;
        --gdg-bg-header: {THEME["surface"]} !important;
        --gdg-bg-header-has-focus: {THEME["border"]} !important;
        --gdg-bg-header-hovered: {THEME["border"]} !important;
        --gdg-bg-bubble: {THEME["surface"]} !important;
        --gdg-bg-bubble-selected: {THEME["border"]} !important;
        --gdg-border-color: {THEME["border"]} !important;
        --gdg-horizontal-border-color: {THEME["border"]} !important;
        --gdg-link-color: #2783DE !important;
    }}
    [data-testid="stDataFrame"] canvas {{
        filter: {THEME["dataframe_filter"]};
    }}
    [data-testid="stDownloadButton"] button {{
        background-color: {THEME["surface"]} !important;
        color: {THEME["text"]} !important;
        border: 1px solid {THEME["border"]} !important;
    }}
    [data-testid="stDownloadButton"] button p {{ color: inherit; }}
    [data-testid="stDownloadButton"] button:hover {{
        background-color: {THEME["app"]} !important;
        color: #2783DE !important;
        border-color: #2783DE !important;
    }}
    [data-testid="stDownloadButton"] button:focus-visible {{
        outline: 2px solid #2783DE;
        outline-offset: 2px;
    }}
    @media (max-width: 760px) {{
        .block-container {{ padding-left: 1rem; padding-right: 1rem; }}
        .kpi-grid {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
        .kpi-value {{ font-size: 1.2rem; }}
    }}
    </style>
    """,
    unsafe_allow_html=True,
)


def brl(value: float) -> str:
    formatted = f"{value:,.2f}"
    return "R$ " + formatted.replace(",", "X").replace(".", ",").replace("X", ".")


def compact_brl(value: float) -> str:
    absolute = abs(value)
    if absolute >= 1_000_000_000:
        return f"R$ {value / 1_000_000_000:.1f} bi".replace(".", ",")
    if absolute >= 1_000_000:
        return f"R$ {value / 1_000_000:.1f} mi".replace(".", ",")
    if absolute >= 1_000:
        return f"R$ {value / 1_000:.1f} mil".replace(".", ",")
    return brl(value)


def kpi_card(label: str, value: str) -> str:
    return (
        '<div class="kpi-card">'
        f'<div class="kpi-label">{label}</div>'
        f'<div class="kpi-value">{value}</div>'
        "</div>"
    )


def integer(value: float) -> str:
    return f"{int(value):,}".replace(",", ".")


def clear_filters(full_period: tuple[date, date]) -> None:
    st.session_state["filter_period"] = full_period
    for key in FILTER_MULTISELECT_KEYS:
        st.session_state[key] = []


def style_figure(fig: go.Figure, height: int = 360) -> go.Figure:
    fig.update_layout(
        height=height,
        margin={"l": 22, "r": 22, "t": 48, "b": 24},
        paper_bgcolor=THEME["surface"],
        plot_bgcolor=THEME["surface"],
        font={"family": "Arial, sans-serif", "color": THEME["text"], "size": 13},
        title_font={"size": 16, "color": THEME["text"]},
        hoverlabel={
            "bgcolor": THEME["hover_bg"],
            "font_color": THEME["hover_text"],
        },
        legend={
            "orientation": "h",
            "yanchor": "bottom",
            "y": 1.02,
            "xanchor": "right",
            "x": 1,
        },
        xaxis={"showgrid": False, "linecolor": THEME["border"]},
        yaxis={"gridcolor": THEME["grid"], "griddash": "dot", "zeroline": False},
    )
    return fig


@st.cache_data(show_spinner=False)
def load_data(
    database: str, modified_at: float
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, int]]:
    del modified_at
    connection = duckdb.connect(database, read_only=True)
    try:
        sales = connection.execute(
            """
            SELECT
                venda_id, data_venda, valor_venda, valor_referencia,
                desconto_concedido, desconto_percentual, marca, modelo, loja, uf,
                canal_origem, forma_pagamento, consultor,
                quality_issues, __source_file, __source_line
            FROM fact_vendas
            """
        ).df()
        quality = connection.execute(
            """
            SELECT "check", severity, failed_rows, status
            FROM quality_report
            ORDER BY failed_rows DESC, "check"
            """
        ).df()
        counts = connection.execute(
            """
            SELECT
                (SELECT COUNT(*) FROM raw_vendas) AS received,
                (SELECT COUNT(*) FROM fact_vendas) AS valid,
                (SELECT COUNT(*) FROM rejected_sales) AS rejected
            """
        ).fetchone()
    finally:
        connection.close()

    sales["data_venda"] = pd.to_datetime(sales["data_venda"])
    sales["marca"] = sales["marca"].astype("string").str.strip().str.upper()
    sales["canal_origem"] = (
        sales["canal_origem"].astype("string").str.strip().str.title()
    )
    sales["forma_pagamento"] = (
        sales["forma_pagamento"].astype("string").str.strip().str.capitalize()
    )
    return (
        sales,
        quality,
        {
            "received": int(counts[0]),
            "valid": int(counts[1]),
            "rejected": int(counts[2]),
        },
    )


if not DB_PATH.exists():
    st.error(f"Banco não encontrado: {DB_PATH}. Execute o pipeline antes do dashboard.")
    st.code(
        'python -u build_pipeline.py "data/incoming/Teste_Tecnico_Dados_Candidato_20260825.zip" --output "data/output"'
    )
    st.stop()

sales, quality, counts = load_data(str(DB_PATH), DB_PATH.stat().st_mtime)

if sales.empty:
    st.warning("Nenhuma venda válida está disponível para exibição.")
    st.stop()

st.sidebar.markdown("### Filtros")
minimum_date = sales["data_venda"].min().date()
maximum_date = sales["data_venda"].max().date()
full_period = (minimum_date, maximum_date)
if "filter_period" not in st.session_state:
    st.session_state["filter_period"] = full_period
date_range = st.sidebar.date_input(
    "Período",
    min_value=minimum_date,
    max_value=maximum_date,
    key="filter_period",
)

brands = sorted(sales["marca"].dropna().unique().tolist())
stores = sorted(sales["loja"].dropna().unique().tolist())
states = sorted(sales["uf"].dropna().unique().tolist())
channels = sorted(sales["canal_origem"].dropna().unique().tolist())
payment_methods = sorted(sales["forma_pagamento"].dropna().unique().tolist())
consultants = sorted(sales["consultor"].dropna().unique().tolist())
selected_brands = st.sidebar.multiselect("Marcas", brands, key="filter_brands")
selected_stores = st.sidebar.multiselect("Lojas", stores, key="filter_stores")
selected_states = st.sidebar.multiselect("UF", states, key="filter_states")
selected_channels = st.sidebar.multiselect(
    "Canal de origem", channels, key="filter_channels"
)
selected_payment_methods = st.sidebar.multiselect(
    "Forma de pagamento", payment_methods, key="filter_payment_methods"
)
selected_consultants = st.sidebar.multiselect(
    "Consultor", consultants, key="filter_consultants"
)
st.sidebar.button(
    "Limpar filtros",
    key="clear_filters",
    on_click=clear_filters,
    args=(full_period,),
    width="stretch",
)

filtered = sales.copy()
if isinstance(date_range, (tuple, list)) and len(date_range) == 2:
    start_date, end_date = pd.Timestamp(date_range[0]), pd.Timestamp(date_range[1])
    filtered = filtered[filtered["data_venda"].between(start_date, end_date)]
if selected_brands:
    filtered = filtered[filtered["marca"].isin(selected_brands)]
if selected_stores:
    filtered = filtered[filtered["loja"].isin(selected_stores)]
if selected_states:
    filtered = filtered[filtered["uf"].isin(selected_states)]
if selected_channels:
    filtered = filtered[filtered["canal_origem"].isin(selected_channels)]
if selected_payment_methods:
    filtered = filtered[filtered["forma_pagamento"].isin(selected_payment_methods)]
if selected_consultants:
    filtered = filtered[filtered["consultor"].isin(selected_consultants)]

period_is_filtered = not (
    isinstance(date_range, (tuple, list))
    and len(date_range) == 2
    and tuple(date_range) == full_period
)
filters_are_active = period_is_filtered or any(
    (
        selected_brands,
        selected_stores,
        selected_states,
        selected_channels,
        selected_payment_methods,
        selected_consultants,
    )
)
if filters_are_active:
    st.sidebar.markdown("**● Filtros ativos**")
else:
    st.sidebar.caption("Nenhum filtro ativo")

filtered_count = len(filtered)
result_label = "venda encontrada" if filtered_count == 1 else "vendas encontradas"
st.sidebar.markdown(f"**{integer(filtered_count)} {result_label}**")

st.markdown(
    '<div class="dashboard-kicker">Automated Sales Pipeline</div>',
    unsafe_allow_html=True,
)
st.markdown(
    '<div class="dashboard-title">Desempenho de vendas</div>',
    unsafe_allow_html=True,
)
st.markdown(
    '<div class="dashboard-subtitle">Visão consolidada das vendas válidas, com filtros interativos e rastreabilidade.</div>',
    unsafe_allow_html=True,
)

if filtered.empty:
    st.warning(
        "Nenhuma venda corresponde aos filtros selecionados. "
        "Ajuste ou limpe os filtros para continuar."
    )
    st.stop()

revenue = float(filtered["valor_venda"].sum())
sales_count = len(filtered)
average_ticket = float(filtered["valor_venda"].mean())
total_discount = float(filtered["desconto_concedido"].sum())

kpis = "".join(
    [
        kpi_card("Faturamento", compact_brl(revenue)),
        kpi_card("Vendas", integer(sales_count)),
        kpi_card("Ticket médio", compact_brl(average_ticket)),
        kpi_card("Desconto concedido", compact_brl(total_discount)),
    ]
)
st.markdown(f'<div class="kpi-grid">{kpis}</div>', unsafe_allow_html=True)

overview_tab, quality_tab, traceability_tab = st.tabs(
    ["Visão geral", "Qualidade", "Rastreabilidade"]
)

with overview_tab:
    monthly = (
        filtered.assign(mes=filtered["data_venda"].dt.to_period("M").dt.to_timestamp())
        .groupby("mes", as_index=False)
        .agg(receita=("valor_venda", "sum"), vendas=("venda_id", "count"))
        .sort_values("mes")
    )

    line = go.Figure()
    line.add_trace(
        go.Scatter(
            x=monthly["mes"],
            y=monthly["receita"],
            mode="lines+markers",
            name="Faturamento",
            line={
                "color": COLORS["blue"],
                "width": 3,
                "shape": "spline",
                "smoothing": 0.8,
            },
            marker={
                "size": 7,
                "color": THEME["surface"],
                "line": {"color": COLORS["blue"], "width": 2},
            },
            fill="tozeroy",
            fillcolor="rgba(39,131,222,0.10)",
            hovertemplate="%{x|%b/%Y}<br>Faturamento: R$ %{y:,.2f}<extra></extra>",
        )
    )
    line.update_layout(title="Evolução mensal do faturamento")
    style_figure(line, 390)
    st.plotly_chart(
        line,
        width="stretch",
        config={
            "displaylogo": False,
            "scrollZoom": True,
            "modeBarButtonsToRemove": ["lasso2d"],
        },
    )

    left, right = st.columns(2)
    brand = (
        filtered.groupby("marca", as_index=False)["valor_venda"]
        .sum()
        .nlargest(10, "valor_venda")
        .sort_values("valor_venda")
    )
    brand_chart = px.bar(
        brand,
        x="valor_venda",
        y="marca",
        orientation="h",
        title="Faturamento por marca",
        labels={"valor_venda": "Faturamento", "marca": ""},
        color_discrete_sequence=[COLORS["blue"]],
    )
    brand_chart.update_traces(
        marker_cornerradius=5, hovertemplate="%{y}<br>R$ %{x:,.2f}<extra></extra>"
    )
    style_figure(brand_chart)
    left.plotly_chart(brand_chart, width="stretch", config={"displaylogo": False})

    store = (
        filtered.groupby("loja", as_index=False)
        .agg(vendas=("venda_id", "count"), receita=("valor_venda", "sum"))
        .sort_values("receita", ascending=True)
    )
    store_chart = px.bar(
        store,
        x="receita",
        y="loja",
        orientation="h",
        title="Desempenho por loja",
        labels={"receita": "Faturamento", "loja": ""},
        color="receita",
        color_continuous_scale=[[0, "#CFE4FA"], [1, COLORS["blue"]]],
    )
    store_chart.update_layout(coloraxis_showscale=False)
    store_chart.update_traces(
        marker_cornerradius=5, hovertemplate="%{y}<br>R$ %{x:,.2f}<extra></extra>"
    )
    style_figure(store_chart)
    right.plotly_chart(store_chart, width="stretch", config={"displaylogo": False})

    left, right = st.columns(2)
    channels = (
        filtered["canal_origem"].fillna("Não informado").value_counts().reset_index()
    )
    channels.columns = ["canal", "vendas"]
    channel_chart = px.pie(
        channels,
        names="canal",
        values="vendas",
        hole=0.68,
        title="Vendas por canal",
        color_discrete_sequence=PALETTE,
    )
    channel_chart.update_traces(
        textposition="inside",
        textinfo="percent",
        hovertemplate="%{label}<br>%{value:,} vendas (%{percent})<extra></extra>",
    )
    style_figure(channel_chart)
    channel_chart.update_layout(
        margin={"l": 18, "r": 145, "t": 48, "b": 20},
        legend={
            "orientation": "v",
            "yanchor": "middle",
            "y": 0.5,
            "xanchor": "left",
            "x": 1.02,
            "font": {"size": 12},
        },
    )
    left.plotly_chart(channel_chart, width="stretch", config={"displaylogo": False})

    payments = (
        filtered["forma_pagamento"].fillna("Não informado").value_counts().reset_index()
    )
    payments.columns = ["forma", "vendas"]
    payment_chart = px.bar(
        payments.sort_values("vendas"),
        x="vendas",
        y="forma",
        orientation="h",
        title="Formas de pagamento",
        labels={"vendas": "Vendas", "forma": ""},
        color_discrete_sequence=[COLORS["green"]],
    )
    payment_chart.update_traces(marker_cornerradius=5)
    style_figure(payment_chart)
    right.plotly_chart(payment_chart, width="stretch", config={"displaylogo": False})

with quality_tab:
    st.markdown(
        f'<div class="quality-note"><b>{integer(counts["valid"])}</b> de '
        f"<b>{integer(counts['received'])}</b> registros foram aprovados; "
        f"<b>{integer(counts['rejected'])}</b> foram enviados para quarentena.</div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="section-title">Resultado das validações</div>',
        unsafe_allow_html=True,
    )
    quality_display = quality.rename(
        columns={
            "check": "Regra",
            "severity": "Severidade",
            "failed_rows": "Registros afetados",
            "status": "Status",
        }
    ).copy()
    quality_display["Severidade"] = quality_display["Severidade"].replace(
        {"error": "Erro", "warning": "Aviso"}
    )
    quality_display["Status"] = quality_display["Status"].replace(
        {"passed": "Aprovada", "failed": "Falhou", "warning": "Aviso"}
    )
    st.dataframe(quality_display, width="stretch", hide_index=True)

    quality_chart_data = quality_display[
        quality_display["Registros afetados"] > 0
    ].sort_values("Registros afetados")
    quality_chart = px.bar(
        quality_chart_data,
        x="Registros afetados",
        y="Regra",
        orientation="h",
        color="Severidade",
        color_discrete_map={"Erro": COLORS["red"], "Aviso": COLORS["orange"]},
        title="Ocorrências por regra de qualidade",
        labels={"Registros afetados": "Registros", "Regra": ""},
    )
    quality_chart.update_traces(marker_cornerradius=5)
    style_figure(quality_chart, 470)
    st.plotly_chart(quality_chart, width="stretch", config={"displaylogo": False})

with traceability_tab:
    st.markdown(f"**{integer(len(filtered))} registros rastreáveis após os filtros**")
    traceability_columns = [
        "venda_id",
        "data_venda",
        "__source_file",
        "__source_line",
        "quality_issues",
        "marca",
        "modelo",
        "loja",
        "uf",
        "consultor",
        "valor_referencia",
        "valor_venda",
        "desconto_percentual",
    ]
    traceability = (
        filtered[traceability_columns]
        .sort_values("data_venda", ascending=False)
        .rename(
            columns={
                "venda_id": "Venda",
                "data_venda": "Data",
                "__source_file": "Arquivo de origem",
                "__source_line": "Linha de origem",
                "quality_issues": "Alertas de qualidade",
                "marca": "Marca",
                "modelo": "Modelo",
                "loja": "Loja",
                "uf": "UF",
                "consultor": "Consultor",
                "valor_referencia": "Valor de referência",
                "valor_venda": "Valor da venda",
                "desconto_percentual": "Desconto (%)",
            }
        )
    )
    st.dataframe(
        traceability,
        width="stretch",
        hide_index=True,
        height=520,
    )

    export_columns = [
        "venda_id",
        "data_venda",
        "marca",
        "modelo",
        "loja",
        "uf",
        "consultor",
        "canal_origem",
        "forma_pagamento",
        "valor_referencia",
        "valor_venda",
        "desconto_percentual",
        "quality_issues",
        "__source_file",
        "__source_line",
    ]
    csv_bytes = (
        filtered[export_columns].to_csv(index=False, sep=";").encode("utf-8-sig")
    )
    st.download_button(
        "Baixar dados filtrados em CSV",
        data=csv_bytes,
        file_name="vendas_filtradas.csv",
        mime="text/csv",
        width="content",
    )

st.caption("Fonte: sales_pipeline.duckdb • Atualização após cada execução do pipeline")
