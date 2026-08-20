"""
CredentialManager 单元测试
使用 monkeypatch 模拟 keyring，不触碰真实 Windows 凭据管理器
"""
import pytest
from app.credential_manager import CredentialManager, APP_NAME


class TestCredentialManager:
    """凭据管理器测试"""

    def test_save_and_get_api_key(self, monkeypatch):
        """保存和读取 API Key"""
        store = {}
        monkeypatch.setattr(
            "app.credential_manager.keyring.set_password",
            lambda s, k, v: store.update({(s, k): v})
        )
        monkeypatch.setattr(
            "app.credential_manager.keyring.get_password",
            lambda s, k: store.get((s, k))
        )

        CredentialManager.save_api_key("TestProvider", "sk-test1234567890")
        result = CredentialManager.get_api_key("TestProvider")
        assert result == "sk-test1234567890"

    def test_get_nonexistent_key_returns_empty(self, monkeypatch):
        """读取不存在的 Key 返回空字符串"""
        monkeypatch.setattr(
            "app.credential_manager.keyring.get_password",
            lambda s, k: None
        )
        assert CredentialManager.get_api_key("NonExistent") == ""

    def test_delete_api_key(self, monkeypatch):
        """删除 API Key"""
        store = {}
        monkeypatch.setattr(
            "app.credential_manager.keyring.set_password",
            lambda s, k, v: store.update({(s, k): v})
        )
        monkeypatch.setattr(
            "app.credential_manager.keyring.get_password",
            lambda s, k: store.get((s, k))
        )
        monkeypatch.setattr(
            "app.credential_manager.keyring.delete_password",
            lambda s, k: store.pop((s, k), None)
        )

        CredentialManager.save_api_key("Test", "sk-abcdef123456")
        CredentialManager.delete_api_key("Test")
        assert CredentialManager.get_api_key("Test") == ""

    def test_mask_api_key_long(self):
        """长 Key 掩码显示"""
        masked = CredentialManager.mask_api_key("sk-1234567890abcdef")
        assert masked.startswith("sk-1")
        assert "****" in masked
        assert masked.endswith("cdef")

    def test_mask_api_key_short(self):
        """短 Key 完全掩码"""
        masked = CredentialManager.mask_api_key("sk-1234")
        assert masked == "****"

    def test_mask_api_key_empty(self):
        """空 Key 显示未设置"""
        assert CredentialManager.mask_api_key("") == "未设置"

    def test_mask_api_key_does_not_contain_full_key(self):
        """掩码结果不包含完整 Key"""
        full_key = "sk-abcdefghijklmnop1234"
        masked = CredentialManager.mask_api_key(full_key)
        # 掩码后的字符串不应包含完整 key
        assert full_key not in masked
        # 但应保留首尾
        assert masked.startswith("sk-a")
        assert masked.endswith("1234")
