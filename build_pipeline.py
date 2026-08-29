from __future__ import annotations

import argparse
import json
import os
import tempfile
import uuid
from decimal import Decimal, InvalidOperation
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

import pipeline

NULL_VALUES = {"", "na", "n/a", "null", "none", "nan", "-"}
MONEY_QUANTUM = Decimal("0.01")
FIRST_SOURCE_OCCURRENCE = "first"
TABLE_DECIMAL_COLUMNS = {
    "fact_vendas": {
        "valor_referencia": "DECIMAL(18,2)",
        "valor_venda": "DECIMAL(18,2)",
        "desconto_valor": "DECIMAL(18,2)",
        "desconto_percentual": "DECIMAL(9,4)",
    },
    "rejected_sales": {
        "valor_referencia": "DECIMAL(18,2)",
        "valor_venda": "DECIMAL(18,2)",
    },
}
QUALITY_RULES: tuple[dict[str, object], ...] = (
    {
        "rule_id": "duplicate_consultor_id",
        "description": "Identificador de consultor duplicado na dimensão.",
        "severity": "error",
        "dataset": "consultores",
        "condition": (
            "consultor_id aparece mais de uma vez; todas as ocorrências são contadas"
        ),
        "treatment": "keep_first_source_occurrence",
        "reason": (
            "A primeira ocorrência na ordem consolidada é canônica; as demais não "
            "entram na dimensão, evitando multiplicidade no relacionamento com vendas."
        ),
        "invalidates_sale": False,
    },
    {
        "rule_id": "duplicate_loja_id",
        "description": "Identificador de loja duplicado na dimensão.",
        "severity": "error",
        "dataset": "lojas",
        "condition": "loja_id aparece mais de uma vez; todas as ocorrências são contadas",
        "treatment": "keep_first_source_occurrence",
        "reason": (
            "A primeira ocorrência na ordem consolidada é canônica; as demais não "
            "entram na dimensão, evitando multiplicidade no relacionamento com vendas."
        ),
        "invalidates_sale": False,
    },
    {
        "rule_id": "duplicate_veiculo_id",
        "description": "Identificador de veículo duplicado na dimensão.",
        "severity": "error",
        "dataset": "veiculos",
        "condition": (
            "veiculo_id aparece mais de uma vez; todas as ocorrências são contadas"
        ),
        "treatment": "keep_first_source_occurrence",
        "reason": (
            "A primeira ocorrência na ordem consolidada é canônica; as demais não "
            "entram na dimensão, evitando multiplicidade no relacionamento com vendas."
        ),
        "invalidates_sale": False,
    },
    {
        "rule_id": "missing_venda_id",
        "description": "Venda sem identificador.",
        "severity": "error",
        "dataset": "vendas",
        "condition": "venda_id está ausente",
        "treatment": "reject_sale",
        "reason": "A venda não pode ser identificada de forma única.",
        "invalidates_sale": True,
    },
    {
        "rule_id": "duplicate_venda_id",
        "description": "Identificador de venda repetido.",
        "severity": "error",
        "dataset": "vendas",
        "condition": "venda_id repete uma ocorrência anterior na ordem consolidada",
        "treatment": "keep_first_and_reject_later_source_occurrences",
        "reason": (
            "A primeira ocorrência na ordem consolidada é canônica; ocorrências "
            "posteriores são rejeitadas para evitar contagem duplicada."
        ),
        "invalidates_sale": True,
    },
    {
        "rule_id": "invalid_data_venda",
        "description": "Data da venda ausente, inválida ou em formato não aceito.",
        "severity": "error",
        "dataset": "vendas",
        "condition": "data_venda normalizada é nula",
        "treatment": "reject_sale",
        "reason": "A data é necessária para análises temporais.",
        "invalidates_sale": True,
    },
    {
        "rule_id": "future_data_venda",
        "description": "Data da venda posterior ao dia da execução.",
        "severity": "warning",
        "dataset": "vendas",
        "condition": "data_venda é posterior à data atual",
        "treatment": "retain_with_warning",
        "reason": "Pode representar dado antecipado ou erro de origem.",
        "invalidates_sale": False,
    },
    {
        "rule_id": "invalid_valor_venda",
        "description": "Valor da venda ausente ou não monetário.",
        "severity": "error",
        "dataset": "vendas",
        "condition": "valor_venda normalizado é nulo",
        "treatment": "reject_sale",
        "reason": "O valor é necessário para as métricas financeiras.",
        "invalidates_sale": True,
    },
    {
        "rule_id": "negative_valor_venda",
        "description": "Valor da venda negativo.",
        "severity": "error",
        "dataset": "vendas",
        "condition": "valor_venda é menor que zero",
        "treatment": "reject_sale",
        "reason": "Venda negativa exige tratamento de negócio não definido.",
        "invalidates_sale": True,
    },
    {
        "rule_id": "invalid_valor_referencia",
        "description": "Valor de referência ausente ou não monetário.",
        "severity": "warning",
        "dataset": "vendas",
        "condition": "valor_referencia normalizado é nulo",
        "treatment": "retain_with_warning",
        "reason": "A venda é utilizável, mas o desconto não pode ser calculado.",
        "invalidates_sale": False,
    },
    {
        "rule_id": "missing_veiculo_id",
        "description": "Venda sem identificador de veículo.",
        "severity": "error",
        "dataset": "vendas",
        "condition": "veiculo_id está ausente",
        "treatment": "reject_sale",
        "reason": "O veículo é obrigatório para compor a fato.",
        "invalidates_sale": True,
    },
    {
        "rule_id": "orphan_veiculo_id",
        "description": "Veículo da venda não existe na dimensão.",
        "severity": "error",
        "dataset": "vendas",
        "condition": "veiculo_id não está na dimensão de veículos",
        "treatment": "reject_sale",
        "reason": "O relacionamento obrigatório com veículo falharia.",
        "invalidates_sale": True,
    },
    {
        "rule_id": "missing_loja_id",
        "description": "Venda sem identificador de loja.",
        "severity": "error",
        "dataset": "vendas",
        "condition": "loja_id está ausente",
        "treatment": "reject_sale",
        "reason": "A loja é obrigatória para compor a fato.",
        "invalidates_sale": True,
    },
    {
        "rule_id": "orphan_loja_id",
        "description": "Loja da venda não existe na dimensão.",
        "severity": "error",
        "dataset": "vendas",
        "condition": "loja_id não está na dimensão de lojas",
        "treatment": "reject_sale",
        "reason": "O relacionamento obrigatório com loja falharia.",
        "invalidates_sale": True,
    },
    {
        "rule_id": "missing_consultor_id",
        "description": "Venda sem identificador de consultor.",
        "severity": "warning",
        "dataset": "vendas",
        "condition": "consultor_id está ausente",
        "treatment": "retain_with_warning",
        "reason": "A venda permanece útil sem atribuição ao consultor.",
        "invalidates_sale": False,
    },
    {
        "rule_id": "orphan_consultor_id",
        "description": "Consultor da venda não existe na dimensão.",
        "severity": "warning",
        "dataset": "vendas",
        "condition": "consultor_id não está na dimensão de consultores",
        "treatment": "retain_with_warning",
        "reason": "A venda permanece útil, com atribuição não resolvida.",
        "invalidates_sale": False,
    },
    {
        "rule_id": "consultor_loja_mismatch",
        "description": "Consultor pertence a loja diferente da venda.",
        "severity": "warning",
        "dataset": "vendas",
        "condition": "loja da venda difere da loja do consultor",
        "treatment": "retain_with_warning",
        "reason": "Pode ser uma venda cruzada legítima ou erro cadastral.",
        "invalidates_sale": False,
    },
    {
        "rule_id": "veiculo_multiple_sales",
        "description": "Veículo está associado a múltiplas vendas.",
        "severity": "warning",
        "dataset": "vendas",
        "condition": "veiculo_id aparece em mais de uma venda",
        "treatment": "retain_with_warning",
        "reason": "A recorrência requer análise, mas não prova duplicidade.",
        "invalidates_sale": False,
    },
)
QUALITY_RULES_BY_ID = {rule["rule_id"]: rule for rule in QUALITY_RULES}


def quality_report_row(rule_id: str, failed_rows: int) -> dict[str, object]:
    rule = QUALITY_RULES_BY_ID[rule_id]
    severity = str(rule["severity"])
    return {
        "check": rule_id,
        **rule,
        "failed_rows": failed_rows,
        "status": (
            "passed"
            if failed_rows == 0
            else "failed"
            if severity == "error"
            else "warning"
        ),
    }


def clean_text(series: pd.Series) -> pd.Series:
    result = series.astype("string").str.strip()
    return result.mask(result.str.lower().isin(NULL_VALUES))


def clean_id(series: pd.Series) -> pd.Series:
    return clean_text(series).str.upper()


def parse_date(series: pd.Series) -> pd.Series:
    value = clean_text(series)
    parsed = pd.to_datetime(value, errors="coerce", format="%Y-%m-%d")
    for date_format in ("%Y/%m/%d", "%d/%m/%Y"):
        missing = parsed.isna() & value.notna()
        parsed.loc[missing] = pd.to_datetime(
            value.loc[missing], errors="coerce", format=date_format
        )
    return parsed


def normalize_number_text(series: pd.Series) -> pd.Series:
    value = clean_text(series).str.replace("R$", "", regex=False)
    value = value.str.replace(r"\s+", "", regex=True)
    comma = value.str.contains(",", regex=False, na=False)
    dot = value.str.contains(".", regex=False, na=False)
    both = comma & dot
    value.loc[both] = (
        value.loc[both]
        .str.replace(".", "", regex=False)
        .str.replace(",", ".", regex=False)
    )
    value.loc[comma & ~dot] = value.loc[comma & ~dot].str.replace(",", ".", regex=False)
    return value


def parse_number(series: pd.Series) -> pd.Series:
    value = normalize_number_text(series)
    return pd.to_numeric(value, errors="coerce").astype("Float64")


def parse_money(series: pd.Series) -> pd.Series:
    def to_decimal(value: object) -> Decimal | None:
        if pd.isna(value):
            return None
        try:
            decimal_value = Decimal(str(value))
            quantized = decimal_value.quantize(MONEY_QUANTUM)
        except InvalidOperation:
            return None
        if not decimal_value.is_finite() or decimal_value != quantized:
            return None
        return quantized

    return normalize_number_text(series).map(to_decimal).astype("object")


def combine(files: list[object], schema: str) -> pd.DataFrame:
    frames = [item.data.copy() for item in files if item.schema_name == schema]
    if not frames:
        raise RuntimeError(f"Schema não encontrado: {schema}")
    return pd.concat(frames, ignore_index=True)


def normalize(
    vendas: pd.DataFrame,
    consultores: pd.DataFrame,
    lojas: pd.DataFrame,
    veiculos: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    vendas = vendas.copy()
    consultores = consultores.copy()
    lojas = lojas.copy()
    veiculos = veiculos.copy()

    for column in ["venda_id", "veiculo_id", "loja_id", "consultor_id"]:
        vendas[column] = clean_id(vendas[column])

    for column in ["canal_origem", "forma_pagamento"]:
        vendas[column] = clean_text(vendas[column])

    vendas["data_venda_original"] = vendas["data_venda"]
    vendas["valor_referencia_original"] = vendas["valor_referencia"]
    vendas["valor_venda_original"] = vendas["valor_venda"]
    vendas["data_venda"] = parse_date(vendas["data_venda"])
    vendas["valor_referencia"] = parse_money(vendas["valor_referencia"])
    vendas["valor_venda"] = parse_money(vendas["valor_venda"])

    consultores["consultor_id"] = clean_id(consultores["consultor_id"])
    consultores["loja_id"] = clean_id(consultores["loja_id"])
    consultores["consultor"] = clean_text(consultores["consultor"])
    consultores["equipe"] = clean_text(consultores["equipe"])
    consultores["data_admissao"] = parse_date(consultores["data_admissao"])

    lojas["loja_id"] = clean_id(lojas["loja_id"])
    for column in ["loja", "cidade", "uf", "cluster"]:
        lojas[column] = clean_text(lojas[column])
    lojas["uf"] = lojas["uf"].str.upper()

    veiculos["veiculo_id"] = clean_id(veiculos["veiculo_id"])
    for column in [
        "marca",
        "modelo",
        "versao",
        "carroceria",
        "cambio",
        "combustivel",
        "tipo_veiculo",
        "cor_externa",
        "cor_interna",
    ]:
        veiculos[column] = clean_text(veiculos[column])
    for column in ["ano_modelo", "quilometragem", "score_avaliacao"]:
        veiculos[column] = parse_number(veiculos[column])

    return vendas, consultores, lojas, veiculos


def validate(
    vendas: pd.DataFrame,
    consultores: pd.DataFrame,
    lojas: pd.DataFrame,
    veiculos: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    vendas = vendas.copy()
    vendas["quality_issues"] = ""
    vendas["is_valid"] = True
    report: list[dict[str, object]] = []

    # Cada dataset possui colunas de rastreabilidade com os mesmos nomes.
    # Renomeá-las evita colisões durante os joins e preserva a origem.
    # A ingestão ordena arquivos pelo nome e preserva a ordem das linhas. Portanto,
    # "first" é a primeira ocorrência determinística nessa ordem consolidada.
    consultores_dim = consultores.drop_duplicates(
        "consultor_id", keep=FIRST_SOURCE_OCCURRENCE
    ).rename(
        columns={
            "__source_file": "consultor_source_file",
            "__source_line": "consultor_source_line",
        }
    )
    lojas_dim = lojas.drop_duplicates("loja_id", keep=FIRST_SOURCE_OCCURRENCE).rename(
        columns={
            "__source_file": "loja_source_file",
            "__source_line": "loja_source_line",
        }
    )
    veiculos_dim = veiculos.drop_duplicates(
        "veiculo_id", keep=FIRST_SOURCE_OCCURRENCE
    ).rename(
        columns={
            "__source_file": "veiculo_source_file",
            "__source_line": "veiculo_source_line",
        }
    )

    dimension_checks = [
        ("duplicate_consultor_id", consultores["consultor_id"].duplicated(False)),
        ("duplicate_loja_id", lojas["loja_id"].duplicated(False)),
        ("duplicate_veiculo_id", veiculos["veiculo_id"].duplicated(False)),
    ]

    for name, mask in dimension_checks:
        count = int(mask.sum())
        report.append(quality_report_row(name, count))

    vehicle_ids = set(veiculos_dim["veiculo_id"].dropna())
    store_ids = set(lojas_dim["loja_id"].dropna())
    consultant_ids = set(consultores_dim["consultor_id"].dropna())
    consultant_store = consultores_dim.set_index("consultor_id")["loja_id"]
    expected_store = vendas["consultor_id"].map(consultant_store)

    checks = [
        ("missing_venda_id", vendas["venda_id"].isna()),
        (
            "duplicate_venda_id",
            vendas["venda_id"].notna()
            & vendas["venda_id"].duplicated(keep=FIRST_SOURCE_OCCURRENCE),
        ),
        ("invalid_data_venda", vendas["data_venda"].isna()),
        (
            "future_data_venda",
            vendas["data_venda"].notna()
            & vendas["data_venda"].gt(pd.Timestamp.today().normalize()),
        ),
        ("invalid_valor_venda", vendas["valor_venda"].isna()),
        ("negative_valor_venda", vendas["valor_venda"].lt(0)),
        (
            "invalid_valor_referencia",
            vendas["valor_referencia"].isna(),
        ),
        (
            "missing_veiculo_id",
            vendas["veiculo_id"].isna(),
        ),
        (
            "orphan_veiculo_id",
            vendas["veiculo_id"].notna() & ~vendas["veiculo_id"].isin(vehicle_ids),
        ),
        ("missing_loja_id", vendas["loja_id"].isna()),
        (
            "orphan_loja_id",
            vendas["loja_id"].notna() & ~vendas["loja_id"].isin(store_ids),
        ),
        (
            "missing_consultor_id",
            vendas["consultor_id"].isna(),
        ),
        (
            "orphan_consultor_id",
            vendas["consultor_id"].notna()
            & ~vendas["consultor_id"].isin(consultant_ids),
        ),
        (
            "consultor_loja_mismatch",
            vendas["consultor_id"].notna()
            & expected_store.notna()
            & expected_store.ne(vendas["loja_id"]),
        ),
        (
            "veiculo_multiple_sales",
            vendas["veiculo_id"].notna() & vendas["veiculo_id"].duplicated(keep=False),
        ),
    ]

    for name, mask in checks:
        rule = QUALITY_RULES_BY_ID[name]
        mask = mask.fillna(False).astype(bool)
        current = vendas.loc[mask, "quality_issues"]
        vendas.loc[mask, "quality_issues"] = np.where(
            current.eq(""), name, current + "|" + name
        )
        if rule["invalidates_sale"]:
            vendas.loc[mask, "is_valid"] = False
        count = int(mask.sum())
        report.append(quality_report_row(name, count))

    rejeitadas = vendas.loc[~vendas["is_valid"]].copy()
    validas = vendas.loc[vendas["is_valid"]].copy()
    consultores_join = consultores_dim.rename(columns={"loja_id": "consultor_loja_id"})

    fato = (
        validas.merge(veiculos_dim, on="veiculo_id", how="left", validate="many_to_one")
        .merge(lojas_dim, on="loja_id", how="left", validate="many_to_one")
        .merge(
            consultores_join,
            on="consultor_id",
            how="left",
            validate="many_to_one",
        )
    )
    fato["desconto_valor"] = fato["valor_referencia"] - fato["valor_venda"]
    has_reference = fato["valor_referencia"].notna() & fato["valor_referencia"].ne(0)
    fato["desconto_percentual"] = pd.Series(pd.NA, index=fato.index, dtype="Float64")
    fato.loc[has_reference, "desconto_percentual"] = (
        fato.loc[has_reference, "desconto_valor"]
        / fato.loc[has_reference, "valor_referencia"]
        * Decimal(100)
    ).map(float)
    return fato, rejeitadas, pd.DataFrame(report)


def _write_outputs(
    output: Path,
    quarantine: Path,
    raw_vendas: pd.DataFrame,
    fato: pd.DataFrame,
    rejeitadas: pd.DataFrame,
    relatorio: pd.DataFrame,
    consultores: pd.DataFrame,
    lojas: pd.DataFrame,
    veiculos: pd.DataFrame,
) -> None:
    output.mkdir(parents=True, exist_ok=True)
    quarantine.mkdir(parents=True, exist_ok=True)
    relatorio.to_csv(output / "quality_report.csv", index=False, encoding="utf-8-sig")
    rejeitadas.to_csv(
        quarantine / "rejected_sales.csv", index=False, encoding="utf-8-sig"
    )

    connection = duckdb.connect(str(output / "sales_pipeline.duckdb"))
    try:
        tables = {
            "raw_vendas": raw_vendas,
            "dim_consultores": consultores,
            "dim_lojas": lojas,
            "dim_veiculos": veiculos,
            "fact_vendas": fato,
            "rejected_sales": rejeitadas,
            "quality_report": relatorio,
        }
        for table, frame in tables.items():
            decimal_columns = TABLE_DECIMAL_COLUMNS.get(table, {})
            database_frame = frame.copy()
            for column in decimal_columns:
                database_frame[column] = database_frame[column].map(
                    lambda value: str(value) if pd.notna(value) else None
                )
            connection.register("source_frame", database_frame)
            replacements = ", ".join(
                f"CAST({column} AS {data_type}) AS {column}"
                for column, data_type in decimal_columns.items()
            )
            selection = f"* REPLACE ({replacements})" if replacements else "*"
            connection.execute(
                f"CREATE OR REPLACE TABLE {table} AS "
                f"SELECT {selection} FROM source_frame"
            )
            connection.unregister("source_frame")

        connection.execute("""
            CREATE OR REPLACE TABLE mart_vendas_mensal AS
            SELECT
                date_trunc('month', data_venda) AS mes,
                marca,
                loja,
                uf,
                COUNT(*) AS quantidade_vendas,
                CAST(SUM(valor_venda) AS DECIMAL(18,2)) AS receita,
                CAST(AVG(valor_venda) AS DECIMAL(18,2)) AS ticket_medio,
                CAST(AVG(desconto_percentual) AS DECIMAL(9,4))
                    AS desconto_medio_percentual
            FROM fact_vendas
            GROUP BY 1, 2, 3, 4
        """)

        parquet = str((output / "fact_sales_pipeline.parquet").resolve())
        parquet = parquet.replace("'", "''")
        connection.execute(
            f"COPY fact_vendas TO '{parquet}' (FORMAT PARQUET, COMPRESSION ZSTD)"
        )
    finally:
        connection.close()


def _publish_outputs(files: tuple[tuple[Path, Path], ...]) -> None:
    transaction_id = uuid.uuid4().hex
    published: list[tuple[Path, Path | None]] = []
    try:
        for staged, target in files:
            backup = None
            if target.exists():
                backup = target.with_name(f".{target.name}.{transaction_id}.bak")
                os.replace(target, backup)
            try:
                os.replace(staged, target)
            except OSError:
                if backup is not None:
                    os.replace(backup, target)
                raise
            published.append((target, backup))
    except OSError:
        for target, backup in reversed(published):
            target.unlink(missing_ok=True)
            if backup is not None:
                os.replace(backup, target)
        raise
    else:
        for _, backup in published:
            if backup is not None:
                backup.unlink(missing_ok=True)


def save(
    output: Path,
    quarantine: Path,
    raw_vendas: pd.DataFrame,
    fato: pd.DataFrame,
    rejeitadas: pd.DataFrame,
    relatorio: pd.DataFrame,
    consultores: pd.DataFrame,
    lojas: pd.DataFrame,
    veiculos: pd.DataFrame,
) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    quarantine.parent.mkdir(parents=True, exist_ok=True)
    with (
        tempfile.TemporaryDirectory(
            prefix=".pipeline-output-", dir=output.parent
        ) as output_staging_name,
        tempfile.TemporaryDirectory(
            prefix=".pipeline-quarantine-", dir=quarantine.parent
        ) as quarantine_staging_name,
    ):
        output_staging = Path(output_staging_name)
        quarantine_staging = Path(quarantine_staging_name)
        _write_outputs(
            output_staging,
            quarantine_staging,
            raw_vendas,
            fato,
            rejeitadas,
            relatorio,
            consultores,
            lojas,
            veiculos,
        )

        output.mkdir(parents=True, exist_ok=True)
        quarantine.mkdir(parents=True, exist_ok=True)
        _publish_outputs(
            (
                (
                    output_staging / "quality_report.csv",
                    output / "quality_report.csv",
                ),
                (
                    output_staging / "sales_pipeline.duckdb",
                    output / "sales_pipeline.duckdb",
                ),
                (
                    output_staging / "fact_sales_pipeline.parquet",
                    output / "fact_sales_pipeline.parquet",
                ),
                (
                    quarantine_staging / "rejected_sales.csv",
                    quarantine / "rejected_sales.csv",
                ),
            )
        )


def run(input_path: Path, output: Path, quarantine: Path) -> dict[str, object]:
    from time import perf_counter

    started = perf_counter()

    def log(message: str) -> None:
        elapsed = perf_counter() - started
        print(f"[{elapsed:8.2f}s] {message}", flush=True)

    log("Iniciando ingestão")
    files = pipeline.ingest_input(input_path)
    log(f"Ingestão concluída: {len(files)} arquivos")

    log("Consolidando datasets")
    raw_vendas = combine(files, "vendas")
    consultores = combine(files, "consultores")
    lojas = combine(files, "lojas")
    veiculos = combine(files, "veiculos")
    log(f"Datasets consolidados: {len(raw_vendas)} vendas e {len(veiculos)} veículos")

    log("Normalizando campos")
    vendas, consultores, lojas, veiculos = normalize(
        raw_vendas,
        consultores,
        lojas,
        veiculos,
    )
    log("Normalização concluída")

    log("Executando validações e relacionamentos")
    fato, rejeitadas, relatorio = validate(
        vendas,
        consultores,
        lojas,
        veiculos,
    )
    log(f"Validação concluída: {len(fato)} válidas e {len(rejeitadas)} rejeitadas")

    log("Gravando CSV, Parquet e DuckDB")
    save(
        output,
        quarantine,
        raw_vendas,
        fato,
        rejeitadas,
        relatorio,
        consultores,
        lojas,
        veiculos,
    )
    log("Arquivos gravados com sucesso")

    return {
        "status": "success",
        "input_files": len(files),
        "sales_received": len(raw_vendas),
        "valid_sales": len(fato),
        "rejected_sales": len(rejeitadas),
        "elapsed_seconds": round(perf_counter() - started, 2),
        "output": str(output.resolve()),
        "quarantine": str(quarantine.resolve()),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Pipeline analítico de vendas")
    parser.add_argument("input", type=Path, help="ZIP, CSV ou diretório de entrada")
    parser.add_argument("--output", type=Path, default=Path("data/output"))
    parser.add_argument("--quarantine", type=Path, default=Path("data/quarantine"))
    args = parser.parse_args()

    try:
        result = run(args.input, args.output, args.quarantine)
    except Exception as error:  # noqa: BLE001 - CLI converts failures to exit code 1.
        print(f"Erro: {error}")
        return 1

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
