"""
API Key 安全管理模块
使用 Windows Credential Manager (keyring) 保存和读取 API Key
"""
import keyring


# 应用名称，用于在 Windows 凭据管理器中标识
APP_NAME = "ClaudeAPISwitcher"


class CredentialManager:
    """API Key 凭据管理器"""

    @staticmethod
    def save_api_key(provider_name: str, api_key: str) -> bool:
        """
        保存 API Key 到 Windows 凭据管理器
        :param provider_name: Provider 名称
        :param api_key: API Key
        :return: 是否成功
        """
        try:
            keyring.set_password(APP_NAME, provider_name, api_key)
            return True
        except Exception:
            return False

    @staticmethod
    def get_api_key(provider_name: str) -> str:
        """
        从 Windows 凭据管理器获取 API Key
        :param provider_name: Provider 名称
        :return: API Key，不存在则返回空字符串
        """
        try:
            key = keyring.get_password(APP_NAME, provider_name)
            return key if key else ""
        except Exception:
            return ""

    @staticmethod
    def delete_api_key(provider_name: str) -> bool:
        """
        删除指定 Provider 的 API Key
        :param provider_name: Provider 名称
        :return: 是否成功
        """
        try:
            keyring.delete_password(APP_NAME, provider_name)
            return True
        except Exception:
            return False

    @staticmethod
    def mask_api_key(api_key: str) -> str:
        """
        将 API Key 显示为掩码格式，只显示前4后4位
        例如：sk-****92ab
        """
        if not api_key:
            return "未设置"
        if len(api_key) <= 8:
            return "****"
        return f"{api_key[:4]}****{api_key[-4:]}"
