from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
INCOMING_DIR = ROOT / "data" / "incoming"
PIPELINE_SCRIPT = ROOT / "build_pipeline.py"
DASHBOARD_SCRIPT = ROOT / "dashboard.py"


def discover_zips() -> list[Path]:
    """Return available ZIP files ordered from newest to oldest."""

    if not INCOMING_DIR.exists():
        raise FileNotFoundError(f"Pasta de entrada não encontrada: {INCOMING_DIR}")

    return sorted(
        INCOMING_DIR.glob("*.zip"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )


def select_zip_interactively(zip_files: list[Path]) -> Path | None:
    """Prompt for one ZIP and return ``None`` when the user chooses to exit."""

    print("\nAutomated Sales Pipeline\n")
    print("Selecione o arquivo que deseja processar:\n")
    for index, path in enumerate(zip_files, start=1):
        print(f"[{index}] {path.name}")
    print("\n[0] Sair\n")

    while True:
        try:
            choice = int(input("Digite o número do arquivo: "))
        except ValueError:
            choice = -1

        if choice == 0:
            return None
        if 1 <= choice <= len(zip_files):
            return zip_files[choice - 1]

        print(f"Opção inválida. Escolha um número entre 0 e {len(zip_files)}.")


def find_zip(requested_name: str | None = None) -> Path | None:
    """Resolve an explicit ZIP or select an available ZIP for manual use."""

    zip_files = discover_zips()

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

    return select_zip_interactively(zip_files)


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

    try:
        zip_files = discover_zips()
    except FileNotFoundError as exc:
        print(exc)
        return

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
            "ZIP específico a processar. Se omitido e houver vários ZIPs, "
            "será exibido um menu para seleção."
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
        if zip_path is None:
            print("[app] Execução cancelada.")
            return 0
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
