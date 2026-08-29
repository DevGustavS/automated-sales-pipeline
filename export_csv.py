from pathlib import Path

import duckdb

DATABASE = Path("data/output/sales_pipeline.duckdb")
OUTPUT = Path("data/output/fact_sales_pipeline.csv")


def export(database: Path, output: Path) -> Path:
    if not database.exists():
        raise FileNotFoundError(f"Banco não encontrado: {database}")

    output.parent.mkdir(parents=True, exist_ok=True)
    connection = duckdb.connect(str(database), read_only=True)
    try:
        output_path = str(output.resolve()).replace("'", "''")
        connection.execute(
            f"COPY fact_vendas TO '{output_path}' (FORMAT CSV, HEADER, DELIMITER ';')"
        )
    finally:
        connection.close()
    return output.resolve()


def main() -> int:
    try:
        generated = export(DATABASE, OUTPUT)
    except FileNotFoundError as error:
        print(error)
        return 1
    print(f"CSV gerado: {generated}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
