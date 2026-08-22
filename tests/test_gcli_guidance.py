from pathlib import Path

import pytest

from app.gcli2api_manager import Gcli2ApiStatus
from app.gui import gcli_guide_text


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
        (_status("oauth_required", running=True), True, "Google OAuth"),
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
