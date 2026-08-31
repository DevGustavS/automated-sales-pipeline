from __future__ import annotations

from argparse import Namespace
from pathlib import Path

import pytest

import app


def _create_incoming(tmp_path: Path, *names: str) -> tuple[Path, ...]:
    incoming = tmp_path / "incoming"
    incoming.mkdir()
    paths = tuple(incoming / name for name in names)
    for path in paths:
        path.touch()
    return paths


def test_find_zip_rejects_empty_input_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _create_incoming(tmp_path)
    monkeypatch.setattr(app, "INCOMING_DIR", tmp_path / "incoming")

    with pytest.raises(FileNotFoundError, match="Nenhum arquivo .zip"):
        app.find_zip()


def test_find_zip_selects_the_only_available_zip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (only_zip,) = _create_incoming(tmp_path, "sales.zip")
    monkeypatch.setattr(app, "INCOMING_DIR", tmp_path / "incoming")

    assert app.find_zip() == only_zip


def test_find_zip_uses_interactive_selection_for_multiple_zips(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first_zip, second_zip = _create_incoming(tmp_path, "first.zip", "second.zip")
    monkeypatch.setattr(app, "INCOMING_DIR", tmp_path / "incoming")
    selected_from: list[list[Path]] = []

    def choose(zip_files: list[Path]) -> Path:
        selected_from.append(zip_files)
        return second_zip

    monkeypatch.setattr(app, "select_zip_interactively", choose)

    assert app.find_zip() == second_zip
    assert set(selected_from[0]) == {first_zip, second_zip}


def test_interactive_selection_accepts_valid_choice(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    first_zip, second_zip = _create_incoming(tmp_path, "first.zip", "second.zip")
    monkeypatch.setattr("builtins.input", lambda _prompt: "2")

    assert app.select_zip_interactively([first_zip, second_zip]) == second_zip
    output = capsys.readouterr().out
    assert "Automated Sales Pipeline" in output
    assert "[1] first.zip" in output
    assert "[2] second.zip" in output
    assert "[0] Sair" in output


def test_interactive_selection_retries_invalid_values_then_accepts_choice(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    first_zip, second_zip, third_zip = _create_incoming(
        tmp_path, "first.zip", "second.zip", "third.zip"
    )
    answers = iter(["", "texto", "-1", "4", "2"])
    monkeypatch.setattr("builtins.input", lambda _prompt: next(answers))

    selected = app.select_zip_interactively([first_zip, second_zip, third_zip])

    assert selected == second_zip
    assert (
        capsys.readouterr().out.count("Opção inválida. Escolha um número entre 0 e 3.")
        == 4
    )


def test_interactive_selection_zero_cancels(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first_zip, second_zip = _create_incoming(tmp_path, "first.zip", "second.zip")
    monkeypatch.setattr("builtins.input", lambda _prompt: "0")

    assert app.select_zip_interactively([first_zip, second_zip]) is None


def test_find_zip_explicit_choice_skips_interactive_menu(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first_zip, _second_zip = _create_incoming(tmp_path, "first.zip", "second.zip")
    monkeypatch.setattr(app, "INCOMING_DIR", tmp_path / "incoming")

    def fail_if_called(_zip_files: list[Path]) -> Path:
        raise AssertionError("O menu não deve abrir com --zip")

    monkeypatch.setattr(app, "select_zip_interactively", fail_if_called)

    assert app.find_zip(first_zip.name) == first_zip


def test_find_zip_rejects_missing_explicit_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _create_incoming(tmp_path)
    monkeypatch.setattr(app, "INCOMING_DIR", tmp_path / "incoming")

    with pytest.raises(FileNotFoundError, match="ZIP não encontrado"):
        app.find_zip("missing.zip")


def test_find_zip_rejects_explicit_non_zip_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (text_file,) = _create_incoming(tmp_path, "notes.txt")
    monkeypatch.setattr(app, "INCOMING_DIR", tmp_path / "incoming")

    with pytest.raises(ValueError, match="não é ZIP"):
        app.find_zip(text_file.name)


def test_list_zips_prints_available_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _create_incoming(tmp_path, "first.zip", "second.zip")
    monkeypatch.setattr(app, "INCOMING_DIR", tmp_path / "incoming")

    app.list_zips()

    output = capsys.readouterr().out
    assert "ZIPs disponíveis:" in output
    assert "first.zip" in output
    assert "second.zip" in output


def test_main_list_only_lists_and_exits(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(app, "parse_args", lambda: Namespace(list=True, zip_name=None))
    monkeypatch.setattr(app, "list_zips", lambda: calls.append("list"))
    monkeypatch.setattr(
        app,
        "find_zip",
        lambda _requested: pytest.fail("A seleção não deveria ser executada"),
    )

    assert app.main() == 0
    assert calls == ["list"]


def test_main_cancellation_does_not_run_pipeline_or_dashboard(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(app, "parse_args", lambda: Namespace(list=False, zip_name=None))
    monkeypatch.setattr(app, "find_zip", lambda _requested: None)
    monkeypatch.setattr(
        app,
        "run_pipeline",
        lambda _path: pytest.fail("O pipeline não deveria ser executado"),
    )
    monkeypatch.setattr(
        app,
        "open_dashboard",
        lambda: pytest.fail("O dashboard não deveria ser aberto"),
    )

    assert app.main() == 0
    assert "Execução cancelada" in capsys.readouterr().out


def test_main_empty_directory_does_not_run_pipeline_or_dashboard(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _create_incoming(tmp_path)
    monkeypatch.setattr(app, "INCOMING_DIR", tmp_path / "incoming")
    monkeypatch.setattr(app, "parse_args", lambda: Namespace(list=False, zip_name=None))
    monkeypatch.setattr(
        app,
        "run_pipeline",
        lambda _path: pytest.fail("O pipeline não deveria ser executado"),
    )
    monkeypatch.setattr(
        app,
        "open_dashboard",
        lambda: pytest.fail("O dashboard não deveria ser aberto"),
    )

    assert app.main() == 1
    assert "Nenhum arquivo .zip" in capsys.readouterr().out


def test_main_keyboard_interrupt_has_no_traceback_or_subprocess(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _create_incoming(tmp_path, "first.zip", "second.zip")
    monkeypatch.setattr(app, "INCOMING_DIR", tmp_path / "incoming")
    monkeypatch.setattr(app, "parse_args", lambda: Namespace(list=False, zip_name=None))

    def interrupt(_prompt: str) -> str:
        raise KeyboardInterrupt

    monkeypatch.setattr("builtins.input", interrupt)
    monkeypatch.setattr(
        app,
        "run_pipeline",
        lambda _path: pytest.fail("O pipeline não deveria ser executado"),
    )
    monkeypatch.setattr(
        app,
        "open_dashboard",
        lambda: pytest.fail("O dashboard não deveria ser aberto"),
    )

    assert app.main() == 130
    assert "Encerrado pelo usuário" in capsys.readouterr().out
