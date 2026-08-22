from pathlib import Path

import pytest

from app.gcli2api_manager import Gcli2ApiStatus, MODE_ANTIGRAVITY, MODE_GEMINI_CLI
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
                "api_key": "saved-password", "model": "gemini-pro",
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
