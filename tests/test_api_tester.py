"""
ApiTester 单元测试
使用 mock 模拟 HTTP 请求，不发送真实网络请求
"""
import pytest
from unittest.mock import patch, MagicMock
from app.api_tester import ApiTester


class TestApiTesterValidation:
    """测试参数验证"""

    def test_empty_base_url(self):
        """空 URL 返回错误"""
        success, msg, ms = ApiTester.test_provider("", "sk-test", "model")
        assert success is False
        assert "URL" in msg or "url" in msg.lower()

    def test_empty_api_key(self):
        """空 API Key 返回错误"""
        success, msg, ms = ApiTester.test_provider(
            "https://test.example.com/anthropic", "", "model")
        assert success is False
        assert "Key" in msg or "key" in msg.lower()

    def test_empty_model(self):
        """空模型名返回错误"""
        success, msg, ms = ApiTester.test_provider(
            "https://test.example.com/anthropic", "sk-test", "")
        assert success is False
        assert "模型" in msg or "model" in msg.lower()


class TestApiTesterMockedRequests:
    """测试 HTTP 请求（mock）"""

    @patch("app.api_tester.requests.post")
    def test_success_200(self, mock_post):
        """200 响应返回成功"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response

        success, msg, ms = ApiTester.test_provider(
            "https://test.example.com/anthropic",
            "sk-test1234567890",
            "test-model"
        )
        assert success is True
        assert "正常" in msg
        assert ms >= 0

    @patch("app.api_tester.requests.post")
    def test_401_unauthorized(self, mock_post):
        """401 响应返回认证失败"""
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_post.return_value = mock_response

        success, msg, ms = ApiTester.test_provider(
            "https://test.example.com/anthropic",
            "sk-invalid-key",
            "test-model"
        )
        assert success is False
        assert "401" in msg or "认证" in msg

    @patch("app.api_tester.requests.post")
    def test_429_rate_limit(self, mock_post):
        """429 响应返回限流"""
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_post.return_value = mock_response

        success, msg, ms = ApiTester.test_provider(
            "https://test.example.com/anthropic",
            "sk-test1234567890",
            "test-model"
        )
        assert success is False
        assert "429" in msg

    @patch("app.api_tester.requests.post")
    def test_500_server_error(self, mock_post):
        """500 响应返回服务器错误"""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_post.return_value = mock_response

        success, msg, ms = ApiTester.test_provider(
            "https://test.example.com/anthropic",
            "sk-test1234567890",
            "test-model"
        )
        assert success is False
        assert "500" in msg

    @patch("app.api_tester.requests.post")
    def test_timeout(self, mock_post):
        """超时异常"""
        import requests
        mock_post.side_effect = requests.exceptions.Timeout()

        success, msg, ms = ApiTester.test_provider(
            "https://test.example.com/anthropic",
            "sk-test1234567890",
            "test-model"
        )
        assert success is False
        assert "超时" in msg or "timeout" in msg.lower()

    @patch("app.api_tester.requests.post")
    def test_connection_error(self, mock_post):
        """连接错误"""
        import requests
        mock_post.side_effect = requests.exceptions.ConnectionError()

        success, msg, ms = ApiTester.test_provider(
            "https://test.example.com/anthropic",
            "sk-test1234567890",
            "test-model"
        )
        assert success is False
        assert "连接" in msg or "connect" in msg.lower()

    @patch("app.api_tester.requests.post")
    def test_url_construction_with_anthropic_suffix(self, mock_post):
        """带 /anthropic 后缀的 URL 构建正确"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response

        ApiTester.test_provider(
            "https://test.example.com/anthropic",
            "sk-test1234567890",
            "test-model"
        )
        # 验证请求的 URL
        called_url = mock_post.call_args[0][0]
        assert "/v1/messages" in called_url

    @patch("app.api_tester.requests.post")
    def test_api_key_not_in_error_message(self, mock_post):
        """错误消息中不包含完整 API Key"""
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_post.return_value = mock_response

        secret_key = "sk-supersecretkey1234567890"
        success, msg, ms = ApiTester.test_provider(
            "https://test.example.com/anthropic",
            secret_key,
            "test-model"
        )
        # 完整 key 不应出现在消息中
        assert secret_key not in msg
