from __future__ import annotations

from pathlib import Path

import pytest

import app


def test_find_zip_rejects_empty_input_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    incoming = tmp_path / "incoming"
    incoming.mkdir()
    monkeypatch.setattr(app, "INCOMING_DIR", incoming)

    with pytest.raises(FileNotFoundError, match="Nenhum arquivo .zip"):
        app.find_zip()


def test_find_zip_selects_the_only_available_zip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    incoming = tmp_path / "incoming"
    incoming.mkdir()
    only_zip = incoming / "sales.zip"
    only_zip.touch()
    monkeypatch.setattr(app, "INCOMING_DIR", incoming)

    assert app.find_zip() == only_zip


def test_find_zip_requires_explicit_choice_for_multiple_zips(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    incoming = tmp_path / "incoming"
    incoming.mkdir()
    first_zip = incoming / "first.zip"
    second_zip = incoming / "second.zip"
    first_zip.touch()
    second_zip.touch()
    monkeypatch.setattr(app, "INCOMING_DIR", incoming)

    with pytest.raises(ValueError, match="Informe --zip explicitamente"):
        app.find_zip()

    assert app.find_zip(second_zip.name) == second_zip
