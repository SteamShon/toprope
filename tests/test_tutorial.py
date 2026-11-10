"""The tutorial's commands run, in order, and say what the page says (ADR-0049, E2)."""
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "docs/tutorial.md"


def blocks() -> list[str]:
    return re.findall(r"```bash\n(.*?)```", PAGE.read_text(), re.S)


@pytest.mark.skipif(shutil.which("uv") is None, reason="the tutorial runs commands with uv")
def test_the_tutorial_runs_as_written(tmp_path):
    script = "\n".join(b for b in blocks() if not b.strip().startswith("uv sync"))
    script = script.replace("/tmp/toprope-tutorial", str(tmp_path))
    out = subprocess.run(["bash", "-euo", "pipefail", "-c", script], cwd=ROOT, capture_output=True, text=True,
                         timeout=600)
    assert out.returncode == 0, out.stdout[-2000:] + out.stderr[-2000:]
    text = out.stdout
    assert "denied: Access to prod is approved by security." in text                      # step 2
    assert "Only a person can approve_request." in text                                  # step 3
    assert "prod_approver: security -> manager" in text                                  # step 4
    assert "the story now ends differently: max (manager) asks to approve it -> ok" in text


def test_the_readme_starts_with_the_same_two_commands():
    readme = (ROOT / "README.md").read_text()
    head = readme[readme.index("## Try it"):readme.index("### A worked example")]
    assert "toprope-init my-access --template approval" in head and "toprope-try" in head
    assert "denied: Access to prod is approved by security." in head
