"""
测试配置 - 提供共享的 fixtures
所有测试使用临时目录，绝不触碰真实 ~/.claude/
"""
import os
import sys
import json
import shutil
import tempfile
import pytest

# 确保项目根目录在 sys.path 中
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)


@pytest.fixture
def temp_dir():
    """创建临时目录，测试结束后自动清理"""
    d = tempfile.mkdtemp(prefix="claude_switcher_test_")
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def data_dir(temp_dir):
    """创建数据目录"""
    d = os.path.join(temp_dir, "data")
    os.makedirs(d, exist_ok=True)
    return d


@pytest.fixture
def logs_dir(temp_dir):
    """创建日志目录"""
    d = os.path.join(temp_dir, "logs")
    os.makedirs(d, exist_ok=True)
    return d


@pytest.fixture
def backups_dir(temp_dir):
    """创建备份目录"""
    d = os.path.join(temp_dir, "backups")
    os.makedirs(d, exist_ok=True)
    return d


@pytest.fixture
def config(data_dir):
    """创建 ConfigManager 实例"""
    from app.config_manager import ConfigManager
    return ConfigManager(data_dir)


@pytest.fixture
def mock_cred_manager(monkeypatch):
    """Mock CredentialManager - 使用内存字典代替 Windows 凭据管理器"""
    store = {}

    def mock_save(service, key, value):
        store[(service, key)] = value
        return True

    def mock_get(service, key):
        return store.get((service, key), "")

    def mock_delete(service, key):
        store.pop((service, key), None)
        return True

    import app.credential_manager as cred_mod
    monkeypatch.setattr(cred_mod.keyring, "set_password", mock_save)
    monkeypatch.setattr(cred_mod.keyring, "get_password",
                        lambda s, k: mock_get(s, k))
    monkeypatch.setattr(cred_mod.keyring, "delete_password", mock_delete)
    return store
