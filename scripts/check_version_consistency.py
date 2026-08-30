#!/usr/bin/env python3
"""Verify that every release-facing file uses the application version."""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path
from typing import Iterable


SEMVER_PATTERN = r"\d+\.\d+\.\d+"
REQUIRED_FILES = (
    Path("app/version.py"),
    Path("build.spec"),
    Path("version_info.txt"),
    Path("README.md"),
)


def _read_text(root: Path, relative_path: Path, errors: list[str]) -> str:
    path = root / relative_path
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        errors.append(f"{relative_path.as_posix()}: cannot read file ({exc})")
        return ""


def _app_versions(source: str, errors: list[str]) -> tuple[str, str]:
    try:
        tree = ast.parse(source, filename="app/version.py")
    except SyntaxError as exc:
        errors.append(f"app/version.py: invalid Python ({exc.msg})")
        return "", ""

    values: dict[str, str] = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name) or target.id not in {
            "APP_VERSION", "APP_VERSION_NAME"
        }:
            continue
        if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            values[target.id] = node.value.value

    version = values.get("APP_VERSION", "")
    version_name = values.get("APP_VERSION_NAME", "")
    if not version:
        errors.append("app/version.py: APP_VERSION string assignment is missing")
    elif not re.fullmatch(SEMVER_PATTERN, version):
        errors.append(f"app/version.py: APP_VERSION is not x.y.z ({version!r})")
    if not version_name:
        errors.append("app/version.py: APP_VERSION_NAME string assignment is missing")
    elif version and version_name != f"V{version}":
        errors.append(
            "app/version.py: APP_VERSION_NAME must equal "
            f"V{version}, found {version_name!r}"
        )
    return version, version_name


def _expect_values(
    errors: list[str], label: str, values: Iterable[str], expected: str,
) -> None:
    found = list(values)
    if not found:
        errors.append(f"{label}: version marker is missing")
        return
    mismatches = sorted({value for value in found if value != expected})
    if mismatches:
        errors.append(
            f"{label}: expected {expected!r}, found {', '.join(map(repr, mismatches))}"
        )


def check_version_consistency(root: Path | str) -> list[str]:
    """Return human-readable consistency errors for a repository root."""
    root = Path(root).resolve()
    errors: list[str] = []
    texts = {
        relative: _read_text(root, relative, errors)
        for relative in REQUIRED_FILES
    }
    version, _version_name = _app_versions(
        texts[Path("app/version.py")], errors
    )
    if not version:
        return errors

    build_text = texts[Path("build.spec")]
    _expect_values(
        errors,
        "build.spec branded names",
        re.findall(rf"Claude API Switcher V({SEMVER_PATTERN})", build_text),
        version,
    )
    _expect_values(
        errors,
        "build.spec product_version",
        re.findall(
            rf"(?m)^\s*product_version\s*=\s*['\"]({SEMVER_PATTERN})['\"]",
            build_text,
        ),
        version,
    )

    version_info_text = texts[Path("version_info.txt")]
    numeric_version = tuple(int(part) for part in version.split(".")) + (0,)
    expected_tuple = ", ".join(str(part) for part in numeric_version)
    for field in ("filevers", "prodvers"):
        matches = re.findall(
            rf"(?m)^\s*{field}\s*=\s*\(([^)]*)\)", version_info_text
        )
        _expect_values(errors, f"version_info.txt {field}", matches, expected_tuple)
    _expect_values(
        errors,
        "version_info.txt FileVersion",
        re.findall(r"StringStruct\('FileVersion',\s*'([^']+)'\)", version_info_text),
        f"{version}.0",
    )
    _expect_values(
        errors,
        "version_info.txt ProductVersion",
        re.findall(r"StringStruct\('ProductVersion',\s*'([^']+)'\)", version_info_text),
        version,
    )
    _expect_values(
        errors,
        "version_info.txt executable name",
        re.findall(
            rf"StringStruct\('OriginalFilename',\s*'Claude API Switcher V({SEMVER_PATTERN})\.exe'\)",
            version_info_text,
        ),
        version,
    )

    readme_text = texts[Path("README.md")]
    _expect_values(
        errors,
        "README.md title",
        re.findall(
            rf"(?m)^# Claude API Switcher V({SEMVER_PATTERN})\s*$", readme_text
        ),
        version,
    )
    _expect_values(
        errors,
        "README.md executable references",
        re.findall(
            rf"Claude API Switcher V({SEMVER_PATTERN})\.exe", readme_text
        ),
        version,
    )
    return errors


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    errors = check_version_consistency(root)
    if errors:
        print("Version consistency check failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    version_source = (root / "app/version.py").read_text(encoding="utf-8")
    version, _ = _app_versions(version_source, [])
    print(f"Version consistency check passed: {version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
