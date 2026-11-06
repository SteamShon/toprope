"""The kernel's command reference is generated from its parsers and kept current (ADR-0037)."""
import re
from pathlib import Path

import pytest

from toprope.kernel.reference import build_reference, main

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs/kernel-commands.md"


def test_the_committed_reference_is_the_generated_one():
    assert DOC.read_text() == build_reference(), \
        "docs/kernel-commands.md is stale: run python -m toprope.kernel.reference --out docs/kernel-commands.md"


def test_every_installed_command_is_in_the_reference():
    scripts = re.search(r"\[project\.scripts\]\n(.*?)\n\n", (ROOT / "pyproject.toml").read_text(), re.S).group(1)
    names = {line.split("=")[0].strip() for line in scripts.splitlines() if "=" in line}
    documented = set(re.findall(r"^## `([a-z-]+)`$", build_reference(), re.M))
    assert names == documented


def test_check_reports_a_stale_file(tmp_path, capsys):
    stale = tmp_path / "k.md"
    stale.write_text(build_reference() + "edited by hand\n")
    with pytest.raises(SystemExit) as e:
        main(["--check", str(stale)])
    assert e.value.code == 1 and "stale" in capsys.readouterr().err
    main(["--out", str(stale)])
    main(["--check", str(stale)])
