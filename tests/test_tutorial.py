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
    assert "OLDPWD" not in script
    out = subprocess.run(["bash", "-euo", "pipefail", "-c", script], cwd=ROOT, capture_output=True, text=True,
                         timeout=600)
    assert out.returncode == 0, out.stdout[-2000:] + out.stderr[-2000:]
    text = out.stdout
    assert "denied: Access to prod is approved by security." in text                      # step 2
    assert '"code": "actor"' in text and "refused, as it should be" in text             # step 3
    assert '"type": "AccessRequestApproveRequest"' in text and '"type": "DecisionRecorded"' in text  # step 3, history
    assert "prod_approver: security -> manager" in text                                  # step 4
    assert "the story now ends differently: max (manager) asks to approve it -> ok" in text
    assert "prod_approver: manager -> security" in text                                 # set back


@pytest.mark.skipif(shutil.which("uv") is None, reason="the README's commands run with uv")
def test_the_readmes_first_commands_run_as_written(tmp_path):
    readme = (ROOT / "README.md").read_text()
    head = readme[readme.index("## Try it"):readme.index("### A worked example")]
    (script,) = re.findall(r"```bash\n(.*?)```", head, re.S)
    out = subprocess.run(["bash", "-euo", "pipefail", "-c", script.replace("--dir /tmp", f"--dir {tmp_path}")
                          .replace("cd /tmp/my-access", f"cd {tmp_path}/my-access")],
                         cwd=ROOT, capture_output=True, text=True, timeout=300)
    assert out.returncode == 0, out.stderr[-2000:]
    for line in re.findall(r"```\n(.*?)```", head, re.S)[0].splitlines():
        if line.strip() and line.strip() != "...":
            assert line.rstrip() in out.stdout, line          # the excerpt is the real output
    assert not (ROOT / "my-access").exists()
