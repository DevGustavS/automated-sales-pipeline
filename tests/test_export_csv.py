from __future__ import annotations

import importlib
import sys
from decimal import Decimal
from pathlib import Path

import duckdb
import pandas as pd


def test_import_has_no_file_or_database_side_effect(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    sys.modules.pop("export_csv", None)

    importlib.import_module("export_csv")

    assert not (tmp_path / "data").exists()


def test_export_writes_semicolon_delimited_fact_csv(tmp_path: Path) -> None:
    export_csv = importlib.import_module("export_csv")
    database = tmp_path / "sales.duckdb"
    output = tmp_path / "exports" / "sales.csv"
    connection = duckdb.connect(str(database))
    try:
        connection.execute(
            """
            CREATE TABLE fact_vendas (
                venda_id VARCHAR,
                valor_venda DECIMAL(18,2)
            )
            """
        )
        connection.execute(
            "INSERT INTO fact_vendas VALUES ('S1', 90.05), ('S2', 150.15)"
        )
    finally:
        connection.close()

    generated = export_csv.export(database, output)
    exported = pd.read_csv(output, sep=";", dtype="string")

    assert generated == output.resolve()
    assert exported.to_dict("records") == [
        {"venda_id": "S1", "valor_venda": "90.05"},
        {"venda_id": "S2", "valor_venda": "150.15"},
    ]
    assert sum(Decimal(value) for value in exported["valor_venda"]) == Decimal("240.20")
