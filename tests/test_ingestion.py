"""Tests for safe, read-only ingestion using only artificial fixtures."""

from __future__ import annotations

import codecs
import hashlib
import io
import json
import stat
import struct
import zipfile
from pathlib import Path

import pandas as pd
import pytest

import pipeline

CONSULTANT_SCHEMA = (
    "consultor_id",
    "consultor",
    "loja_id",
    "equipe",
    "data_admissao",
)
STORE_SCHEMA = ("loja_id", "loja", "cidade", "uf", "cluster")
SALES_SCHEMA = (
    "venda_id",
    "data_venda",
    "veiculo_id",
    "loja_id",
    "consultor_id",
    "canal_origem",
    "forma_pagamento",
    "valor_referencia",
    "valor_venda",
)


def _csv_text(
    headers: tuple[str, ...],
    rows: list[tuple[str, ...]],
    newline: str = "\n",
) -> str:
    """Build a small semicolon-delimited CSV fixture."""

    lines = [";".join(headers), *(";".join(row) for row in rows)]
    return newline.join(lines) + newline


def _valid_store_csv() -> str:
    """Return one valid artificial store CSV."""

    return _csv_text(
        STORE_SCHEMA,
        [("LOJ001", "Unidade 01", "Natal", "RN", "Capital")],
    )


def _write_zip(path: Path, members: list[tuple[str, str | bytes]]) -> Path:
    """Create a small ZIP fixture with the supplied member order."""

    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in members:
            archive.writestr(name, content)
    return path


def _sha256(path: Path) -> str:
    """Calculate a file hash without modifying the fixture."""

    return hashlib.sha256(path.read_bytes()).hexdigest()


def _mutate_single_member_zip(
    path: Path,
    *,
    flag_bits: int | None = None,
    compression_method: int | None = None,
    crc: int | None = None,
) -> Path:
    """Patch matching local and central headers in a one-member ZIP fixture."""

    with zipfile.ZipFile(path) as archive:
        [info] = archive.infolist()

    payload = bytearray(path.read_bytes())
    central_offset = payload.rfind(b"PK\x01\x02")
    assert central_offset >= 0

    if flag_bits is not None:
        struct.pack_into("<H", payload, info.header_offset + 6, flag_bits)
        struct.pack_into("<H", payload, central_offset + 8, flag_bits)
    if compression_method is not None:
        struct.pack_into("<H", payload, info.header_offset + 8, compression_method)
        struct.pack_into("<H", payload, central_offset + 10, compression_method)
    if crc is not None:
        struct.pack_into("<I", payload, info.header_offset + 14, crc)
        struct.pack_into("<I", payload, central_offset + 16, crc)

    path.write_bytes(payload)
    return path


def test_read_valid_csv_preserves_text_and_trace(tmp_path: Path) -> None:
    """Keep every domain value textual and append source provenance."""

    csv_path = tmp_path / "vendas_2026_06.csv"
    csv_path.write_text(
        _csv_text(
            SALES_SCHEMA,
            [
                (
                    "VND0001",
                    "2026-06-01",
                    "VEI0001",
                    "LOJ001",
                    "",
                    "Indicação",
                    "À vista",
                    "000123,40",
                    "NA",
                ),
                (
                    "VND0001",
                    "formato-livre",
                    "VEI0001",
                    "LOJ001",
                    "CON001",
                    "Site",
                    "Financiamento",
                    "0",
                    "000100",
                ),
            ],
            newline="\r\n",
        ),
        encoding="utf-8",
        newline="",
    )

    result = pipeline.ingest_input(csv_path)

    assert len(result) == 1
    ingested = result[0]
    assert isinstance(ingested.data, pd.DataFrame)
    assert ingested.schema_name == "vendas"
    assert ingested.encoding == "utf-8"
    assert ingested.delimiter == ";"
    assert list(ingested.data.columns) == [
        *SALES_SCHEMA,
        "__source_file",
        "__source_line",
    ]
    assert ingested.data["valor_referencia"].tolist() == ["000123,40", "0"]
    assert ingested.data["valor_venda"].tolist() == ["NA", "000100"]
    assert ingested.data["consultor_id"].tolist()[0] == ""
    assert ingested.data["venda_id"].tolist() == ["VND0001", "VND0001"]
    assert ingested.data["__source_file"].tolist() == [csv_path.name] * 2
    assert ingested.data["__source_line"].tolist() == [2, 3]
    assert all(
        isinstance(value, str)
        for column in SALES_SCHEMA
        for value in ingested.data[column].tolist()
    )


def test_trace_uses_physical_record_start(tmp_path: Path) -> None:
    """Track the first physical line of records containing embedded newlines."""

    csv_path = tmp_path / "dim_consultores.csv"
    csv_path.write_text(
        ";".join(CONSULTANT_SCHEMA)
        + '\nCON001;"Consultor\nUm";LOJ001;Equipe 1;2024-01-01\n'
        + "CON002;Consultor Dois;LOJ001;Equipe 1;2024-01-02\n",
        encoding="utf-8",
        newline="",
    )

    frame = pipeline.ingest_input(csv_path)[0].data

    assert frame["consultor"].tolist() == ["Consultor\nUm", "Consultor Dois"]
    assert frame["__source_line"].tolist() == [2, 4]


def test_valid_zip_allows_expected_readme_and_utf8_bom(tmp_path: Path) -> None:
    """Allow only the known README metadata and remove a UTF-8 BOM safely."""

    archive_path = _write_zip(
        tmp_path / "entrada.zip",
        [
            ("README.md", "# Pacote artificial\n"),
            (
                "dados/dimensoes/dim_lojas.csv",
                codecs.BOM_UTF8 + _valid_store_csv().encode("utf-8"),
            ),
        ],
    )

    result = pipeline.ingest_input(archive_path)

    assert len(result) == 1
    assert result[0].source_file == "dados/dimensoes/dim_lojas.csv"
    assert result[0].schema_name == "lojas"
    assert result[0].encoding == "utf-8-sig"
    assert result[0].data.columns[0] == "loja_id"


def test_valid_directory_is_recursive_and_deterministic(tmp_path: Path) -> None:
    """Read a directory recursively while ignoring its foundation placeholder."""

    root = tmp_path / "entrada"
    sales_path = root / "dados" / "vendas" / "vendas_2026_06.csv"
    store_path = root / "dados" / "dimensoes" / "dim_lojas.csv"
    sales_path.parent.mkdir(parents=True)
    store_path.parent.mkdir(parents=True)
    sales_path.write_text(
        _csv_text(
            SALES_SCHEMA,
            [
                (
                    "VND1",
                    "2026-06-01",
                    "VEI1",
                    "LOJ1",
                    "CON1",
                    "Site",
                    "À vista",
                    "10",
                    "9",
                )
            ],
        ),
        encoding="utf-8",
    )
    store_path.write_text(_valid_store_csv(), encoding="utf-8")
    (root / ".gitkeep").write_text("", encoding="utf-8")

    result = pipeline.ingest_input(root)

    assert [item.source_file for item in result] == [
        "dados/dimensoes/dim_lojas.csv",
        "dados/vendas/vendas_2026_06.csv",
    ]


def test_rejects_junction_like_directory_entry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Reject a Windows junction before traversing its apparent directory."""

    root = tmp_path / "entrada"
    junction = root / "junction"
    junction.mkdir(parents=True)
    (junction / "dim_lojas.csv").write_text(_valid_store_csv(), encoding="utf-8")
    original_is_junction = Path.is_junction

    def report_artificial_junction(path: Path) -> bool:
        """Model a junction portably without requiring OS link privileges."""

        return path == junction or original_is_junction(path)

    monkeypatch.setattr(Path, "is_junction", report_artificial_junction)

    with pytest.raises(pipeline.InputValidationError, match="junctions"):
        pipeline.ingest_input(root)


def test_rejects_link_like_top_level_input(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Reject a link-like input itself before resolving or opening it."""

    csv_path = tmp_path / "dim_lojas.csv"
    csv_path.write_text(_valid_store_csv(), encoding="utf-8")
    original_is_symlink = Path.is_symlink

    def report_artificial_symlink(path: Path) -> bool:
        """Model a symbolic link without requiring Windows link privileges."""

        return path == csv_path or original_is_symlink(path)

    monkeypatch.setattr(Path, "is_symlink", report_artificial_symlink)

    with pytest.raises(pipeline.InputValidationError, match="Links"):
        pipeline.ingest_input(csv_path)


def test_rejects_directory_entry_resolving_outside_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Reject an entry whose resolved location would leave the selected root."""

    root = tmp_path / "entrada"
    root.mkdir()
    entry = root / "dim_lojas.csv"
    entry.write_text(_valid_store_csv(), encoding="utf-8")
    outside = tmp_path / "outside.csv"
    original_resolve = Path.resolve

    def redirect_entry(path: Path, strict: bool = False) -> Path:
        """Model a concurrent path redirection for the containment check."""

        if path == entry:
            return outside
        return original_resolve(path, strict=strict)

    monkeypatch.setattr(Path, "resolve", redirect_entry)

    with pytest.raises(pipeline.InputValidationError, match="fora do diretório"):
        pipeline.ingest_input(root)


def test_zip_member_order_does_not_affect_result(tmp_path: Path) -> None:
    """Return a canonical order regardless of ZIP insertion order."""

    archive_path = _write_zip(
        tmp_path / "reversed.zip",
        [
            (
                "dados/vendas/vendas_2026_06.csv",
                _csv_text(
                    SALES_SCHEMA,
                    [
                        (
                            "VND1",
                            "2026-06-01",
                            "VEI1",
                            "LOJ1",
                            "CON1",
                            "Site",
                            "À vista",
                            "10",
                            "9",
                        )
                    ],
                ),
            ),
            ("dados/dimensoes/dim_lojas.csv", _valid_store_csv()),
        ],
    )

    names = [item.source_file for item in pipeline.ingest_input(archive_path)]

    assert names == [
        "dados/dimensoes/dim_lojas.csv",
        "dados/vendas/vendas_2026_06.csv",
    ]


def test_missing_input_has_clear_error_and_nonzero_cli(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Fail clearly and nonzero when the requested input does not exist."""

    missing = tmp_path / "ausente.zip"

    with pytest.raises(pipeline.InputValidationError, match="não existe"):
        pipeline.ingest_input(missing)
    exit_code = pipeline.main(["inspect", str(missing)])

    assert exit_code == 2
    assert str(missing) in capsys.readouterr().err


def test_rejects_unsupported_extension(tmp_path: Path) -> None:
    """Reject an allowed-looking payload with an unsupported extension."""

    path = tmp_path / "dim_lojas.json"
    path.write_text(_valid_store_csv(), encoding="utf-8")

    with pytest.raises(pipeline.InputValidationError, match="Extensão"):
        pipeline.ingest_input(path)


@pytest.mark.parametrize(
    "headers",
    [
        STORE_SCHEMA[:-1],
        (*STORE_SCHEMA, "extra"),
        ("loja", "loja_id", "cidade", "uf", "cluster"),
        ("loja_id", "loja", "cidade", "uf", "uf"),
        ("loja_id", "loja ", "cidade", "uf", "cluster"),
    ],
)
def test_rejects_missing_or_incorrect_schema(
    tmp_path: Path, headers: tuple[str, ...]
) -> None:
    """Require exact, ordered, unique columns for a known dataset."""

    path = tmp_path / "dim_lojas.csv"
    path.write_text(_csv_text(headers, []), encoding="utf-8")

    with pytest.raises(pipeline.CsvValidationError, match="Schema") as error:
        pipeline.ingest_input(path)

    assert path.name in str(error.value)


@pytest.mark.parametrize(
    "payload",
    [
        ",".join(STORE_SCHEMA).encode("utf-8") + b"\n",
        ";".join(STORE_SCHEMA).encode("utf-16"),
        ";".join(STORE_SCHEMA).encode("utf-32"),
        (";".join(STORE_SCHEMA) + "\nLOJ1;Unidade;São Paulo;SP;Capital\n").encode(
            "cp1252"
        ),
        b"loja_id;loja;cidade;uf;cluster\nLOJ1;\x00;Natal;RN;Capital\n",
        (";".join(STORE_SCHEMA) + "\nLOJ1;Unidade;Natal;RN\n").encode("utf-8"),
    ],
)
def test_rejects_wrong_real_csv_format(tmp_path: Path, payload: bytes) -> None:
    """Reject wrong delimiter, encoding, binary content, and malformed rows."""

    path = tmp_path / "dim_lojas.csv"
    path.write_bytes(payload)

    with pytest.raises(pipeline.CsvValidationError):
        pipeline.ingest_input(path)


@pytest.mark.parametrize(
    "unsafe_name",
    [
        "../dim_lojas.csv",
        "dados/../../dim_lojas.csv",
        "dados/./dim_lojas.csv",
        "/dados/dimensoes/dim_lojas.csv",
        "C:/temp/dim_lojas.csv",
        "C:\\temp\\dim_lojas.csv",
        "\\\\server\\share\\dim_lojas.csv",
    ],
)
def test_rejects_zip_slip_and_absolute_paths(tmp_path: Path, unsafe_name: str) -> None:
    """Reject parent traversal and POSIX, drive, or UNC absolute paths."""

    archive_path = _write_zip(
        tmp_path / "unsafe.zip",
        [(unsafe_name, _valid_store_csv())],
    )

    with pytest.raises(pipeline.ArchiveValidationError, match="Caminho"):
        pipeline.ingest_input(archive_path)

    assert not (tmp_path / "dim_lojas.csv").exists()


@pytest.mark.parametrize(
    "unexpected_name",
    ["payload.exe", "dados/segredos.csv", "__MACOSX/._dim_lojas.csv"],
)
def test_rejects_unexpected_zip_content(tmp_path: Path, unexpected_name: str) -> None:
    """Invalidate the whole ZIP when any member is outside the allowlist."""

    archive_path = _write_zip(
        tmp_path / "unexpected.zip",
        [
            ("dados/dimensoes/dim_lojas.csv", _valid_store_csv()),
            (unexpected_name, "não permitido"),
        ],
    )

    with pytest.raises(pipeline.ArchiveValidationError, match="inesperado"):
        pipeline.ingest_input(archive_path)


def test_rejects_zip_symlink(tmp_path: Path) -> None:
    """Reject a ZIP member marked as a Unix symbolic link."""

    archive_path = tmp_path / "symlink.zip"
    link = zipfile.ZipInfo("dados/dimensoes/dim_lojas.csv")
    link.create_system = 3
    link.external_attr = (stat.S_IFLNK | 0o777) << 16
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr(link, "target")

    with pytest.raises(pipeline.ArchiveValidationError, match="simbólico"):
        pipeline.ingest_input(archive_path)


def test_rejects_zip_member_with_incoherent_unix_type(tmp_path: Path) -> None:
    """Reject a regular-file type advertised with a directory-style name."""

    archive_path = tmp_path / "incoherent.zip"
    member = zipfile.ZipInfo("dados/")
    member.create_system = 3
    member.external_attr = (stat.S_IFREG | 0o644) << 16
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr(member, b"")

    with pytest.raises(pipeline.ArchiveValidationError, match="incoerente"):
        pipeline.ingest_input(archive_path)


@pytest.mark.parametrize(
    ("name", "file_type", "message"),
    [
        ("dados/dimensoes/dim_lojas.csv", stat.S_IFDIR, "incoerente"),
        ("dados/dimensoes/dim_lojas.csv", stat.S_IFIFO, "especial"),
    ],
)
def test_rejects_incoherent_directory_type_and_special_member(
    tmp_path: Path, name: str, file_type: int, message: str
) -> None:
    """Reject a directory type without a slash and a Unix special file."""

    archive_path = tmp_path / "invalid-type.zip"
    member = zipfile.ZipInfo(name)
    member.create_system = 3
    member.external_attr = (file_type | 0o644) << 16
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr(member, _valid_store_csv())

    with pytest.raises(pipeline.ArchiveValidationError, match=message):
        pipeline.ingest_input(archive_path)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ({"flag_bits": 1}, "criptografado"),
        ({"compression_method": 99}, "compressão"),
    ],
)
def test_rejects_encryption_and_unsupported_compression(
    tmp_path: Path, mutation: dict[str, int], message: str
) -> None:
    """Reject encrypted flags and compression methods outside the allowlist."""

    archive_path = _write_zip(
        tmp_path / "unsupported.zip",
        [("dados/dimensoes/dim_lojas.csv", _valid_store_csv())],
    )
    _mutate_single_member_zip(archive_path, **mutation)

    with pytest.raises(pipeline.ArchiveValidationError, match=message):
        pipeline.ingest_input(archive_path)


def test_rejects_casefold_zip_path_collision(tmp_path: Path) -> None:
    """Reject paths that collide on the case-insensitive Windows filesystem."""

    archive_path = _write_zip(
        tmp_path / "collision.zip",
        [
            ("dados/dimensoes/dim_lojas.csv", _valid_store_csv()),
            ("DADOS/DIMENSOES/DIM_LOJAS.CSV", _valid_store_csv()),
        ],
    )

    with pytest.raises(pipeline.ArchiveValidationError, match="colisão"):
        pipeline.ingest_input(archive_path)


def test_enforces_zip_file_and_size_limits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Apply archive, file-count, member, total, and compression-ratio limits."""

    archive_path = _write_zip(
        tmp_path / "limited.zip",
        [
            ("README.md", "metadata"),
            ("dados/dimensoes/dim_lojas.csv", _valid_store_csv()),
        ],
    )

    monkeypatch.setattr(pipeline, "MAX_ZIP_ARCHIVE_BYTES", 1)
    with pytest.raises(pipeline.ArchiveValidationError, match="limite"):
        pipeline.ingest_input(archive_path)

    monkeypatch.setattr(pipeline, "MAX_ZIP_ARCHIVE_BYTES", 64 * 1024 * 1024)
    monkeypatch.setattr(pipeline, "MAX_ZIP_FILES", 1)
    with pytest.raises(pipeline.ArchiveValidationError, match="limite"):
        pipeline.ingest_input(archive_path)

    monkeypatch.setattr(pipeline, "MAX_ZIP_FILES", 32)
    monkeypatch.setattr(pipeline, "MAX_ZIP_MEMBER_BYTES", 8)
    with pytest.raises(pipeline.ArchiveValidationError, match="limite"):
        pipeline.ingest_input(archive_path)

    monkeypatch.setattr(pipeline, "MAX_ZIP_MEMBER_BYTES", 32 * 1024 * 1024)
    monkeypatch.setattr(pipeline, "MAX_ZIP_UNCOMPRESSED_BYTES", 8)
    with pytest.raises(pipeline.ArchiveValidationError, match="limite"):
        pipeline.ingest_input(archive_path)

    monkeypatch.setattr(pipeline, "MAX_ZIP_UNCOMPRESSED_BYTES", 64 * 1024 * 1024)
    monkeypatch.setattr(pipeline, "MAX_COMPRESSION_RATIO", 0.01)
    with pytest.raises(pipeline.ArchiveValidationError, match="compressão"):
        pipeline.ingest_input(archive_path)


def test_enforces_directory_file_and_size_limits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Apply count, individual-size, and total-size limits to directories."""

    root = tmp_path / "entrada"
    root.mkdir()
    (root / "dim_lojas.csv").write_text(_valid_store_csv(), encoding="utf-8")
    (root / "lojas_extra.csv").write_text(_valid_store_csv(), encoding="utf-8")

    monkeypatch.setattr(pipeline, "MAX_DIRECTORY_ENTRIES", 1)
    with pytest.raises(pipeline.InputValidationError, match="limite"):
        pipeline.ingest_input(root)

    monkeypatch.setattr(pipeline, "MAX_DIRECTORY_ENTRIES", 32)
    monkeypatch.setattr(pipeline, "MAX_ZIP_MEMBER_BYTES", 8)
    with pytest.raises(pipeline.InputValidationError, match="limite"):
        pipeline.ingest_input(root)

    monkeypatch.setattr(pipeline, "MAX_ZIP_MEMBER_BYTES", 32 * 1024 * 1024)
    monkeypatch.setattr(pipeline, "MAX_ZIP_UNCOMPRESSED_BYTES", 8)
    with pytest.raises(pipeline.InputValidationError, match="limite"):
        pipeline.ingest_input(root)


def test_directory_entry_limit_bounds_nested_depth(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Bound directory depth by counting directories as discovered entries."""

    root = tmp_path / "entrada"
    deepest = root / "nivel-1" / "nivel-2"
    deepest.mkdir(parents=True)
    (deepest / "dim_lojas.csv").write_text(_valid_store_csv(), encoding="utf-8")
    monkeypatch.setattr(pipeline, "MAX_DIRECTORY_ENTRIES", 2)

    with pytest.raises(pipeline.InputValidationError, match="entradas"):
        pipeline.ingest_input(root)


def test_enforces_actual_copy_limit() -> None:
    """Stop a ZIP stream when actual copied bytes exceed the member limit."""

    source = io.BytesIO(b"123456789")
    destination = io.BytesIO()

    with pytest.raises(pipeline.ArchiveValidationError, match="excede o limite"):
        pipeline._copy_zip_member_limited(source, destination, byte_limit=8)

    assert destination.getvalue() == b""


def test_rejects_corrupt_zip(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Return an expected validation error for a fake ZIP file."""

    archive_path = tmp_path / "corrupt.zip"
    archive_path.write_bytes(b"not a zip")

    with pytest.raises(pipeline.ArchiveValidationError, match="ZIP válido"):
        pipeline.ingest_input(archive_path)

    assert pipeline.main(["inspect", str(archive_path)]) == 3
    assert capsys.readouterr().err.startswith("Erro:")


def test_zip_disappearing_after_path_validation_has_controlled_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Return code 3 if a ZIP disappears between path validation and inspection."""

    archive_path = _write_zip(
        tmp_path / "vanishing.zip",
        [("dados/dimensoes/dim_lojas.csv", _valid_store_csv())],
    )
    original_validate = pipeline._validate_input_path

    def validate_then_remove(path: Path) -> tuple[str, Path]:
        """Model a concurrent removal immediately after path validation."""

        input_kind, resolved = original_validate(path)
        resolved.unlink()
        return input_kind, resolved

    monkeypatch.setattr(pipeline, "_validate_input_path", validate_then_remove)

    assert pipeline.main(["inspect", str(archive_path)]) == 3
    stderr = capsys.readouterr().err
    assert stderr.startswith("Erro:")
    assert "Traceback" not in stderr


def test_rejects_malformed_deflate_as_controlled_archive_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Convert a malformed DEFLATE stream into a clear archive error and code 3."""

    member_name = "dados/dimensoes/dim_lojas.csv"
    archive_path = _write_zip(
        tmp_path / "malformed-deflate.zip",
        [(member_name, _valid_store_csv())],
    )
    with zipfile.ZipFile(archive_path) as archive:
        info = archive.getinfo(member_name)

    payload = bytearray(archive_path.read_bytes())
    local_header = struct.unpack_from("<IHHHHHIIIHH", payload, info.header_offset)
    assert local_header[0] == 0x04034B50
    filename_size, extra_size = local_header[-2:]
    compressed_data_start = info.header_offset + 30 + filename_size + extra_size
    payload[compressed_data_start] |= 0x06
    archive_path.write_bytes(payload)

    with pytest.raises(pipeline.ArchiveValidationError, match="processar o ZIP"):
        pipeline.ingest_input(archive_path)

    assert pipeline.main(["inspect", str(archive_path)]) == 3
    stderr = capsys.readouterr().err
    assert stderr.startswith("Erro:")
    assert "Traceback" not in stderr


def test_rejects_crc_failure_before_temporary_extraction(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Reject a CRC mismatch before creating an extraction directory."""

    archive_path = _write_zip(
        tmp_path / "bad-crc.zip",
        [("dados/dimensoes/dim_lojas.csv", _valid_store_csv())],
    )
    with zipfile.ZipFile(archive_path) as archive:
        [info] = archive.infolist()
    _mutate_single_member_zip(archive_path, crc=info.CRC ^ 0xFFFFFFFF)

    def forbid_temporary_directory(*args: object, **kwargs: object) -> None:
        """Fail if CRC validation reaches temporary extraction."""

        pytest.fail(f"TemporaryDirectory chamado: args={args}, kwargs={kwargs}")

    monkeypatch.setattr(
        pipeline.tempfile,
        "TemporaryDirectory",
        forbid_temporary_directory,
    )

    with pytest.raises(pipeline.ArchiveValidationError, match="CRC"):
        pipeline.ingest_input(archive_path)


def test_csv_schema_error_uses_exit_code_four(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Return the documented CSV-specific exit code for schema rejection."""

    csv_path = tmp_path / "dim_lojas.csv"
    csv_path.write_text(_csv_text(STORE_SCHEMA[:-1], []), encoding="utf-8")

    assert pipeline.main(["inspect", str(csv_path)]) == 4
    assert "Schema" in capsys.readouterr().err


def test_zip_temporary_directory_is_removed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Remove temporary extraction directories after success and validation failure."""

    temporary_parent = tmp_path / "temporary"
    temporary_parent.mkdir()
    monkeypatch.setattr(pipeline.tempfile, "tempdir", str(temporary_parent))

    valid_archive = _write_zip(
        tmp_path / "valid.zip",
        [("dados/dimensoes/dim_lojas.csv", _valid_store_csv())],
    )
    pipeline.ingest_input(valid_archive)
    assert list(temporary_parent.iterdir()) == []

    invalid_archive = _write_zip(
        tmp_path / "invalid-schema.zip",
        [
            (
                "dados/dimensoes/dim_lojas.csv",
                _csv_text(STORE_SCHEMA[:-1], []),
            )
        ],
    )
    with pytest.raises(pipeline.CsvValidationError):
        pipeline.ingest_input(invalid_archive)
    assert list(temporary_parent.iterdir()) == []


def test_ingestion_does_not_modify_original_zip(tmp_path: Path) -> None:
    """Preserve the original archive bytes, size, and modification time."""

    archive_path = _write_zip(
        tmp_path / "original.zip",
        [("dados/dimensoes/dim_lojas.csv", _valid_store_csv())],
    )
    before = (
        _sha256(archive_path),
        archive_path.stat().st_size,
        archive_path.stat().st_mtime_ns,
    )

    pipeline.ingest_input(archive_path)

    after = (
        _sha256(archive_path),
        archive_path.stat().st_size,
        archive_path.stat().st_mtime_ns,
    )
    assert after == before
    assert not list(tmp_path.glob("*.duckdb"))


def test_csv_and_directory_ingestion_preserve_original_bytes_and_size(
    tmp_path: Path,
) -> None:
    """Preserve a CSV when it is read directly and through its directory."""

    root = tmp_path / "entrada"
    root.mkdir()
    csv_path = root / "dim_lojas.csv"
    csv_path.write_text(_valid_store_csv(), encoding="utf-8")
    before = (_sha256(csv_path), csv_path.stat().st_size)

    pipeline.ingest_input(csv_path)
    pipeline.ingest_input(root)

    assert (_sha256(csv_path), csv_path.stat().st_size) == before
    assert not list(root.rglob("*.duckdb"))


def test_main_success_prints_calculated_inspection(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Print calculated metadata rather than hardcoded discovery numbers."""

    csv_path = tmp_path / "pasta com espaços" / "dim_lojas.csv"
    csv_path.parent.mkdir()
    csv_path.write_text(_valid_store_csv(), encoding="utf-8")

    exit_code = pipeline.main(["inspect", str(csv_path)])
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert output["total_files"] == 1
    assert output["total_rows"] == 1
    assert output["files"][0]["source_file"] == "dim_lojas.csv"
    assert output["files"][0]["headers"] == list(STORE_SCHEMA)
    assert output["files"][0]["delimiter"] == ";"
