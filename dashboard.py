from __future__ import annotations

import os
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
    "text": "#2C2C2B",
    "muted": "#7D7A75",
    "border": "#E6E5E3",
    "surface": "#FFFFFF",
}
PALETTE = ["#5E9FE8", "#EAC26B", "#72BC8F", "#BF8EDA", "#DE9255", "#DF84A8"]

st.set_page_config(
    page_title="Sales Performance",
    page_icon="🚘",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    .stApp { background: #F7F8FA; color: #2C2C2B; }
    .block-container {
        max-width: 1440px;
        padding-top: 4.25rem !important;
        padding-bottom: 3rem;
    }
    [data-testid="stSidebar"] { background: #FFFFFF; border-right: 1px solid #E6E5E3; }
    .kpi-grid {
        display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
        gap: 12px; margin: 0 0 18px;
    }
    .kpi-card {
        min-width: 0; background: #FFFFFF; border: 1px solid #E6E5E3;
        border-radius: 12px; padding: 17px 18px;
        box-shadow: 0 1px 2px rgba(0,0,0,.03);
    }
    .kpi-label {
        color: #7D7A75; font-size: .78rem; font-weight: 700;
        letter-spacing: .01em; margin-bottom: 7px;
    }
    .kpi-value {
        color: #2C2C2B; font-size: clamp(1.25rem, 1.75vw, 1.65rem);
        line-height: 1.15; font-weight: 760; white-space: nowrap;
    }
    .kpi-value.positive { color: #46A171; }
    [data-testid="stPlotlyChart"] {
        background: #FFFFFF; border: 1px solid #E6E5E3; border-radius: 12px;
        padding: 8px; box-shadow: 0 1px 2px rgba(0,0,0,.03);
    }
    .dashboard-kicker {
        display: block; min-height: 24px; padding-top: 2px;
        color: #2783DE; font-size: .82rem; line-height: 1.45;
        font-weight: 750; letter-spacing: .08em; text-transform: uppercase;
    }
    .dashboard-title { font-size: 2rem; font-weight: 760; margin: .2rem 0 0; color: #2C2C2B; }
    .dashboard-subtitle { color: #7D7A75; margin: .35rem 0 1.4rem; }
    .section-title { font-size: 1.05rem; font-weight: 700; margin: 1.25rem 0 .65rem; color: #2C2C2B; }
    .quality-note { background: #E8F1EC; color: #2E6849; border: 1px solid #CDE3D6; border-radius: 10px; padding: 12px 14px; }
    div[data-baseweb="tab-list"] { gap: 10px; }
    button[data-baseweb="tab"] { border-radius: 8px; padding-left: 16px; padding-right: 16px; }
    @media (max-width: 760px) {
        .block-container { padding-left: 1rem; padding-right: 1rem; }
        .kpi-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
        .kpi-value { font-size: 1.2rem; }
    }
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


def kpi_card(label: str, value: str, positive: bool = False) -> str:
    value_class = "kpi-value positive" if positive else "kpi-value"
    return (
        '<div class="kpi-card">'
        f'<div class="kpi-label">{label}</div>'
        f'<div class="{value_class}">{value}</div>'
        "</div>"
    )


def integer(value: float) -> str:
    return f"{int(value):,}".replace(",", ".")


def style_figure(fig: go.Figure, height: int = 360) -> go.Figure:
    fig.update_layout(
        height=height,
        margin={"l": 22, "r": 22, "t": 48, "b": 24},
        paper_bgcolor="#FFFFFF",
        plot_bgcolor="#FFFFFF",
        font={"family": "Arial, sans-serif", "color": COLORS["text"], "size": 13},
        title_font={"size": 16, "color": COLORS["text"]},
        hoverlabel={"bgcolor": "#202020", "font_color": "#FFFFFF"},
        legend={
            "orientation": "h",
            "yanchor": "bottom",
            "y": 1.02,
            "xanchor": "right",
            "x": 1,
        },
        xaxis={"showgrid": False, "linecolor": COLORS["border"]},
        yaxis={"gridcolor": "#EFEFED", "griddash": "dot", "zeroline": False},
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
                desconto_percentual, marca, modelo, loja, uf,
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
date_range = st.sidebar.date_input(
    "Período",
    value=(minimum_date, maximum_date),
    min_value=minimum_date,
    max_value=maximum_date,
)

brands = sorted(sales["marca"].dropna().unique().tolist())
stores = sorted(sales["loja"].dropna().unique().tolist())
states = sorted(sales["uf"].dropna().unique().tolist())
selected_brands = st.sidebar.multiselect("Marcas", brands)
selected_stores = st.sidebar.multiselect("Lojas", stores)
selected_states = st.sidebar.multiselect("UF", states)

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

st.markdown(
    '<div class="dashboard-kicker">Automated Sales Pipeline</div>',
    unsafe_allow_html=True,
)
st.markdown(
    '<div class="dashboard-title">Sales performance</div>', unsafe_allow_html=True
)
st.markdown(
    '<div class="dashboard-subtitle">Visão consolidada das vendas válidas, com filtros interativos e rastreabilidade.</div>',
    unsafe_allow_html=True,
)

if filtered.empty:
    st.warning("Nenhum registro corresponde aos filtros selecionados.")
    st.stop()

revenue = float(filtered["valor_venda"].sum())
sales_count = len(filtered)
average_ticket = float(filtered["valor_venda"].mean())
average_discount = float(filtered["desconto_percentual"].mean())
quality_rate = counts["valid"] / counts["received"] * 100 if counts["received"] else 0

kpis = "".join(
    [
        kpi_card("Faturamento", compact_brl(revenue)),
        kpi_card("Vendas", integer(sales_count)),
        kpi_card("Ticket médio", compact_brl(average_ticket)),
        kpi_card("Desconto médio", f"{average_discount:.1f}%"),
        kpi_card("Aprovação de qualidade", f"{quality_rate:.2f}%", positive=True),
    ]
)
st.markdown(f'<div class="kpi-grid">{kpis}</div>', unsafe_allow_html=True)

executive_tab, quality_tab, data_tab = st.tabs(
    ["Visão executiva", "Qualidade", "Dados"]
)

with executive_tab:
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
                "color": "#FFFFFF",
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
    st.dataframe(quality, width="stretch", hide_index=True)

    quality_chart_data = quality[quality["failed_rows"] > 0].sort_values("failed_rows")
    quality_chart = px.bar(
        quality_chart_data,
        x="failed_rows",
        y="check",
        orientation="h",
        color="severity",
        color_discrete_map={"error": COLORS["red"], "warning": COLORS["orange"]},
        title="Ocorrências por regra de qualidade",
        labels={"failed_rows": "Registros", "check": "", "severity": "Severidade"},
    )
    quality_chart.update_traces(marker_cornerradius=5)
    style_figure(quality_chart, 470)
    st.plotly_chart(quality_chart, width="stretch", config={"displaylogo": False})

with data_tab:
    st.markdown(f"**{integer(len(filtered))} registros após os filtros**")
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
        "__source_file",
        "__source_line",
    ]
    st.dataframe(
        filtered[export_columns].sort_values("data_venda", ascending=False),
        width="stretch",
        hide_index=True,
        height=520,
    )
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
