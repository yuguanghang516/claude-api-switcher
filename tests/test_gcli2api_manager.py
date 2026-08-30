from pathlib import Path
from types import SimpleNamespace
import io
import subprocess
import threading

import pytest
import requests

from app.gcli2api_manager import (
    DEFAULT_BASE_URL,
    PLACEHOLDER_PASSWORD,
    REPO_URL,
    Gcli2ApiManager,
    Gcli2ApiStatus,
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


def test_clean_claude_models_removes_transport_aliases_and_duplicates():
    result = Gcli2ApiManager.clean_claude_models([
        "gemini-3.6-flash-high",
        "假流式/gemini-3.6-flash-high",
        "流式抗截断/gemini-3.6-flash-high",
        "claude-sonnet-4-6",
        "chat_20706",
        "gemini-3.1-flash-image",
    ])

    assert result == ("claude-sonnet-4-6", "gemini-3.6-flash-high")


def test_normalize_model_name_strips_nested_feature_prefixes():
    assert Gcli2ApiManager.normalize_model_name(
        " 假流式/流式抗截断/gemini-2.5-pro "
    ) == "gemini-2.5-pro"


def test_clean_claude_models_prioritizes_stronger_models():
    result = Gcli2ApiManager.clean_claude_models([
        "gemini-3.5-flash-lite",
        "gemini-3.1-pro-high",
        "gpt-oss-120b-medium",
        "claude-sonnet-4-6",
        "claude-opus-4-6-thinking",
    ])

    assert result == (
        "claude-opus-4-6-thinking",
        "claude-sonnet-4-6",
        "gpt-oss-120b-medium",
        "gemini-3.1-pro-high",
        "gemini-3.5-flash-lite",
    )


@pytest.mark.parametrize("model,expected", [
    ("gemini-3.1-pro-high", True),
    ("claude-sonnet-4-6", True),
    ("gpt-oss-120b-medium", True),
    ("gemini-3.1-flash-image", False),
    ("gemini-pro-agent", False),
    ("chat_20706", False),
    ("tab_jump_flash_lite_preview", False),
])
def test_claude_text_model_filter(model, expected):
    assert Gcli2ApiManager.is_claude_text_model(model) is expected


def test_import_antigravity_credentials_uses_panel_upload_api(monkeypatch, manager, tmp_path):
    first = tmp_path / "ag-one.json"
    second = tmp_path / "ag-two.json"
    first.write_text('{"refresh_token":"hidden-one"}', encoding="utf-8")
    second.write_text('{"refresh_token":"hidden-two"}', encoding="utf-8")
    seen = {}

    def fake_post(url, **kwargs):
        seen.update(url=url, **kwargs)
        return FakeResponse(200, {
            "uploaded_count": 2,
            "results": [
                {"filename": "ag-one.json", "status": "success"},
                {"filename": "ag-two.json", "status": "success"},
            ],
        })

    monkeypatch.setattr("app.gcli2api_manager.requests.post", fake_post)
    result = manager.import_credentials([first, second], "panel-secret")

    assert result.ok and result.uploaded_count == 2
    assert seen["url"].endswith("/creds/upload")
    assert seen["params"] == {"mode": "antigravity"}
    assert seen["headers"]["Authorization"] == "Bearer panel-secret"
    assert seen["allow_redirects"] is False
    assert [item[0] for item in seen["files"]] == ["files", "files"]
    assert "panel-secret" not in result.message
    assert "hidden-one" not in result.message


def test_import_credentials_rejects_invalid_json_before_network(monkeypatch, manager, tmp_path):
    invalid = tmp_path / "bad.json"
    invalid.write_text("[]", encoding="utf-8")
    monkeypatch.setattr(
        "app.gcli2api_manager.requests.post", lambda *args, **kwargs: pytest.fail("no network"))

    result = manager.import_credentials([invalid], "secret")

    assert not result.ok
    assert "顶层必须是对象" in result.errors[0]


def test_model_quotas_aggregate_best_remaining_and_credential_count(monkeypatch, manager):
    responses = iter((
        FakeResponse(200, {"items": [
            {"filename": "ag-one.json", "disabled": False},
            {"filename": "ag-two.json", "disabled": False},
            {"filename": "disabled.json", "disabled": True},
        ]}),
        FakeResponse(200, {"models": {
            "gemini-pro": {"remaining": 0.25, "resetTime": "08-23 11:00"},
            "gemini-flash": {"remaining": 1.0, "resetTime": "08-23 10:00"},
        }}),
        FakeResponse(200, {"models": {
            "gemini-pro": {"remaining": 0.8, "resetTime": "08-23 12:00"},
        }}),
    ))
    monkeypatch.setattr(
        "app.gcli2api_manager.requests.get", lambda *args, **kwargs: next(responses))

    snapshot = manager.get_model_quotas("panel-secret")

    assert snapshot.ok and snapshot.credential_count == 2
    by_model = {item.model: item for item in snapshot.models}
    assert by_model["gemini-pro"].remaining_percent == 80
    assert by_model["gemini-pro"].credential_count == 2
    assert by_model["gemini-pro"].reset_time == "08-23 12:00"
    assert by_model["gemini-flash"].remaining_percent == 100


def test_model_quotas_reports_panel_password_mismatch(monkeypatch, manager):
    monkeypatch.setattr(
        "app.gcli2api_manager.requests.get", lambda *args, **kwargs: FakeResponse(403))
    snapshot = manager.get_model_quotas("wrong")
    assert not snapshot.ok
    assert "密码" in snapshot.message


def test_model_quotas_keeps_partial_results_with_bounded_concurrency(monkeypatch, manager):
    filenames = [f"ag-{index}.json" for index in range(4)]
    active = 0
    max_active = 0
    state_lock = threading.Lock()
    two_started = threading.Event()

    def fake_get(url, **kwargs):
        nonlocal active, max_active
        if url.endswith("/creds/status"):
            return FakeResponse(200, {
                "items": [{"filename": name, "disabled": False} for name in filenames]
            })
        filename = url.rsplit("/", 1)[-1]
        with state_lock:
            active += 1
            max_active = max(max_active, active)
            if active >= 2:
                two_started.set()
        two_started.wait(timeout=1)
        try:
            if filename == "ag-1.json":
                raise requests.exceptions.Timeout()
            return FakeResponse(200, {"models": {
                "gemini-pro": {"remaining": 0.5, "resetTime": "soon"},
            }})
        finally:
            with state_lock:
                active -= 1

    monkeypatch.setattr("app.gcli2api_manager.requests.get", fake_get)
    snapshot = manager.get_model_quotas(
        "panel-secret", max_workers=2, total_timeout=2, item_timeout=1)

    assert snapshot.ok
    assert snapshot.credential_count == 4
    assert snapshot.failed_count == 1
    assert "1 个凭证读取失败" in snapshot.message
    assert snapshot.models[0].credential_count == 3
    assert max_active == 2


def test_detect_quota_fallback_uses_strict_small_budget(monkeypatch, manager):
    seen = {}
    monkeypatch.setattr(
        "app.gcli2api_manager.requests.get",
        lambda *args, **kwargs: FakeResponse(200, {"data": []}),
    )

    def fake_quotas(password, mode, **kwargs):
        seen.update(password=password, mode=mode, **kwargs)
        return SimpleNamespace(ok=False, models=())

    monkeypatch.setattr(manager, "get_model_quotas", fake_quotas)
    status = manager.detect("secret")

    assert status.state == "oauth_required"
    assert seen["total_timeout"] <= 4
    assert seen["item_timeout"] <= 2
    assert seen["max_workers"] <= 4
    assert seen["max_credentials"] <= 12


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
        (403, "auth_failed"),
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
    assert seen["stdout"] == subprocess.PIPE
    assert seen["stderr"] == subprocess.STDOUT


def test_concurrent_start_creates_only_one_owned_process(monkeypatch, manager):
    python = _make_managed_install(manager)
    popen_calls = 0
    call_lock = threading.Lock()

    class FakeProcess:
        pid = 321

        def __init__(self):
            self.args = [str(python), str(manager.install_dir / "web.py")]
            self.stdout = io.StringIO("")
            self.return_code = None

        def poll(self):
            return self.return_code

        def terminate(self):
            self.return_code = 0

        def wait(self, timeout=None):
            return self.return_code

    process = FakeProcess()

    def fake_popen(*_args, **_kwargs):
        nonlocal popen_calls
        with call_lock:
            popen_calls += 1
        return process

    monkeypatch.setattr("app.gcli2api_manager.subprocess.Popen", fake_popen)
    barrier = threading.Barrier(8)
    results = []

    def start_once():
        barrier.wait(timeout=2)
        results.append(manager.start("api-secret", "panel-secret"))

    threads = [threading.Thread(target=start_once) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=2)

    assert popen_calls == 1
    assert len(results) == 8 and all(result[0] for result in results)
    assert manager._managed_process is process


def test_start_and_wait_timeout_stops_only_process_created_by_call(monkeypatch, manager):
    python = _make_managed_install(manager)
    stopped = _startup_status(manager, "stopped")
    monkeypatch.setattr(manager, "detect", lambda *_args: stopped)

    class FakeProcess:
        pid = 654

        def __init__(self):
            self.args = [str(python), str(manager.install_dir / "web.py")]
            self.stdout = io.StringIO("")
            self.return_code = None
            self.terminate_calls = 0

        def poll(self):
            return self.return_code

        def terminate(self):
            self.terminate_calls += 1
            self.return_code = 0

        def wait(self, timeout=None):
            return self.return_code

    process = FakeProcess()
    monkeypatch.setattr(
        "app.gcli2api_manager.subprocess.Popen", lambda *_args, **_kwargs: process)

    ok, message, _ = manager.start_and_wait(
        "api-secret", "panel-secret", timeout=0, poll_interval=0)

    assert not ok
    assert process.terminate_calls == 1
    assert manager._managed_process is None
    assert "已停止本次启动的进程" in message


def test_stop_releases_lifecycle_lock_while_reader_drains(monkeypatch, manager):
    python = _make_managed_install(manager)
    terminated = threading.Event()
    reader_drained = threading.Event()
    manager.logger = SimpleNamespace(debug=lambda _line: reader_drained.set())

    class BlockingStream:
        def __init__(self):
            self.sent = False

        def __iter__(self):
            return self

        def __next__(self):
            if self.sent:
                raise StopIteration
            assert terminated.wait(timeout=1)
            self.sent = True
            return "shutdown complete\n"

        def close(self):
            pass

    class FakeProcess:
        pid = 777

        def __init__(self):
            self.args = [str(python), str(manager.install_dir / "web.py")]
            self.stdout = BlockingStream()
            self.return_code = None

        def poll(self):
            return self.return_code

        def terminate(self):
            terminated.set()

        def wait(self, timeout=None):
            assert reader_drained.wait(timeout=1), "reader could not drain during stop"
            self.return_code = 0
            return 0

    process = FakeProcess()
    monkeypatch.setattr(
        "app.gcli2api_manager.subprocess.Popen", lambda *_args, **_kwargs: process)
    assert manager.start("api-secret", "panel-secret")[0]

    ok, message = manager.stop_managed()

    assert ok and "已停止" in message
    assert reader_drained.is_set()
    assert manager._managed_process is None
    assert manager._managed_reader_thread is None


def test_managed_process_output_is_bounded_redacted_and_reported(monkeypatch, manager):
    python = _make_managed_install(manager)
    stopped = _startup_status(manager, "stopped")
    monkeypatch.setattr(manager, "detect", lambda *_args: stopped)
    debug_lines = []
    manager.logger = SimpleNamespace(debug=debug_lines.append)

    class FakeProcess:
        pid = 987

        def __init__(self):
            self.args = [str(python), str(manager.install_dir / "web.py")]
            self.stdout = io.StringIO(
                "boot api-secret panel-secret Authorization: Bearer upstream-token\n")

        def poll(self):
            return 7

    process = FakeProcess()
    monkeypatch.setattr(
        "app.gcli2api_manager.subprocess.Popen", lambda *_args, **_kwargs: process)

    ok, message, _ = manager.start_and_wait(
        "api-secret", "panel-secret", timeout=1, poll_interval=0)

    assert not ok and "退出码 7" in message
    assert "最后日志" in message
    combined = "\n".join(debug_lines + list(manager._recent_process_logs) + [message])
    assert "api-secret" not in combined
    assert "panel-secret" not in combined
    assert "upstream-token" not in combined
    assert "[REDACTED]" in combined
    assert all(len(line) <= 500 for line in manager._recent_process_logs)


def test_start_rejects_remote_service(tmp_path):
    manager = Gcli2ApiManager(tmp_path, "https://proxy.example.com")
    assert manager.start()[0] is False


def _startup_status(manager, state, *, running=False, ready=False, error_code="", models=()):
    return Gcli2ApiStatus(
        state=state, installed=True, running=running, ready=ready,
        base_url=manager.base_url, install_dir=manager.install_dir,
        error_code=error_code, models=tuple(models), message=state,
    )


def test_start_and_wait_does_not_duplicate_existing_ready_service(monkeypatch, manager):
    ready = _startup_status(manager, "ready", running=True, ready=True, models=("gemini-pro",))
    monkeypatch.setattr(manager, "detect", lambda _password, _mode=None: ready)
    monkeypatch.setattr(manager, "start", lambda *_args: pytest.fail("must not start twice"))

    ok, message, status = manager.start_and_wait("secret", "secret")

    assert ok and status is ready
    assert "已经启动" in message


def test_start_and_wait_reports_ready_only_after_http_probe(monkeypatch, manager):
    stopped = _startup_status(manager, "stopped")
    ready = _startup_status(manager, "ready", running=True, ready=True, models=("gemini-pro",))
    states = iter((stopped, stopped, ready))
    monkeypatch.setattr(manager, "detect", lambda _password, _mode=None: next(states))
    monkeypatch.setattr(manager, "start", lambda *_args: (True, "process created"))

    ok, message, status = manager.start_and_wait("secret", "secret", timeout=1, poll_interval=0)

    assert ok and status is ready
    assert "可以调用" in message


def test_start_and_wait_guides_oauth_after_service_starts(monkeypatch, manager):
    stopped = _startup_status(manager, "stopped")
    oauth = _startup_status(manager, "oauth_required", running=True, error_code="no_models")
    states = iter((stopped, oauth))
    monkeypatch.setattr(manager, "detect", lambda _password, _mode=None: next(states))
    monkeypatch.setattr(manager, "start", lambda *_args: (True, "process created"))

    ok, message, status = manager.start_and_wait("secret", "secret", timeout=1, poll_interval=0)

    assert ok and status is oauth
    assert "Google OAuth" in message


def test_start_and_wait_rejects_wrong_password_without_spawning(monkeypatch, manager):
    auth = _startup_status(manager, "auth_required", running=True, error_code="auth_failed")
    monkeypatch.setattr(manager, "detect", lambda _password, _mode=None: auth)
    monkeypatch.setattr(manager, "start", lambda *_args: pytest.fail("must not start on occupied port"))

    ok, message, status = manager.start_and_wait("wrong", "wrong")

    assert not ok and status is auth
    assert "API_PASSWORD" in message


def test_start_and_wait_reports_process_exit(monkeypatch, manager):
    stopped = _startup_status(manager, "stopped")
    monkeypatch.setattr(manager, "detect", lambda _password, _mode=None: stopped)

    def fake_start(*_args):
        manager._managed_process = SimpleNamespace(poll=lambda: 7)
        return True, "process created"

    monkeypatch.setattr(manager, "start", fake_start)
    ok, message, status = manager.start_and_wait("secret", "secret", timeout=1, poll_interval=0)

    assert not ok and status is stopped
    assert "退出码 7" in message


def test_start_and_wait_reports_timeout(monkeypatch, manager):
    stopped = _startup_status(manager, "stopped")
    monkeypatch.setattr(manager, "detect", lambda _password, _mode=None: stopped)
    monkeypatch.setattr(manager, "start", lambda *_args: (True, "process created"))
    times = iter((0.0, 1.0))
    monkeypatch.setattr("app.gcli2api_manager.time.monotonic", lambda: next(times))

    ok, message, status = manager.start_and_wait("secret", "secret", timeout=0.5, poll_interval=0)

    assert not ok and status is stopped
    assert "0.5 秒内服务未响应" in message


def test_stop_refuses_unknown_process(manager):
    ok, message = manager.stop_managed()
    assert not ok and "没有" in message


def test_stop_refuses_process_identity_mismatch(manager):
    process = SimpleNamespace(args=["other.exe"], pid=1, poll=lambda: None)
    manager._managed_process = process
    manager._managed_executable = "expected.exe"
    ok, message = manager.stop_managed()
    assert not ok and "不匹配" in message
