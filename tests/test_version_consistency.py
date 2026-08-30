import re
import shutil
import subprocess
import sys
from pathlib import Path

from scripts.check_version_consistency import check_version_consistency


REPO_ROOT = Path(__file__).resolve().parents[1]
VERSION_FILES = (
    Path("app/version.py"),
    Path("build.spec"),
    Path("version_info.txt"),
    Path("README.md"),
)


def test_repository_versions_are_consistent():
    assert check_version_consistency(REPO_ROOT) == []


def test_script_runs_directly():
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts/check_version_consistency.py")],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "Version consistency check passed" in result.stdout


def test_readme_version_mismatch_is_reported(tmp_path):
    for relative_path in VERSION_FILES:
        destination = tmp_path / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPO_ROOT / relative_path, destination)

    readme = tmp_path / "README.md"
    text = readme.read_text(encoding="utf-8")
    mismatched, replacements = re.subn(
        r"(?m)^# Claude API Switcher V\d+\.\d+\.\d+\s*$",
        "# Claude API Switcher V9.9.9",
        text,
        count=1,
    )
    assert replacements == 1
    readme.write_text(mismatched, encoding="utf-8")

    errors = check_version_consistency(tmp_path)
    assert any("README.md title" in error and "9.9.9" in error for error in errors)
