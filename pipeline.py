"""Safe discovery and ingestion for the automotive sales data package."""

from __future__ import annotations

import argparse
import codecs
import csv
import json
import re
import stat
import sys
import tempfile
import zipfile
import zlib
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import BinaryIO, Literal

import pandas as pd

EXPECTED_SCHEMAS: dict[str, tuple[str, ...]] = {
    "consultores": (
        "consultor_id",
        "consultor",
        "loja_id",
        "equipe",
        "data_admissao",
    ),
    "lojas": ("loja_id", "loja", "cidade", "uf", "cluster"),
    "veiculos": (
        "veiculo_id",
        "ano_modelo",
        "marca",
        "modelo",
        "versao",
        "carroceria",
        "cambio",
        "combustivel",
        "tipo_veiculo",
        "quilometragem",
        "cor_externa",
        "cor_interna",
        "score_avaliacao",
    ),
    "vendas": (
        "venda_id",
        "data_venda",
        "veiculo_id",
        "loja_id",
        "consultor_id",
        "canal_origem",
        "forma_pagamento",
        "valor_referencia",
        "valor_venda",
    ),
}

DIMENSION_FILES: dict[str, str] = {
    "dim_consultores.csv": "consultores",
    "dim_lojas.csv": "lojas",
    "dim_veiculos.csv": "veiculos",
}
SALES_FILE_PATTERN = re.compile(
    r"^vendas_\d{4}(?:_(?:0[1-9]|1[0-2]))?\.csv$",
    re.ASCII,
)

MAX_ZIP_FILES = 32
MAX_DIRECTORY_ENTRIES = 32
MAX_ZIP_ARCHIVE_BYTES = 64 * 1024 * 1024
MAX_ZIP_MEMBER_BYTES = 32 * 1024 * 1024
MAX_ZIP_UNCOMPRESSED_BYTES = 64 * 1024 * 1024
MAX_COMPRESSION_RATIO = 200.0
COPY_CHUNK_BYTES = 1024 * 1024
CSV_SAMPLE_CHARS = 64 * 1024

ALLOWED_COMPRESSION_METHODS = {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}
ALLOWED_ZIP_DIRECTORIES = {
    PurePosixPath("dados"),
    PurePosixPath("dados/dimensoes"),
    PurePosixPath("dados/vendas"),
}
TRACE_COLUMNS = ("__source_file", "__source_line")


class IngestionError(Exception):
    """Base class for expected ingestion failures."""

    exit_code = 1


class InputValidationError(IngestionError):
    """Report an invalid input path or unsupported input type."""

    exit_code = 2


class ArchiveValidationError(IngestionError):
    """Report an invalid, unsafe, or oversized ZIP archive."""

    exit_code = 3


class CsvValidationError(IngestionError):
    """Report an invalid CSV format or schema."""

    exit_code = 4


@dataclass(slots=True)
class IngestedFile:
    """Hold one validated CSV and its in-memory textual data."""

    source_file: str
    schema_name: str
    encoding: str
    delimiter: str
    data: pd.DataFrame


@dataclass(frozen=True, slots=True)
class _CsvSource:
    """Describe a validated CSV source before it is read."""

    path: Path
    source_file: str
    schema_hint: str | None


@dataclass(frozen=True, slots=True)
class _ValidatedZipMember:
    """Describe a ZIP member approved for temporary extraction."""

    info: zipfile.ZipInfo
    source_file: str
    schema_hint: str


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser for safe inspection."""

    parser = argparse.ArgumentParser(
        description="Inspeciona e valida entradas comerciais sem alterá-las."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    inspect_parser = subparsers.add_parser(
        "inspect",
        help="valida e resume um ZIP, CSV ou diretório",
    )
    inspect_parser.add_argument("input", type=Path, help="caminho da entrada")
    return parser


def ingest_input(path: Path) -> list[IngestedFile]:
    """Validate and load an input in deterministic source-file order."""

    input_kind, validated_path = _validate_input_path(path)
    if input_kind == "zip":
        ingested = _ingest_zip(validated_path)
    elif input_kind == "directory":
        ingested = [
            _read_csv_as_text(source) for source in _discover_directory(validated_path)
        ]
    else:
        source = _source_for_standalone_csv(validated_path)
        ingested = [_read_csv_as_text(source)]

    return sorted(
        ingested,
        key=lambda item: (item.source_file.casefold(), item.source_file),
    )


def _validate_input_path(path: Path) -> tuple[Literal["csv", "zip", "directory"], Path]:
    """Validate existence, type, link status, and extension of an input."""

    candidate = Path(path)
    if not candidate.exists():
        raise InputValidationError(f"A entrada não existe: {candidate}")
    if _is_link_like(candidate):
        raise InputValidationError(f"Links e junctions não são aceitos: {candidate}")

    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise InputValidationError(
            f"Não foi possível resolver a entrada {candidate}: {exc}"
        ) from exc

    if resolved.is_dir():
        return "directory", resolved
    if not resolved.is_file():
        raise InputValidationError(
            f"A entrada não é arquivo nem diretório: {candidate}"
        )

    suffix = resolved.suffix.casefold()
    if suffix == ".csv":
        return "csv", resolved
    if suffix == ".zip":
        return "zip", resolved
    raise InputValidationError(
        f"Extensão não permitida para {candidate}: {suffix or '(sem extensão)'}"
    )


def _is_link_like(path: Path) -> bool:
    """Return whether a path is a symbolic link or Windows junction."""

    return path.is_symlink() or path.is_junction()


def _source_for_standalone_csv(path: Path) -> _CsvSource:
    """Create a source descriptor for one standalone CSV."""

    _validate_regular_file_size(path, path.name)
    return _CsvSource(
        path=path,
        source_file=path.name,
        schema_hint=_schema_hint_from_filename(path.name),
    )


def _discover_directory(root: Path) -> list[_CsvSource]:
    """Discover accepted CSVs recursively without following link-like paths."""

    sources: list[_CsvSource] = []
    entry_count = 0
    total_bytes = 0
    pending_directories = [root]

    try:
        while pending_directories:
            current_directory = pending_directories.pop()
            for entry in current_directory.iterdir():
                entry_count += 1
                if entry_count > MAX_DIRECTORY_ENTRIES:
                    raise InputValidationError(
                        "O diretório excede o limite de "
                        f"{MAX_DIRECTORY_ENTRIES} entradas."
                    )
                if _is_link_like(entry):
                    raise InputValidationError(
                        f"Links e junctions não são aceitos no diretório: {entry}"
                    )

                resolved_entry = entry.resolve(strict=True)
                if not resolved_entry.is_relative_to(root):
                    raise InputValidationError(
                        f"Conteúdo resolve para fora do diretório de entrada: {entry}"
                    )
                if resolved_entry.is_dir():
                    pending_directories.append(resolved_entry)
                    continue
                if not resolved_entry.is_file():
                    raise InputValidationError(
                        f"Conteúdo não regular no diretório: {entry}"
                    )

                relative = entry.relative_to(root).as_posix()
                size = resolved_entry.stat().st_size
                total_bytes += size
                if total_bytes > MAX_ZIP_UNCOMPRESSED_BYTES:
                    raise InputValidationError(
                        "O diretório excede o limite total de "
                        f"{MAX_ZIP_UNCOMPRESSED_BYTES} bytes."
                    )

                if entry.name == ".gitkeep" or relative.casefold() == "readme.md":
                    continue
                if entry.suffix.casefold() != ".csv":
                    raise InputValidationError(
                        f"Conteúdo inesperado no diretório: {relative}"
                    )

                _validate_regular_file_size(resolved_entry, relative)
                sources.append(
                    _CsvSource(
                        path=resolved_entry,
                        source_file=relative,
                        schema_hint=_schema_hint_from_filename(entry.name),
                    )
                )
    except OSError as exc:
        raise InputValidationError(
            f"Não foi possível percorrer o diretório {root}: {exc}"
        ) from exc

    if not sources:
        raise InputValidationError(f"Nenhum CSV aceito foi encontrado em: {root}")
    return sorted(
        sources,
        key=lambda item: (item.source_file.casefold(), item.source_file),
    )


def _validate_regular_file_size(path: Path, source_file: str) -> None:
    """Reject an empty or oversized regular CSV before it is read."""

    try:
        size = path.stat().st_size
    except OSError as exc:
        raise InputValidationError(
            f"Não foi possível consultar o tamanho de {source_file}: {exc}"
        ) from exc
    if size == 0:
        raise CsvValidationError(f"CSV vazio: {source_file}")
    if size > MAX_ZIP_MEMBER_BYTES:
        raise InputValidationError(
            f"{source_file} excede o limite de {MAX_ZIP_MEMBER_BYTES} bytes."
        )


def _ingest_zip(path: Path) -> list[IngestedFile]:
    """Inspect, temporarily extract, and load a validated ZIP archive."""

    try:
        archive_size = path.stat().st_size
    except OSError as exc:
        raise ArchiveValidationError(
            f"Não foi possível consultar o ZIP {path}: {exc}"
        ) from exc
    if archive_size > MAX_ZIP_ARCHIVE_BYTES:
        raise ArchiveValidationError(
            f"O ZIP excede o limite de {MAX_ZIP_ARCHIVE_BYTES} bytes: {path}"
        )
    if not zipfile.is_zipfile(path):
        raise ArchiveValidationError(f"O arquivo não contém um ZIP válido: {path}")

    try:
        with zipfile.ZipFile(path) as archive:
            members = _inspect_zip(archive)
            bad_member = archive.testzip()
            if bad_member is not None:
                raise ArchiveValidationError(
                    f"Falha de integridade CRC no membro ZIP: {bad_member}"
                )

            with tempfile.TemporaryDirectory(
                prefix="automated-sales-ingestion-"
            ) as temporary_directory:
                sources = _extract_zip_csvs(
                    archive,
                    members,
                    Path(temporary_directory),
                )
                return [_read_csv_as_text(source) for source in sources]
    except ArchiveValidationError:
        raise
    except (EOFError, OSError, RuntimeError, zipfile.BadZipFile, zlib.error) as exc:
        raise ArchiveValidationError(
            f"Não foi possível processar o ZIP {path}: {exc}"
        ) from exc


def _inspect_zip(archive: zipfile.ZipFile) -> list[_ValidatedZipMember]:
    """Validate every ZIP member and all limits before extraction."""

    validated: list[_ValidatedZipMember] = []
    seen_paths: set[str] = set()
    total_bytes = 0
    file_count = 0

    for info in archive.infolist():
        normalized = _normalize_zip_member(info)
        collision_key = normalized.as_posix().casefold()
        if collision_key in seen_paths:
            raise ArchiveValidationError(
                f"Caminho duplicado ou colisão por caixa no ZIP: {info.filename}"
            )
        seen_paths.add(collision_key)

        _validate_zip_member_type(info)
        if info.is_dir():
            if normalized not in ALLOWED_ZIP_DIRECTORIES:
                raise ArchiveValidationError(
                    f"Diretório inesperado no ZIP: {info.filename}"
                )
            continue

        file_count += 1
        if file_count > MAX_ZIP_FILES:
            raise ArchiveValidationError(
                f"O ZIP excede o limite de {MAX_ZIP_FILES} arquivos."
            )
        if info.file_size > MAX_ZIP_MEMBER_BYTES:
            raise ArchiveValidationError(
                f"Membro excede o limite de {MAX_ZIP_MEMBER_BYTES} bytes: "
                f"{info.filename}"
            )

        total_bytes += info.file_size
        if total_bytes > MAX_ZIP_UNCOMPRESSED_BYTES:
            raise ArchiveValidationError(
                "O ZIP excede o limite descompactado de "
                f"{MAX_ZIP_UNCOMPRESSED_BYTES} bytes."
            )

        if info.file_size > 0:
            if info.compress_size == 0:
                raise ArchiveValidationError(
                    f"Razão de compressão inválida no membro: {info.filename}"
                )
            ratio = info.file_size / info.compress_size
            if ratio > MAX_COMPRESSION_RATIO:
                raise ArchiveValidationError(
                    f"Membro excede a razão de compressão {MAX_COMPRESSION_RATIO:g}: "
                    f"{info.filename}"
                )

        schema_hint = _schema_for_zip_member(normalized)
        if schema_hint is not None:
            validated.append(
                _ValidatedZipMember(
                    info=info,
                    source_file=normalized.as_posix(),
                    schema_hint=schema_hint,
                )
            )

    if not validated:
        raise ArchiveValidationError("O ZIP não contém CSVs previstos pelo desafio.")
    return sorted(
        validated,
        key=lambda item: (item.source_file.casefold(), item.source_file),
    )


def _normalize_zip_member(info: zipfile.ZipInfo) -> PurePosixPath:
    """Reject unsafe ZIP paths and return one normalized POSIX path."""

    name = info.filename
    if not name or "\x00" in name:
        raise ArchiveValidationError("O ZIP contém um caminho vazio ou com NUL.")
    if "\\" in name:
        raise ArchiveValidationError(
            f"Caminho ZIP usa separador inseguro para Windows: {name}"
        )
    if name.startswith(("/", "\\")):
        raise ArchiveValidationError(f"Caminho absoluto rejeitado no ZIP: {name}")

    windows_path = PureWindowsPath(name)
    if windows_path.drive or windows_path.is_absolute():
        raise ArchiveValidationError(f"Caminho absoluto rejeitado no ZIP: {name}")

    candidate = name[:-1] if info.is_dir() and name.endswith("/") else name
    parts = candidate.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise ArchiveValidationError(f"Caminho inseguro rejeitado no ZIP: {name}")

    normalized = PurePosixPath(*parts)
    if normalized.is_absolute() or ".." in normalized.parts:
        raise ArchiveValidationError(f"Caminho inseguro rejeitado no ZIP: {name}")
    return normalized


def _validate_zip_member_type(info: zipfile.ZipInfo) -> None:
    """Reject encrypted, linked, special, or unsupported ZIP members."""

    if info.flag_bits & 0x1:
        raise ArchiveValidationError(f"Membro ZIP criptografado: {info.filename}")
    if info.compress_type not in ALLOWED_COMPRESSION_METHODS:
        raise ArchiveValidationError(
            f"Método de compressão não permitido em: {info.filename}"
        )

    mode = info.external_attr >> 16
    file_type = stat.S_IFMT(mode)
    if file_type == stat.S_IFLNK:
        raise ArchiveValidationError(
            f"Link simbólico rejeitado no ZIP: {info.filename}"
        )
    if file_type not in {0, stat.S_IFREG, stat.S_IFDIR}:
        raise ArchiveValidationError(
            f"Membro especial rejeitado no ZIP: {info.filename}"
        )
    if file_type == stat.S_IFREG and info.is_dir():
        raise ArchiveValidationError(
            f"Tipo de arquivo incoerente com o caminho ZIP: {info.filename}"
        )
    if file_type == stat.S_IFDIR and not info.is_dir():
        raise ArchiveValidationError(
            f"Tipo de diretório incoerente com o caminho ZIP: {info.filename}"
        )


def _schema_for_zip_member(path: PurePosixPath) -> str | None:
    """Return the schema for an allowed ZIP path or reject its content."""

    if path == PurePosixPath("README.md"):
        return None
    if path.parent == PurePosixPath("dados/dimensoes"):
        schema = DIMENSION_FILES.get(path.name.casefold())
        if schema is not None:
            return schema
    if path.parent == PurePosixPath("dados/vendas") and SALES_FILE_PATTERN.fullmatch(
        path.name.casefold()
    ):
        return "vendas"
    raise ArchiveValidationError(f"Conteúdo inesperado no ZIP: {path.as_posix()}")


def _extract_zip_csvs(
    archive: zipfile.ZipFile,
    members: Sequence[_ValidatedZipMember],
    destination: Path,
) -> list[_CsvSource]:
    """Extract only validated CSV members into one temporary directory."""

    temporary_root = destination.resolve(strict=True)
    sources: list[_CsvSource] = []

    for member in members:
        relative = PurePosixPath(member.source_file)
        target = temporary_root.joinpath(*relative.parts)
        resolved_target = target.resolve(strict=False)
        if not resolved_target.is_relative_to(temporary_root):
            raise ArchiveValidationError(
                f"Destino escaparia do diretório temporário: {member.source_file}"
            )
        resolved_target.parent.mkdir(parents=True, exist_ok=True)

        try:
            with (
                archive.open(member.info, "r") as source_stream,
                resolved_target.open("xb") as destination_stream,
            ):
                copied = _copy_zip_member_limited(
                    source_stream,
                    destination_stream,
                    MAX_ZIP_MEMBER_BYTES,
                )
        except (EOFError, OSError, RuntimeError, zipfile.BadZipFile, zlib.error) as exc:
            raise ArchiveValidationError(
                f"Falha ao extrair temporariamente {member.source_file}: {exc}"
            ) from exc

        if copied != member.info.file_size:
            raise ArchiveValidationError(
                f"Tamanho extraído diverge do informado: {member.source_file}"
            )
        sources.append(
            _CsvSource(
                path=resolved_target,
                source_file=member.source_file,
                schema_hint=member.schema_hint,
            )
        )

    return sources


def _copy_zip_member_limited(
    source: BinaryIO,
    destination: BinaryIO,
    byte_limit: int,
) -> int:
    """Copy one ZIP stream while enforcing the actual extracted byte limit."""

    copied = 0
    while chunk := source.read(COPY_CHUNK_BYTES):
        copied += len(chunk)
        if copied > byte_limit:
            raise ArchiveValidationError(
                f"Conteúdo extraído excede o limite de {byte_limit} bytes."
            )
        destination.write(chunk)
    return copied


def _schema_hint_from_filename(filename: str) -> str | None:
    """Return a known schema hint from a challenge dataset filename."""

    normalized = filename.casefold()
    dimension_schema = DIMENSION_FILES.get(normalized)
    if dimension_schema is not None:
        return dimension_schema
    if SALES_FILE_PATTERN.fullmatch(normalized):
        return "vendas"
    return None


def _detect_csv_format(path: Path, source_file: str) -> tuple[str, str]:
    """Detect UTF-8 encoding and delimiter, rejecting other real formats."""

    try:
        with path.open("rb") as raw_stream:
            prefix = raw_stream.read(4)
    except OSError as exc:
        raise CsvValidationError(f"Não foi possível ler {source_file}: {exc}") from exc

    unsupported_boms = (
        codecs.BOM_UTF32_LE,
        codecs.BOM_UTF32_BE,
        codecs.BOM_UTF16_LE,
        codecs.BOM_UTF16_BE,
    )
    if any(prefix.startswith(bom) for bom in unsupported_boms):
        raise CsvValidationError(f"Encoding não permitido em {source_file}; use UTF-8.")
    encoding = "utf-8-sig" if prefix.startswith(codecs.BOM_UTF8) else "utf-8"

    try:
        with path.open("r", encoding=encoding, errors="strict", newline="") as stream:
            sample = stream.read(CSV_SAMPLE_CHARS)
    except UnicodeDecodeError as exc:
        raise CsvValidationError(
            f"Encoding inválido em {source_file}; esperado UTF-8."
        ) from exc
    except OSError as exc:
        raise CsvValidationError(f"Não foi possível ler {source_file}: {exc}") from exc

    if not sample:
        raise CsvValidationError(f"CSV vazio: {source_file}")
    if "\x00" in sample:
        raise CsvValidationError(f"Conteúdo binário/NUL rejeitado em: {source_file}")

    header_line = sample.splitlines()[0] if sample.splitlines() else sample
    delimiter_counts = {
        delimiter: header_line.count(delimiter) for delimiter in (";", ",", "\t", "|")
    }
    detected = max(delimiter_counts, key=delimiter_counts.get)
    if delimiter_counts[detected] == 0:
        raise CsvValidationError(
            f"Não foi possível detectar o delimitador de {source_file}."
        )
    if detected != ";":
        raise CsvValidationError(
            f"Delimitador inválido em {source_file}: {detected!r}; esperado ';'."
        )
    return encoding, detected


def _read_csv_as_text(source: _CsvSource) -> IngestedFile:
    """Read a validated CSV as text and append in-memory provenance."""

    encoding, delimiter = _detect_csv_format(source.path, source.source_file)
    rows: list[list[str]] = []
    source_lines: list[int] = []

    try:
        with source.path.open(
            "r",
            encoding=encoding,
            errors="strict",
            newline="",
        ) as stream:
            reader = csv.reader(stream, delimiter=delimiter, strict=True)
            try:
                header = next(reader)
            except StopIteration as exc:
                raise CsvValidationError(f"CSV vazio: {source.source_file}") from exc

            columns = tuple(header)
            schema_name = _resolve_schema(
                columns,
                source.schema_hint,
                source.source_file,
            )

            while True:
                source_line = reader.line_num + 1
                try:
                    row = next(reader)
                except StopIteration:
                    break
                if len(row) != len(columns):
                    raise CsvValidationError(
                        f"Quantidade de campos inválida em {source.source_file}, "
                        f"linha {source_line}: esperado {len(columns)}, recebido {len(row)}."
                    )
                if any("\x00" in value for value in row):
                    raise CsvValidationError(
                        f"Conteúdo NUL rejeitado em {source.source_file}, "
                        f"linha {source_line}."
                    )
                rows.append(row)
                source_lines.append(source_line)
    except CsvValidationError:
        raise
    except UnicodeDecodeError as exc:
        raise CsvValidationError(
            f"Encoding inválido em {source.source_file}; esperado UTF-8."
        ) from exc
    except csv.Error as exc:
        raise CsvValidationError(
            f"CSV malformado em {source.source_file}: {exc}"
        ) from exc
    except OSError as exc:
        raise CsvValidationError(
            f"Não foi possível ler {source.source_file}: {exc}"
        ) from exc

    frame = pd.DataFrame(rows, columns=columns, dtype="string")
    frame[TRACE_COLUMNS[0]] = pd.Series(
        [source.source_file] * len(frame),
        index=frame.index,
        dtype="string",
    )
    frame[TRACE_COLUMNS[1]] = pd.Series(
        source_lines,
        index=frame.index,
        dtype="Int64",
    )
    return IngestedFile(
        source_file=source.source_file,
        schema_name=schema_name,
        encoding=encoding,
        delimiter=delimiter,
        data=frame,
    )


def _resolve_schema(
    columns: tuple[str, ...],
    schema_hint: str | None,
    source_file: str,
) -> str:
    """Match an exact ordered header to one expected schema."""

    if not columns or any(not column for column in columns):
        raise CsvValidationError(f"Schema vazio ou com coluna vazia: {source_file}")
    if len(set(columns)) != len(columns):
        raise CsvValidationError(f"Schema com colunas duplicadas: {source_file}")

    if schema_hint is not None:
        expected = EXPECTED_SCHEMAS[schema_hint]
        if columns != expected:
            detail = _schema_difference(expected, columns)
            raise CsvValidationError(
                f"Schema inválido em {source_file} para {schema_hint}: {detail}"
            )
        return schema_hint

    matches = [
        name for name, expected in EXPECTED_SCHEMAS.items() if columns == expected
    ]
    if len(matches) != 1:
        raise CsvValidationError(
            f"Schema de {source_file} não corresponde a nenhum dataset previsto."
        )
    return matches[0]


def _schema_difference(
    expected: tuple[str, ...],
    received: tuple[str, ...],
) -> str:
    """Describe missing, extra, or reordered schema columns."""

    missing = [column for column in expected if column not in received]
    extra = [column for column in received if column not in expected]
    details: list[str] = []
    if missing:
        details.append(f"ausentes={missing}")
    if extra:
        details.append(f"extras={extra}")
    if not missing and not extra and expected != received:
        details.append("ordem das colunas divergente")
    return "; ".join(details) or "cabeçalho divergente"


def _print_summary(files: Sequence[IngestedFile]) -> None:
    """Print calculated inspection metadata as deterministic JSON."""

    payload = {
        "files": [
            {
                "source_file": item.source_file,
                "schema": item.schema_name,
                "encoding": item.encoding,
                "delimiter": item.delimiter,
                "headers": list(EXPECTED_SCHEMAS[item.schema_name]),
                "rows": len(item.data),
            }
            for item in files
        ],
        "total_files": len(files),
        "total_rows": sum(len(item.data) for item in files),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def main(argv: Sequence[str] | None = None) -> int:
    """Run the inspection command and return a meaningful exit code."""

    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        files = ingest_input(args.input)
    except IngestionError as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return exc.exit_code

    _print_summary(files)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
