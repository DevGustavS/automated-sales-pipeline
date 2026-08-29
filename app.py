from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
INCOMING_DIR = ROOT / "data" / "incoming"
PIPELINE_SCRIPT = ROOT / "build_pipeline.py"
DASHBOARD_SCRIPT = ROOT / "dashboard.py"


def find_zip(requested_name: str | None = None) -> Path:
    """Resolve an explicit ZIP or select the only ZIP in the input directory.

    Automatic selection is intentionally limited to one available ZIP. When
    multiple inputs exist, the caller must choose one with ``--zip``.
    """

    if not INCOMING_DIR.exists():
        raise FileNotFoundError(f"Pasta de entrada não encontrada: {INCOMING_DIR}")

    zip_files = sorted(
        INCOMING_DIR.glob("*.zip"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )

    if requested_name:
        requested = Path(requested_name)

        if requested.is_absolute():
            candidate = requested
        elif requested.parent != Path("."):
            candidate = (ROOT / requested).resolve()
        else:
            candidate = INCOMING_DIR / requested.name

        if not candidate.exists():
            raise FileNotFoundError(f"ZIP não encontrado: {candidate}")

        if candidate.suffix.lower() != ".zip":
            raise ValueError(f"O arquivo informado não é ZIP: {candidate}")

        return candidate

    if not zip_files:
        raise FileNotFoundError(f"Nenhum arquivo .zip encontrado em {INCOMING_DIR}")

    if len(zip_files) == 1:
        return zip_files[0]

    available = ", ".join(path.name for path in zip_files)
    raise ValueError(
        f"{len(zip_files)} ZIPs encontrados em {INCOMING_DIR}. "
        f"Informe --zip explicitamente. Disponíveis: {available}"
    )


def run_pipeline(zip_path: Path) -> None:
    """Run the pipeline for the selected ZIP and propagate command failures."""

    print(f"[app] Entrada selecionada: {zip_path.name}")
    print("[app] Executando pipeline...")

    subprocess.run(
        [sys.executable, str(PIPELINE_SCRIPT), str(zip_path)],
        cwd=ROOT,
        check=True,
    )

    print("[app] Pipeline concluído com sucesso.")


def open_dashboard() -> None:
    """Start the local Streamlit dashboard after a successful pipeline run."""

    print("[app] Abrindo dashboard...")

    subprocess.run(
        [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            str(DASHBOARD_SCRIPT),
            "--server.headless=false",
        ],
        cwd=ROOT,
        check=True,
    )


def list_zips() -> None:
    """Print the ZIP files currently available in the input directory."""

    if not INCOMING_DIR.exists():
        print(f"Pasta não encontrada: {INCOMING_DIR}")
        return

    zip_files = sorted(
        INCOMING_DIR.glob("*.zip"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )

    if not zip_files:
        print("Nenhum ZIP encontrado.")
        return

    print("ZIPs disponíveis:")
    for index, path in enumerate(zip_files, start=1):
        print(f"{index}. {path.name}")


def parse_args() -> argparse.Namespace:
    """Parse the launcher command-line arguments."""

    parser = argparse.ArgumentParser(
        description=(
            "Executa o Automated Sales Pipeline com um ZIP de "
            "data/incoming/ e abre o dashboard Streamlit."
        )
    )
    parser.add_argument(
        "--zip",
        dest="zip_name",
        help=(
            "ZIP específico a processar. Se omitido, a pasta deve conter "
            "exatamente um ZIP."
        ),
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="Lista os ZIPs disponíveis e encerra.",
    )
    return parser.parse_args()


def main() -> int:
    """Run the selected pipeline input and open the dashboard on success."""

    args = parse_args()

    if args.list:
        list_zips()
        return 0

    if not PIPELINE_SCRIPT.exists():
        print(f"[erro] Não encontrado: {PIPELINE_SCRIPT}")
        return 1

    if not DASHBOARD_SCRIPT.exists():
        print(f"[erro] Não encontrado: {DASHBOARD_SCRIPT}")
        return 1

    try:
        zip_path = find_zip(args.zip_name)
        run_pipeline(zip_path)
        open_dashboard()
        return 0

    except subprocess.CalledProcessError as exc:
        print(
            f"[erro] Um comando terminou com código {exc.returncode}. "
            "O dashboard não será iniciado se o pipeline falhar."
        )
        return exc.returncode or 1

    except (FileNotFoundError, ValueError) as exc:
        print(f"[erro] {exc}")
        return 1

    except KeyboardInterrupt:
        print("\n[app] Encerrado pelo usuário.")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
