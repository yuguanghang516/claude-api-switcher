from pathlib import Path
from types import SimpleNamespace

import pytest
import requests

from app.gcli2api_manager import (
    DEFAULT_BASE_URL,
    PLACEHOLDER_PASSWORD,
    REPO_URL,
    Gcli2ApiManager,
)


class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = {"data": []} if payload is None else payload

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


@pytest.fixture
def manager(tmp_path):
    instance = Gcli2ApiManager(tmp_path, auto_discover=False)
    instance._version = lambda: ""
    return instance


@pytest.mark.parametrize("url", [
    "http://127.0.0.1:7861",
    "http://localhost:7861/",
    "http://[::1]:7861",
    "https://proxy.example.com",
])
def test_validate_base_url_accepts_safe_addresses(url):
    assert Gcli2ApiManager.validate_base_url(url)


@pytest.mark.parametrize("url", [
    "http://proxy.example.com",
    "ftp://127.0.0.1:7861",
    "http://user:pass@127.0.0.1:7861",
    "http://127.0.0.1:7861?key=secret",
    "",
])
def test_validate_base_url_rejects_unsafe_addresses(url):
    assert not Gcli2ApiManager.validate_base_url(url)


def test_normalizes_default_url(tmp_path):
    item = Gcli2ApiManager(tmp_path, DEFAULT_BASE_URL + "/")
    assert item.base_url == DEFAULT_BASE_URL
    assert item.models_url == DEFAULT_BASE_URL + "/v1/models"


def test_remote_http_raises(tmp_path):
    with pytest.raises(ValueError):
        Gcli2ApiManager(tmp_path, "http://example.com")


def test_managed_path_stays_under_data_dir(manager):
    target = manager._safe_install_dir()
    target.relative_to((manager.data_dir / "integrations").resolve())


def test_discovers_existing_terminal_install(monkeypatch, tmp_path):
    existing = tmp_path / "terminal-install" / "gcli2api"
    (existing / ".venv" / "Scripts").mkdir(parents=True)
    (existing / "web.py").touch()
    (existing / "pyproject.toml").write_text("[project]\nname='gcli2api'", encoding="utf-8")
    (existing / ".venv" / "Scripts" / "python.exe").touch()
    monkeypatch.setenv("GCLI2API_HOME", str(existing))

    discovered = Gcli2ApiManager(tmp_path / "app-data")

    assert discovered.install_dir == existing.resolve()
    assert discovered.install_dir != discovered.managed_install_dir


def test_install_reuses_existing_terminal_install(monkeypatch, tmp_path):
    existing = tmp_path / "gcli2api"
    (existing / ".venv" / "Scripts").mkdir(parents=True)
    (existing / "web.py").touch()
    (existing / "pyproject.toml").touch()
    (existing / ".venv" / "Scripts" / "python.exe").touch()
    monkeypatch.setenv("GCLI2API_HOME", str(existing))
    discovered = Gcli2ApiManager(tmp_path / "app-data")
    monkeypatch.setattr(discovered, "detect_dependencies", lambda: pytest.fail("must not reinstall"))

    ok, message = discovered.install()

    assert ok
    assert "无需重复安装" in message
    assert str(existing.resolve()) in message


def test_start_uses_discovered_terminal_install(monkeypatch, tmp_path):
    existing = tmp_path / "gcli2api"
    python = existing / ".venv" / "Scripts" / "python.exe"
    python.parent.mkdir(parents=True)
    python.touch()
    (existing / "web.py").touch()
    (existing / "pyproject.toml").touch()
    monkeypatch.setenv("GCLI2API_HOME", str(existing))
    discovered = Gcli2ApiManager(tmp_path / "app-data")
    seen = {}

    class FakeProcess:
        pid = 456

        def __init__(self, args):
            self.args = args

        def poll(self):
            return None

    def fake_popen(args, **kwargs):
        seen["args"] = args
        seen.update(kwargs)
        return FakeProcess(args)

    monkeypatch.setattr("app.gcli2api_manager.subprocess.Popen", fake_popen)

    ok, _ = discovered.start("api-password", "panel-password")

    assert ok
    assert Path(seen["args"][0]) == python.resolve()
    assert Path(seen["cwd"]) == existing.resolve()


def test_select_models_prefers_pro_and_flash():
    primary, fast = Gcli2ApiManager.select_models([
        "other", "gemini-2.5-flash", "gemini-3.1-pro-preview"
    ])
    assert primary == "gemini-3.1-pro-preview"
    assert fast == "gemini-2.5-flash"


def test_select_models_has_safe_fallback():
    assert Gcli2ApiManager.select_models([]) == ("gemini-2.5-pro", "gemini-2.5-pro")


def test_extract_models_deduplicates_and_ignores_invalid():
    result = Gcli2ApiManager._extract_models({"data": [
        {"id": "gemini-a"}, {"id": "gemini-a"}, {"name": "x"}, "bad"
    ]})
    assert result == ("gemini-a",)


def test_examples_never_include_real_password(manager):
    examples = manager.generate_examples("gemini-test")
    assert set(examples) == {"anthropic", "openai", "gemini"}
    assert all(PLACEHOLDER_PASSWORD in value for value in examples.values())
    assert "/v1/chat/completions" in examples["openai"]
    assert ":generateContent" in examples["gemini"]


def test_redact_hides_headers_query_and_explicit_secret():
    text = "Authorization: Bearer abc123 https://x.test?a=1&key=xyz explicit-secret"
    redacted = Gcli2ApiManager._redact(text, ("explicit-secret",))
    assert "abc123" not in redacted
    assert "xyz" not in redacted
    assert "explicit-secret" not in redacted
    assert redacted.count("[REDACTED]") >= 2


def test_detect_ready_sends_bearer_without_redirect(monkeypatch, manager):
    seen = {}

    def fake_get(url, **kwargs):
        seen.update(url=url, **kwargs)
        return FakeResponse(200, {"data": [{"id": "gemini-2.5-pro"}]})

    monkeypatch.setattr("app.gcli2api_manager.requests.get", fake_get)
    status = manager.detect("top-secret")
    assert status.ready and status.state == "ready"
    assert status.models == ("gemini-2.5-pro",)
    assert seen["headers"]["Authorization"] == "Bearer top-secret"
    assert seen["allow_redirects"] is False


@pytest.mark.parametrize("code,error_code", [
    (302, "redirect"),
    (401, "auth_failed"),
    (403, "forbidden"),
    (404, "not_found"),
    (429, "rate_limited"),
    (500, "server_error"),
    (418, "http_error"),
])
def test_detect_classifies_http_errors(monkeypatch, manager, code, error_code):
    monkeypatch.setattr(
        "app.gcli2api_manager.requests.get", lambda *args, **kwargs: FakeResponse(code)
    )
    status = manager.detect("secret")
    assert status.error_code == error_code
    assert "secret" not in status.message


def test_detect_empty_models_requests_oauth(monkeypatch, manager):
    monkeypatch.setattr(
        "app.gcli2api_manager.requests.get", lambda *args, **kwargs: FakeResponse(200)
    )
    status = manager.detect("secret")
    assert status.state == "oauth_required"
    assert status.running and not status.ready


def test_detect_invalid_json(monkeypatch, manager):
    monkeypatch.setattr(
        "app.gcli2api_manager.requests.get",
        lambda *args, **kwargs: FakeResponse(200, ValueError("bad")),
    )
    assert manager.detect().error_code == "invalid_json"


def test_detect_timeout(monkeypatch, manager):
    def raise_timeout(*args, **kwargs):
        raise requests.exceptions.Timeout("secret")

    monkeypatch.setattr("app.gcli2api_manager.requests.get", raise_timeout)
    assert manager.detect("secret").error_code == "timeout"


def test_detect_dns_failure(monkeypatch, manager):
    def raise_dns(*args, **kwargs):
        raise requests.exceptions.ConnectionError("getaddrinfo ENOTFOUND secret")

    monkeypatch.setattr("app.gcli2api_manager.requests.get", raise_dns)
    status = manager.detect("secret")
    assert status.error_code == "dns"
    assert "secret" not in status.message


def test_detect_installed_but_stopped(monkeypatch, manager):
    manager.install_dir.mkdir(parents=True)
    (manager.install_dir / "web.py").touch()

    def raise_refused(*args, **kwargs):
        raise requests.exceptions.ConnectionError("connection refused")

    monkeypatch.setattr("app.gcli2api_manager.requests.get", raise_refused)
    status = manager.detect()
    assert status.state == "stopped"
    assert status.installed


def test_dependency_commands_use_fixed_ids_and_no_shell(monkeypatch, manager):
    monkeypatch.setattr(
        manager, "detect_dependencies", lambda: {"git": False, "uv": False, "winget": True}
    )
    monkeypatch.setattr(manager, "_resolve_executable", lambda name: "winget.exe" if name == "winget" else "")
    commands = manager.build_dependency_install_commands()
    flat = " ".join(" ".join(command) for command in commands)
    assert "Git.Git" in flat and "astral-sh.uv" in flat
    assert "Invoke-Expression" not in flat


def test_install_stops_when_dependencies_and_winget_missing(monkeypatch, manager):
    monkeypatch.setattr(
        manager, "detect_dependencies", lambda: {"git": False, "uv": False, "winget": False}
    )
    ok, message = manager.install()
    assert not ok
    assert "WinGet" in message


def test_install_uses_fixed_repo_and_shell_false(monkeypatch, manager):
    calls = []
    manager.install_dir.mkdir(parents=True)

    monkeypatch.setattr(
        manager, "detect_dependencies", lambda: {"git": True, "uv": True, "winget": True}
    )
    monkeypatch.setattr(manager, "build_dependency_install_commands", lambda: [])
    monkeypatch.setattr(manager, "_resolve_executable", lambda name: f"{name}.exe")

    def fake_run(args, cwd=None, timeout=0):
        calls.append((list(args), cwd, timeout))
        if "clone" in args:
            manager.install_dir.mkdir(parents=True, exist_ok=True)
            (manager.install_dir / "web.py").touch()
        if "sync" in args:
            python = manager.install_dir / ".venv" / "Scripts" / "python.exe"
            python.parent.mkdir(parents=True)
            python.touch()
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(manager, "_run_command", fake_run)
    ok, _ = manager.install()
    assert ok
    assert any(REPO_URL in call[0] for call in calls)
    assert any(call[0][0] == "uv.exe" and call[0][1] == "sync" for call in calls)


def test_install_stops_after_failed_clone(monkeypatch, manager):
    manager.install_dir.mkdir(parents=True)
    monkeypatch.setattr(
        manager, "detect_dependencies", lambda: {"git": True, "uv": True, "winget": True}
    )
    monkeypatch.setattr(manager, "build_dependency_install_commands", lambda: [])
    monkeypatch.setattr(manager, "_resolve_executable", lambda name: f"{name}.exe")
    calls = []

    def fake_run(args, cwd=None, timeout=0):
        calls.append(list(args))
        return SimpleNamespace(returncode=1, stdout="", stderr="Bearer secret")

    monkeypatch.setattr(manager, "_run_command", fake_run)
    ok, message = manager.install()
    assert not ok
    assert "secret" not in message
    assert not any("sync" in call for call in calls)


def _make_managed_install(manager):
    manager.install_dir.mkdir(parents=True)
    python = manager.install_dir / ".venv" / "Scripts" / "python.exe"
    python.parent.mkdir(parents=True)
    python.touch()
    (manager.install_dir / "web.py").touch()
    return python


def test_start_uses_argument_array_and_local_host(monkeypatch, manager):
    python = _make_managed_install(manager)
    seen = {}

    class FakeProcess:
        pid = 123

        def __init__(self):
            self.args = [str(python), str(manager.install_dir / "web.py")]

        def poll(self):
            return None

    def fake_popen(args, **kwargs):
        seen["args"] = args
        seen.update(kwargs)
        return FakeProcess()

    monkeypatch.setattr("app.gcli2api_manager.subprocess.Popen", fake_popen)
    ok, message = manager.start("api-secret", "panel-secret")
    assert ok and "123" in message
    assert isinstance(seen["args"], list)
    assert seen["shell"] is False
    assert seen["env"]["HOST"] == "127.0.0.1"
    assert "api-secret" not in " ".join(seen["args"])


def test_start_rejects_remote_service(tmp_path):
    manager = Gcli2ApiManager(tmp_path, "https://proxy.example.com")
    assert manager.start()[0] is False


def test_stop_refuses_unknown_process(manager):
    ok, message = manager.stop_managed()
    assert not ok and "没有" in message


def test_stop_refuses_process_identity_mismatch(manager):
    process = SimpleNamespace(args=["other.exe"], pid=1, poll=lambda: None)
    manager._managed_process = process
    manager._managed_executable = "expected.exe"
    ok, message = manager.stop_managed()
    assert not ok and "不匹配" in message
