from pathlib import Path

import pytest

from app.gcli2api_manager import (
    Gcli2ApiManager, Gcli2ApiStatus, GcliModelQuota, GcliQuotaSnapshot,
    MODE_ANTIGRAVITY, MODE_GEMINI_CLI,
)
from app.gui import MainWindow, gcli_guide_text


def _status(state, *, installed=True, running=False, ready=False, message=""):
    return Gcli2ApiStatus(
        state=state, installed=installed, running=running, ready=ready,
        install_dir=Path("gcli2api"), message=message,
    )


@pytest.mark.parametrize(
    ("status", "has_password", "expected"),
    [
        (_status("not_installed", installed=False), False, "一键安装"),
        (_status("stopped"), False, "自己设置"),
        (_status("stopped"), True, "启动服务"),
        (_status("auth_required", running=True), True, "API_PASSWORD"),
        (_status("oauth_required", running=True), True, "Antigravity"),
        (_status("ready", running=True, ready=True), True, "测试并使用"),
        (_status("error", message="端口异常"), True, "端口异常"),
    ],
)
def test_chinese_guidance_always_names_the_next_action(status, has_password, expected):
    assert expected in gcli_guide_text(status, has_password, "zh")


def test_english_password_guidance_explains_source():
    text = gcli_guide_text(_status("stopped"), False, "en")
    assert "choose your own password" in text.lower()
    assert "Generate & Copy" in text


def test_saved_claude_gcli_connection_restores_password_and_mode():
    window = MainWindow.__new__(MainWindow)

    class Providers:
        def get_all_providers(self):
            return [{"name": "Gemini", "provider_kind": "gcli2api"}]

        def get_provider_detail(self, _name):
            return {
                "base_url": "http://127.0.0.1:7861/antigravity",
                "api_key": "saved-password", "model": "假流式/gemini-pro",
            }

    window.provider_manager = Providers()
    window.model_manager = type("Models", (), {"get_all_providers": lambda self: []})()
    assert window._saved_gcli_connection() == (
        "saved-password", MODE_ANTIGRAVITY, "gemini-pro")


def test_saved_gateway_gcli_connection_is_used_as_fallback():
    window = MainWindow.__new__(MainWindow)
    window.provider_manager = type(
        "Providers", (), {"get_all_providers": lambda self: []})()

    class Models:
        def get_all_providers(self):
            return [{
                "id": "gcli", "provider_type": "gcli2api",
                "name": "Gemini CLI Enterprise (gcli2api)",
                "base_url": "http://127.0.0.1:7861/v1", "api_key": "gateway-password",
            }]

        def get_models_by_provider(self, _provider_id):
            return [{"model_name": "gemini-enterprise"}]

    window.model_manager = Models()
    assert window._saved_gcli_connection() == (
        "gateway-password", MODE_GEMINI_CLI, "gemini-enterprise")


def test_saved_gcli_local_gateway_is_detected_for_restart():
    window = MainWindow.__new__(MainWindow)
    window.gateway = type(
        "Gateway", (), {"get_base_url": lambda self: "http://127.0.0.1:8787"})()

    class Providers:
        def get_all_providers(self):
            return [{"name": "Gemini", "provider_kind": "gcli2api"}]

        def get_provider_detail(self, _name):
            return {"base_url": "HTTP://127.0.0.1:8787/"}

    window.provider_manager = Providers()
    assert window._saved_gcli_uses_local_gateway() is True


def test_ready_antigravity_service_schedules_automatic_quota_refresh():
    window = MainWindow.__new__(MainWindow)
    scheduled = []
    window.root = type("Root", (), {
        "after": lambda self, delay, callback: scheduled.append((delay, callback)),
    })()
    window._refresh_gcli_quotas = lambda: None

    status = Gcli2ApiStatus(
        state="ready", running=True, ready=True, mode=MODE_ANTIGRAVITY)

    assert window._schedule_gcli_quota_refresh(status) is True
    assert scheduled == [(60, window._refresh_gcli_quotas)]


def test_enterprise_service_does_not_schedule_antigravity_quota_refresh():
    window = MainWindow.__new__(MainWindow)
    window.root = type("Root", (), {
        "after": lambda self, delay, callback: pytest.fail("unexpected quota refresh"),
    })()
    window._refresh_gcli_quotas = lambda: None

    status = Gcli2ApiStatus(
        state="ready", running=True, ready=True, mode=MODE_GEMINI_CLI)

    assert window._schedule_gcli_quota_refresh(status) is False


def test_quota_worker_restores_persistent_service_status_copy():
    window = MainWindow.__new__(MainWindow)
    status = Gcli2ApiStatus(
        state="ready", running=True, ready=True, mode=MODE_ANTIGRAVITY)
    window._gcli_status = status
    calls = []
    window._set_gcli_busy = lambda busy: calls.append(("busy", busy))
    window._render_gcli_status = lambda value: calls.append(("status", value))

    window._finish_gcli_busy_status()

    assert calls == [("busy", False), ("status", status)]


def test_direct_gcli_connection_does_not_restart_local_gateway():
    window = MainWindow.__new__(MainWindow)
    window.gateway = type(
        "Gateway", (), {"get_base_url": lambda self: "http://127.0.0.1:8787"})()

    class Providers:
        def get_all_providers(self):
            return [{"name": "Gemini", "provider_kind": "gcli2api"}]

        def get_provider_detail(self, _name):
            return {"base_url": "http://127.0.0.1:7861/antigravity"}

    window.provider_manager = Providers()
    assert window._saved_gcli_uses_local_gateway() is False


def test_prepare_local_gcli_starts_services_and_uses_clean_ranked_models():
    window = MainWindow.__new__(MainWindow)
    calls = {"start": 0, "gateway": 0}

    class Gcli:
        def start_and_wait(self, password, panel_password, mode):
            calls["start"] += 1
            assert password == panel_password == "local-password"
            return True, "ready", Gcli2ApiStatus(
                state="ready", running=True, ready=True, mode=mode,
                models=("假流式/gemini-3.6-flash-high", "claude-sonnet-4-6"))

        def get_model_quotas(self, _password, _mode):
            return GcliQuotaSnapshot(True, models=(
                GcliModelQuota("流式抗截断/gemini-3.6-flash-high", 88),
                GcliModelQuota("claude-sonnet-4-6", 100),
            ))

        normalize_model_name = staticmethod(Gcli2ApiManager.normalize_model_name)
        clean_claude_models = staticmethod(Gcli2ApiManager.clean_claude_models)

        @staticmethod
        def claude_base_url(_mode):
            return "http://127.0.0.1:7861/antigravity"

    class Gateway:
        def get_base_url(self):
            return "http://127.0.0.1:8787"

        def configure_gcli_failover(self, base_url, key, models, quota, preferred):
            calls["configured"] = (base_url, key, models, quota, preferred)

        def start(self):
            calls["gateway"] += 1
            return True, "started"

    window.gcli2api = Gcli()
    window.gateway = Gateway()
    window.provider_manager = type("Providers", (), {
        "add_or_update_provider": lambda self, **kwargs: (
            calls.update({
                "saved_model": kwargs["model"],
                "saved_auth_mode": kwargs["auth_mode"],
            }) or True, "saved")
    })()
    ok, message, status, snapshot = window._prepare_gcli_provider_for_test({
        "name": "Gemini Antigravity (gcli2api)",
        "provider_kind": "gcli2api",
        "base_url": "http://127.0.0.1:8787",
        "api_key": "local-password",
        "model": "假流式/gemini-3.6-flash-high",
    })

    assert ok and status.ready and snapshot.ok
    assert calls["start"] == calls["gateway"] == 1
    assert calls["configured"][2] == ["claude-sonnet-4-6", "gemini-3.6-flash-high"]
    assert calls["configured"][4] == "gemini-3.6-flash-high"
    assert calls["saved_model"] == "gemini-3.6-flash-high"
    assert calls["saved_auth_mode"] == "bearer"
    assert "本地切换网关已启动" in message


def test_prepare_gcli_oauth_required_explains_exact_next_step():
    window = MainWindow.__new__(MainWindow)
    window.gcli2api = type("Gcli", (), {
        "start_and_wait": lambda self, *args, **kwargs: (
            True, "oauth", Gcli2ApiStatus(
                state="oauth_required", running=True, ready=False,
                mode=MODE_ANTIGRAVITY)),
    })()
    window.gateway = object()

    ok, message, _, _ = window._prepare_gcli_provider_for_test({
        "provider_kind": "gcli2api", "name": "Gemini Antigravity (gcli2api)",
        "base_url": "http://127.0.0.1:8787", "api_key": "password",
    })

    assert not ok
    assert "打开面板" in message and "Antigravity 凭证" in message


def test_switch_gcli_model_persists_both_claude_model_slots():
    window = MainWindow.__new__(MainWindow)
    saved = {}

    class Value:
        value = "gemini-2.5-pro"

        def get(self):
            return self.value

        def set(self, value):
            self.value = value

    class Providers:
        def get_all_providers(self):
            return [{"name": "Gemini", "provider_kind": "gcli2api"}]

        def get_provider_detail(self, _name):
            return {
                "name": "Gemini", "base_url": "http://127.0.0.1:8787",
                "api_key": "password", "enabled": True, "priority": 10,
                "auth_mode": "x-api-key",
            }

        def add_or_update_provider(self, **kwargs):
            saved.update(kwargs)
            return True, "saved"

    window.lang = "zh"
    window.gcli2api = Gcli2ApiManager
    window.gcli_model_var = Value()
    window.provider_manager = Providers()
    window.gateway = type("Gateway", (), {"get_base_url": lambda self: "http://127.0.0.1:8787"})()
    window._gcli_quota_snapshot = None
    calls = []
    window._gcli_password = lambda: "password"
    window._configure_gcli_failover = lambda: calls.append("configured")
    window._render_gcli_quotas = lambda _snapshot: calls.append("rendered")
    window._refresh_provider_list = lambda: None
    window._refresh_current_status = lambda: None
    window._append_log = lambda message: calls.append(message)

    window._switch_gcli_model("假流式/claude-opus-4-6-thinking")

    assert window.gcli_model_var.get() == "claude-opus-4-6-thinking"
    assert saved["model"] == saved["small_fast_model"] == "claude-opus-4-6-thinking"
    assert saved["auth_mode"] == "bearer"
    assert "configured" in calls and "rendered" in calls


def test_quick_launch_provider_never_falls_back_to_longcat():
    window = MainWindow.__new__(MainWindow)
    window.provider_manager = type("Providers", (), {
        "get_current_provider": lambda self: None,
        "get_all_providers": lambda self: [{
            "name": "LongCat", "enabled": True, "has_api_key": True,
        }],
    })()

    assert window._find_launch_provider() is None
