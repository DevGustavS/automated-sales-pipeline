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
QUALITY_RULE_LABELS = {
    "duplicate_consultor_id": "Consultor duplicado",
    "duplicate_loja_id": "Loja duplicada",
    "duplicate_veiculo_id": "Veículo duplicado",
    "missing_venda_id": "Identificador da venda ausente",
    "duplicate_venda_id": "Venda duplicada",
    "invalid_data_venda": "Data de venda inválida",
    "future_data_venda": "Data de venda futura",
    "invalid_valor_venda": "Valor de venda inválido",
    "negative_valor_venda": "Valor de venda negativo",
    "zero_valor_venda": "Valor de venda igual a zero",
    "suspicious_valor_venda_placeholder": "Valor de venda suspeito (9.999.999)",
    "invalid_valor_referencia": "Valor de referência inválido",
    "missing_veiculo_id": "Identificador do veículo ausente",
    "orphan_veiculo_id": "Veículo sem correspondência",
    "missing_loja_id": "Identificador da loja ausente",
    "orphan_loja_id": "Loja sem correspondência",
    "missing_consultor_id": "Identificador do consultor ausente",
    "orphan_consultor_id": "Consultor sem correspondência",
    "consultor_loja_mismatch": "Consultor vinculado a outra loja",
    "veiculo_multiple_sales": "Veículo associado a múltiplas vendas",
}
TRACEABILITY_SEARCH_COLUMNS = (
    "venda_id",
    "consultor",
    "loja",
    "modelo",
    "marca",
    "__source_file",
)
TRACEABILITY_SORT_OPTIONS = {
    "Data mais recente": ("data_venda", False),
    "Data mais antiga": ("data_venda", True),
    "Maior valor de venda": ("valor_venda", False),
    "Menor valor de venda": ("valor_venda", True),
}

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
        "control_hover_bg": "#F0F3F6",
        "control_selected_bg": "#E5F2FC",
        "disabled_bg": "#F1F2F4",
        "disabled_text": "#A4A19B",
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
        "control_hover_bg": "#21262D",
        "control_selected_bg": "#1B3148",
        "disabled_bg": "#1C2128",
        "disabled_text": "#6E7681",
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
    html, body, .stApp {{
        background: {THEME["app"]};
        color: {THEME["text"]};
        color-scheme: {"dark" if dark_mode else "light"};
        --background-color: {THEME["app"]};
        --secondary-background-color: {THEME["surface"]};
        --text-color: {THEME["text"]};
        --primary-color: {COLORS["blue"]};
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
    [data-testid="stWidgetLabel"] p,
    [data-testid="stWidgetLabel"] label {{ color: {THEME["muted"]}; }}
    [data-testid="stTextInputRootElement"],
    [data-testid="stSelectbox"] [data-baseweb="select"] > div,
    [data-testid="stMultiSelect"] [data-baseweb="select"] > div,
    [data-testid="stSidebar"] [data-baseweb="input"] > div,
    [data-testid="stMultiSelect"] [role="group"],
    [data-testid="stDateInputField"] {{
        background-color: {THEME["surface"]} !important;
        color: {THEME["text"]};
        border-color: {THEME["border"]} !important;
    }}
    [data-testid="stTextInput"] input,
    [data-testid="stSelectbox"] input,
    [data-testid="stMultiSelect"] input {{
        background-color: {THEME["surface"]} !important;
    }}
    [data-testid="stSelectbox"] div:has(> input[role="combobox"]),
    [data-testid="stMultiSelect"] div:has(> input[role="combobox"]),
    [data-testid="stSelectbox"] button[aria-label="Open"],
    [data-testid="stMultiSelect"] button[aria-label="Open"] {{
        background-color: {THEME["surface"]} !important;
        border-color: {THEME["border"]} !important;
    }}
    [data-testid="stTextInput"] input,
    [data-testid="stSelectbox"] input,
    [data-testid="stMultiSelect"] input,
    [data-testid="stDateInputField"] [role="spinbutton"] {{
        color: {THEME["text"]};
        caret-color: {THEME["text"]};
    }}
    [data-testid="stTextInput"] input::placeholder,
    [data-testid="stSelectbox"] input::placeholder,
    [data-testid="stMultiSelect"] input::placeholder {{
        color: {THEME["muted"]};
        opacity: 1;
    }}
    [data-testid="stSelectbox"] svg,
    [data-testid="stMultiSelect"] svg,
    [data-testid="stDateInputField"] svg,
    [data-testid="stSidebar"] button svg {{
        color: {THEME["muted"]};
        fill: currentColor;
    }}
    [data-testid="stSelectboxVirtualDropdown"],
    [data-testid="stMultiSelectDropdown"],
    [data-testid="stDateInputCalendar"],
    [data-testid="stDateInputHeaderPickerPopover"],
    [data-testid="stDateInputQuickSelectPopover"] {{
        background: {THEME["surface"]} !important;
        color: {THEME["text"]};
        border-color: {THEME["border"]} !important;
        box-shadow: 0 8px 24px {THEME["shadow"]};
    }}
    [data-testid="stSelectboxVirtualDropdown"] *,
    [data-testid="stMultiSelectDropdown"] *,
    [data-testid="stDateInputCalendar"] *,
    [data-testid="stDateInputHeaderPickerPopover"] *,
    [data-testid="stDateInputQuickSelectPopover"] * {{
        color: {THEME["text"]} !important;
    }}
    [data-testid="stSelectboxVirtualDropdown"] [role="option"],
    [data-testid="stMultiSelectDropdown"] [role="option"] {{
        color: {THEME["text"]} !important;
    }}
    [data-testid="stSelectboxVirtualDropdown"] [role="option"]:hover,
    [data-testid="stMultiSelectDropdown"] [role="option"]:hover {{
        background: {THEME["control_hover_bg"]} !important;
    }}
    [data-testid="stSelectboxVirtualDropdown"] [role="option"][aria-selected="true"],
    [data-testid="stMultiSelectDropdown"] [role="option"][aria-selected="true"] {{
        background: {THEME["control_selected_bg"]} !important;
    }}
    [data-testid="stDateInputCalendar"] button,
    [data-testid="stDateInputQuickSelect"] {{
        color: {THEME["text"]};
    }}
    [data-testid="stDateInputCalendar"] [role="gridcell"][aria-selected="true"] {{
        background: {THEME["control_selected_bg"]};
    }}
    [data-testid="stDateInputCalendar"] button:disabled {{
        color: {THEME["disabled_text"]} !important;
    }}
    [data-testid="stDateInputQuickSelectPopover"] [role="option"]:hover {{
        background: {THEME["control_hover_bg"]} !important;
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
    [data-testid="stTab"]:hover {{
        background: {THEME["control_hover_bg"]};
        color: {THEME["text"]};
    }}
    [data-testid="stTab"][aria-selected="true"] {{ color: {COLORS["blue"]}; }}
    [data-testid="stTab"]:focus-visible {{
        outline: 2px solid {COLORS["blue"]};
        outline-offset: 2px;
    }}
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
        --gdg-link-color: {COLORS["blue"]} !important;
    }}
    [data-testid="stDataFrame"] canvas {{
        filter: {THEME["dataframe_filter"]};
    }}
    [data-testid="stButton"] button,
    [data-testid="stDownloadButton"] button {{
        background-color: {THEME["surface"]} !important;
        color: {THEME["text"]} !important;
        border: 1px solid {THEME["border"]} !important;
    }}
    [data-testid="stButton"] button p,
    [data-testid="stDownloadButton"] button p {{ color: inherit; }}
    [data-testid="stButton"] button:hover,
    [data-testid="stDownloadButton"] button:hover {{
        background-color: {THEME["control_hover_bg"]} !important;
        color: {COLORS["blue"]} !important;
        border-color: {COLORS["blue"]} !important;
    }}
    [data-testid="stButton"] button:active,
    [data-testid="stDownloadButton"] button:active {{
        background-color: {THEME["control_selected_bg"]} !important;
    }}
    [data-testid="stButton"] button:focus-visible,
    [data-testid="stDownloadButton"] button:focus-visible {{
        outline: 2px solid {COLORS["blue"]};
        outline-offset: 2px;
    }}
    [data-testid="stButton"] button:disabled,
    [data-testid="stDownloadButton"] button:disabled {{
        background-color: {THEME["disabled_bg"]} !important;
        color: {THEME["disabled_text"]} !important;
        border-color: {THEME["border"]} !important;
    }}
    [data-testid="stPlotlyChart"] .modebar-btn path {{
        fill: {THEME["muted"]} !important;
    }}
    [data-testid="stPlotlyChart"] .modebar-btn:hover path {{
        fill: {THEME["text"]} !important;
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


def percentage(numerator: float, denominator: float) -> str:
    if denominator == 0:
        return "0,00%"
    return f"{numerator / denominator * 100:.2f}%".replace(".", ",")


def friendly_quality_rule(rule: str) -> str:
    rule_id = str(rule).strip()
    return QUALITY_RULE_LABELS.get(rule_id, rule_id.replace("_", " ").strip().title())


def quality_alert_mask(frame: pd.DataFrame) -> pd.Series:
    return frame["quality_issues"].astype("string").fillna("").str.strip().ne("")


def search_traceability(frame: pd.DataFrame, query: str) -> pd.DataFrame:
    normalized_query = query.strip()
    if not normalized_query:
        return frame

    matches = pd.DataFrame(
        {
            column: frame[column]
            .astype("string")
            .str.contains(
                normalized_query,
                case=False,
                na=False,
                regex=False,
            )
            for column in TRACEABILITY_SEARCH_COLUMNS
        },
        index=frame.index,
    ).any(axis=1)
    return frame.loc[matches]


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
            "font": {"color": THEME["text"]},
            "title": {"font": {"color": THEME["muted"]}},
        },
        xaxis={
            "showgrid": False,
            "linecolor": THEME["border"],
            "tickfont": {"color": THEME["muted"]},
            "title_font": {"color": THEME["muted"]},
        },
        yaxis={
            "gridcolor": THEME["grid"],
            "griddash": "dot",
            "zeroline": False,
            "tickfont": {"color": THEME["muted"]},
            "title_font": {"color": THEME["muted"]},
        },
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
            "font": {"size": 12, "color": THEME["text"]},
            "title": {"font": {"color": THEME["muted"]}},
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
        '<div class="dashboard-title">Qualidade dos dados</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="dashboard-subtitle">Visão das validações executadas pelo '
        "pipeline e dos registros afetados por problemas de qualidade.</div>",
        unsafe_allow_html=True,
    )

    approval_rate = percentage(counts["valid"], counts["received"])
    volume_kpis = "".join(
        [
            kpi_card("Recebidos", integer(counts["received"])),
            kpi_card("Válidos", integer(counts["valid"])),
            kpi_card("Rejeitados", integer(counts["rejected"])),
            kpi_card("Taxa de aprovação", approval_rate),
        ]
    )
    st.markdown(
        f'<div class="kpi-grid quality-volume-kpis">{volume_kpis}</div>',
        unsafe_allow_html=True,
    )

    rules_executed = len(quality)
    rules_passed = int(quality["status"].eq("passed").sum())
    rules_failed = int(quality["status"].eq("failed").sum())
    rules_warning = int(quality["status"].eq("warning").sum())
    rules_kpis = "".join(
        [
            kpi_card("Regras executadas", integer(rules_executed)),
            kpi_card("Aprovadas", integer(rules_passed)),
            kpi_card("Falhas", integer(rules_failed)),
            kpi_card("Avisos", integer(rules_warning)),
        ]
    )
    st.markdown(
        f'<div class="kpi-grid quality-rules-kpis">{rules_kpis}</div>',
        unsafe_allow_html=True,
    )

    st.markdown(
        f'<div class="quality-note"><b>{integer(counts["valid"])}</b> de '
        f"<b>{integer(counts['received'])}</b> registros foram aprovados; "
        f"<b>{integer(counts['rejected'])}</b> foram enviados para quarentena.</div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="section-title">Principais problemas encontrados</div>',
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
    quality_display["Regra"] = quality_display["Regra"].map(friendly_quality_rule)
    quality_display["Severidade"] = quality_display["Severidade"].replace(
        {"error": "Erro", "warning": "Aviso"}
    )
    quality_display["Status"] = quality_display["Status"].replace(
        {"passed": "Aprovada", "failed": "Falhou", "warning": "Aviso"}
    )

    quality_chart_data = quality_display[
        quality_display["Registros afetados"] > 0
    ].sort_values("Registros afetados")
    if quality_chart_data.empty:
        st.info("Nenhuma ocorrência de qualidade foi registrada nesta execução.")
    else:
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
        quality_chart.update_traces(
            marker_cornerradius=5,
            hovertemplate="%{y}<br>%{x:,} registros<extra></extra>",
        )
        style_figure(quality_chart, 470)
        st.plotly_chart(
            quality_chart,
            width="stretch",
            config={"displaylogo": False},
        )

    st.markdown(
        '<div class="section-title">Detalhamento das validações</div>',
        unsafe_allow_html=True,
    )
    st.caption(
        "Erro identifica uma falha crítica: regras de venda podem enviar registros "
        "à quarentena, enquanto duplicidades em dimensões preservam a primeira "
        "ocorrência. Aviso mantém a venda válida e sinaliza necessidade de análise."
    )

    severity_column, status_column = st.columns(2)
    with severity_column:
        selected_quality_severity = st.selectbox(
            "Severidade",
            ["Todas", "Erro", "Aviso"],
            key="quality_severity_filter",
        )
    with status_column:
        selected_quality_status = st.selectbox(
            "Status",
            ["Todos", "Aprovada", "Falhou", "Aviso"],
            key="quality_status_filter",
        )

    filtered_quality_display = quality_display.copy()
    if selected_quality_severity != "Todas":
        filtered_quality_display = filtered_quality_display[
            filtered_quality_display["Severidade"].eq(selected_quality_severity)
        ]
    if selected_quality_status != "Todos":
        filtered_quality_display = filtered_quality_display[
            filtered_quality_display["Status"].eq(selected_quality_status)
        ]

    if filtered_quality_display.empty:
        st.info("Nenhuma regra corresponde aos filtros locais selecionados.")

    st.dataframe(
        filtered_quality_display,
        width="stretch",
        hide_index=True,
        column_config={
            "Regra": st.column_config.TextColumn("Regra", width="large"),
            "Severidade": st.column_config.TextColumn("Severidade"),
            "Registros afetados": st.column_config.NumberColumn(
                "Registros afetados", format="%d"
            ),
            "Status": st.column_config.TextColumn("Status"),
        },
    )

    quality_csv_bytes = filtered_quality_display.to_csv(index=False, sep=";").encode(
        "utf-8-sig"
    )
    st.download_button(
        "Baixar relatório de qualidade",
        data=quality_csv_bytes,
        file_name="relatorio_qualidade.csv",
        mime="text/csv",
        width="content",
    )

with traceability_tab:
    st.markdown(
        '<div class="dashboard-title">Rastreabilidade</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="dashboard-subtitle">Investigue as vendas válidas e acompanhe '
        "sua origem desde o arquivo de entrada.</div>",
        unsafe_allow_html=True,
    )

    filtered_alert_mask = quality_alert_mask(filtered)
    traceability_kpis = "".join(
        [
            kpi_card("Registros rastreáveis", integer(len(filtered))),
            kpi_card("Registros com alertas", integer(filtered_alert_mask.sum())),
        ]
    )
    st.markdown(
        f'<div class="kpi-grid traceability-kpis">{traceability_kpis}</div>',
        unsafe_allow_html=True,
    )

    st.markdown(
        '<div class="section-title">Busca e investigação</div>',
        unsafe_allow_html=True,
    )
    traceability_query = st.text_input(
        "Buscar venda, consultor, loja ou modelo",
        key="traceability_search",
        placeholder="Digite um ID, nome, loja, modelo, marca ou arquivo",
    )
    quality_filter_column, sort_column = st.columns(2)
    with quality_filter_column:
        traceability_quality_filter = st.selectbox(
            "Qualidade",
            ["Todos", "Com alerta", "Sem alerta"],
            key="traceability_quality_filter",
        )
    with sort_column:
        traceability_sort = st.selectbox(
            "Ordenar por",
            list(TRACEABILITY_SORT_OPTIONS),
            key="traceability_sort",
        )

    investigated = search_traceability(filtered.copy(), traceability_query)
    investigated_alert_mask = quality_alert_mask(investigated)
    if traceability_quality_filter == "Com alerta":
        investigated = investigated.loc[investigated_alert_mask]
    elif traceability_quality_filter == "Sem alerta":
        investigated = investigated.loc[~investigated_alert_mask]

    sort_column_name, sort_ascending = TRACEABILITY_SORT_OPTIONS[traceability_sort]
    investigated = investigated.sort_values(
        sort_column_name,
        ascending=sort_ascending,
        kind="stable",
    )

    investigated_count = len(investigated)
    investigated_label = (
        "registro rastreável" if investigated_count == 1 else "registros rastreáveis"
    )
    st.markdown(f"**{integer(investigated_count)} {investigated_label}**")
    if investigated.empty:
        st.info("Nenhuma venda corresponde aos critérios de investigação.")

    st.markdown(
        '<div class="section-title">Registros</div>',
        unsafe_allow_html=True,
    )
    st.caption(
        "Cada venda preserva o arquivo e a linha de origem, permitindo rastrear o "
        "registro desde a ingestão até a camada analítica."
    )

    traceability_columns = [
        "venda_id",
        "data_venda",
        "quality_issues",
        "marca",
        "modelo",
        "loja",
        "uf",
        "consultor",
        "valor_venda",
        "valor_referencia",
        "desconto_percentual",
        "__source_file",
        "__source_line",
    ]
    traceability = investigated[traceability_columns].rename(
        columns={
            "venda_id": "Venda",
            "data_venda": "Data",
            "quality_issues": "Alertas de qualidade",
            "marca": "Marca",
            "modelo": "Modelo",
            "loja": "Loja",
            "uf": "UF",
            "consultor": "Consultor",
            "valor_referencia": "Valor de referência",
            "valor_venda": "Valor da venda",
            "desconto_percentual": "Desconto (%)",
            "__source_file": "Arquivo de origem",
            "__source_line": "Linha de origem",
        }
    )
    traceability["Alertas de qualidade"] = traceability["Alertas de qualidade"].where(
        quality_alert_mask(investigated), "Sem alertas"
    )
    st.dataframe(
        traceability,
        width="stretch",
        hide_index=True,
        height=520,
        column_config={
            "Venda": st.column_config.TextColumn("Venda"),
            "Data": st.column_config.DatetimeColumn("Data", format="DD/MM/YYYY"),
            "Alertas de qualidade": st.column_config.TextColumn(
                "Alertas de qualidade", width="large"
            ),
            "Valor da venda": st.column_config.NumberColumn(
                "Valor da venda", format="R$ %.2f"
            ),
            "Valor de referência": st.column_config.NumberColumn(
                "Valor de referência", format="R$ %.2f"
            ),
            "Desconto (%)": st.column_config.NumberColumn(
                "Desconto (%)", format="%.2f%%"
            ),
            "Arquivo de origem": st.column_config.TextColumn(
                "Arquivo de origem", width="large"
            ),
            "Linha de origem": st.column_config.NumberColumn(
                "Linha de origem", format="%d"
            ),
        },
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
    investigated_csv_bytes = (
        investigated[export_columns].to_csv(index=False, sep=";").encode("utf-8-sig")
    )
    st.download_button(
        "Baixar dados investigados",
        data=investigated_csv_bytes,
        file_name="vendas_investigadas.csv",
        mime="text/csv",
        width="content",
    )

st.caption("Fonte: sales_pipeline.duckdb • Atualização após cada execução do pipeline")
