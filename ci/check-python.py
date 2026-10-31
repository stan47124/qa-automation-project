"""Validate the bootstrap interpreter and an existing workspace venv without changes."""

import os
from pathlib import Path
import subprocess
import sys


def normalized(path):
    return os.path.normcase(os.path.realpath(path))


def main():
    if "windowsapps" in str(Path(sys.executable).resolve()).lower():
        raise SystemExit("WindowsApps Python is not allowed; select an installed interpreter.")
    print(f"Bootstrap Python: {sys.executable} ({sys.version.split()[0]})", flush=True)
    venv_python = Path(__file__).resolve().parents[1] / ".venv/Scripts/python.exe"
    if venv_python.is_file():
        base_prefix = subprocess.check_output(
            [str(venv_python), "-c", "import sys; print(sys.base_prefix)"], text=True
        ).strip()
        if normalized(base_prefix) != normalized(sys.prefix):
            raise SystemExit(
                "Existing .venv uses another Python installation. Use a new Jenkins workspace; "
                "the environment will not be overwritten."
            )


if __name__ == "__main__":
    main()
