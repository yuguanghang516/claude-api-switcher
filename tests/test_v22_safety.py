"""v2.3 安全快速启动回归测试。"""
import ast
import json
from pathlib import Path

import pytest

import app.claude_launcher as launcher_module
import app.path_resolver as resolver_module
from app.claude_launcher import ClaudeLauncher
from app.config_manager import ConfigManager
from app.i18n import TEXTS
from app.provider_manager import ProviderManager
from app.path_resolver import ClaudeCommandResolver, ProjectDirectoryResolver
from main import get_state_dir, migrate_legacy_config


def _mock_which(name):
    """模拟 Windows Terminal 和 cmd.exe 都存在。"""
    if name in ("wt.exe", "cmd.exe"):
        return name
    return None


def test_launcher_keeps_key_out_of_command_and_temp_files(tmp_path, monkeypatch):
    captured = {}
    secret = "SENSITIVE_SENTINEL"
    claude_path = tmp_path / "claude.cmd"
    claude_path.write_text("@echo off", encoding="utf-8")
    before = set(tmp_path.iterdir())
    monkeypatch.setattr(launcher_module.shutil, "which", _mock_which)

    def fake_popen(command, **kwargs):
        captured["command"] = command
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(launcher_module.subprocess, "Popen", fake_popen)
    ok, _ = ClaudeLauncher.launch(
        "Unit", "https://unit.invalid/anthropic", secret, "unit-model", "", str(tmp_path),
        claude_path=str(claude_path),
    )

    assert ok is True
    assert secret not in " ".join(captured["command"])
    assert captured["env"]["ANTHROPIC_AUTH_TOKEN"] == secret
    assert captured["env"]["CLAUDE_SWITCHER_CLAUDE_PATH"] == str(claude_path)
    assert captured["cwd"] == str(tmp_path)
    assert set(tmp_path.iterdir()) == before


def test_launcher_uses_x_api_key_without_inherited_bearer(tmp_path, monkeypatch):
    captured = {}
    claude_path = tmp_path / "claude.cmd"
    claude_path.write_text("@echo off", encoding="utf-8")
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "old-bearer")
    monkeypatch.setattr(launcher_module.shutil, "which", _mock_which)
    monkeypatch.setattr(
        launcher_module.subprocess,
        "Popen",
        lambda command, **kwargs: captured.update(command=command, **kwargs),
    )

    ok, _ = ClaudeLauncher.launch(
        "Unit", "https://unit.invalid/anthropic", "new-key", "unit-model", "",
        str(tmp_path), claude_path=str(claude_path), auth_mode="x-api-key",
    )

    assert ok is True
    assert captured["env"]["ANTHROPIC_API_KEY"] == "new-key"
    assert captured["env"]["ANTHROPIC_AUTH_TOKEN"] == ""
    assert "new-tab" in captured["command"]


def test_launcher_uses_bearer_without_inherited_x_api_key(tmp_path, monkeypatch):
    captured = {}
    claude_path = tmp_path / "claude.cmd"
    claude_path.write_text("@echo off", encoding="utf-8")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "old-x-api-key")
    monkeypatch.setattr(launcher_module.shutil, "which", _mock_which)
    monkeypatch.setattr(
        launcher_module.subprocess,
        "Popen",
        lambda command, **kwargs: captured.update(command=command, **kwargs),
    )

    ok, _ = ClaudeLauncher.launch(
        "Unit", "https://unit.invalid/anthropic", "new-token", "unit-model", "",
        str(tmp_path), claude_path=str(claude_path), auth_mode="bearer",
    )

    assert ok is True
    assert captured["env"]["ANTHROPIC_AUTH_TOKEN"] == "new-token"
    assert captured["env"]["ANTHROPIC_API_KEY"] == ""


def test_project_resolver_prefers_manual_directory(tmp_path):
    manual = tmp_path / "manual"
    recent = tmp_path / "recent"
    manual.mkdir()
    recent.mkdir()
    claude_json = tmp_path / ".claude.json"
    claude_json.write_text(json.dumps({"projects": {
        str(recent): {"lastStartTime": 9999}
    }}), encoding="utf-8")
    result = ProjectDirectoryResolver(str(tmp_path), str(claude_json)).resolve(str(manual))
    assert result.path == str(manual)
    assert result.source == "manual"


def test_project_resolver_uses_most_recent_existing_project(tmp_path):
    older = tmp_path / "older"
    newest = tmp_path / "newest"
    missing = tmp_path / "missing"
    older.mkdir()
    newest.mkdir()
    claude_json = tmp_path / ".claude.json"
    claude_json.write_text(json.dumps({"projects": {
        str(older): {"lastStartTime": 10},
        str(missing): {"lastStartTime": 999},
        str(newest): {"lastStartTime": 20},
    }}), encoding="utf-8")
    result = ProjectDirectoryResolver(str(tmp_path), str(claude_json)).resolve()
    assert result.path == str(newest)
    assert result.source == "recent"


def test_project_resolver_corrupt_json_falls_back_to_home(tmp_path):
    claude_json = tmp_path / ".claude.json"
    claude_json.write_text("not json", encoding="utf-8")
    result = ProjectDirectoryResolver(str(tmp_path), str(claude_json)).resolve()
    assert result.path == str(tmp_path)
    assert result.source == "home"


@pytest.mark.parametrize("payload", ["[]", "null", '"text"'])
def test_project_resolver_non_object_json_falls_back_to_home(tmp_path, payload):
    claude_json = tmp_path / ".claude.json"
    claude_json.write_text(payload, encoding="utf-8")

    result = ProjectDirectoryResolver(str(tmp_path), str(claude_json)).resolve()

    assert result.path == str(tmp_path)
    assert result.source == "home"


@pytest.mark.parametrize("value", [float("nan"), float("inf"), "nan", "inf"])
def test_project_resolver_rejects_non_finite_timestamps(value):
    assert ProjectDirectoryResolver._timestamp(value) is None


def test_claude_command_resolver_prefers_cmd_on_path(tmp_path, monkeypatch):
    cmd = tmp_path / "claude.cmd"
    exe = tmp_path / "claude.exe"
    cmd.write_text("", encoding="utf-8")
    exe.write_text("", encoding="utf-8")
    paths = {"claude.cmd": str(cmd), "claude.exe": str(exe)}
    monkeypatch.setattr(resolver_module.shutil, "which", lambda name: paths.get(name))
    assert ClaudeCommandResolver.resolve() == str(cmd)


def test_claude_command_resolver_falls_back_to_npm(tmp_path, monkeypatch):
    npm = tmp_path / "npm"
    npm.mkdir()
    cmd = npm / "claude.cmd"
    cmd.write_text("", encoding="utf-8")
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setattr(resolver_module.shutil, "which", lambda _name: None)
    assert ClaudeCommandResolver.resolve() == str(cmd)


def test_remote_http_provider_is_rejected(tmp_path, monkeypatch):
    manager = ProviderManager(ConfigManager(str(tmp_path / "data")))
    monkeypatch.setattr(manager.cred, "save_api_key", lambda *_args: True)
    ok, message = manager.add_or_update_provider(
        "Unsafe", "http://example.com/anthropic", "model", "", "secret"
    )
    assert ok is False
    assert "HTTPS" in message


def test_imported_same_name_cannot_reuse_legacy_credential(tmp_path, monkeypatch):
    config = ConfigManager(str(tmp_path / "data"))
    manager = ProviderManager(config)
    store = {"LongCat": "SENSITIVE_SENTINEL"}
    monkeypatch.setattr(manager.cred, "get_api_key", lambda key: store.get(key, ""))
    monkeypatch.setattr(manager.cred, "save_api_key", lambda key, value: store.setdefault(key, value) is not None)
    source = tmp_path / "import.json"
    source.write_text(json.dumps({"providers": [{
        "name": "LongCat", "base_url": "https://different.invalid/anthropic",
        "model": "different-model", "enabled": True,
    }]}), encoding="utf-8")

    ok, _ = manager.import_config(str(source))
    assert ok is True
    imported = manager.get_provider_detail("LongCat")
    assert imported["api_key"] == ""
    assert imported["id"] != "LongCat"


def test_runtime_state_uses_local_app_data(tmp_path, monkeypatch):
    monkeypatch.delenv("CLAUDE_SWITCHER_DATA_DIR", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert get_state_dir() == str(tmp_path / "ClaudeAPISwitcher")


def test_legacy_config_migration_only_copies_config(tmp_path):
    legacy = tmp_path / "legacy"
    (legacy / "data").mkdir(parents=True)
    (legacy / "logs").mkdir()
    (legacy / "data" / "config.json").write_text('{"providers": []}', encoding="utf-8")
    (legacy / "logs" / "private.log").write_text("private", encoding="utf-8")
    target = tmp_path / "state" / "data"
    migrate_legacy_config(str(legacy), str(target))
    assert (target / "config.json").exists()
    assert not (tmp_path / "state" / "logs" / "private.log").exists()


def test_gui_static_translation_keys_exist():
    source = Path(__file__).parents[1] / "app" / "gui.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    keys = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not node.args:
            continue
        if isinstance(node.func, ast.Name) and node.func.id == "t":
            if isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                keys.add(node.args[0].value)
        if isinstance(node.func, ast.Attribute) and node.func.attr == "_bind_text":
            if len(node.args) > 1 and isinstance(node.args[1], ast.Constant):
                keys.add(node.args[1].value)
    assert keys <= set(TEXTS)
