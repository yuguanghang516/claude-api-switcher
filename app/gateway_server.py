"""
本地 AI 网关服务
提供 OpenAI API 兼容接口，让任何支持 OpenAI API 的客户端可以直接连接

支持的接口：
- /v1/chat/completions  (OpenAI 聊天补全)
- /v1/models            (模型列表)
- /v1/health            (健康检查)
"""
import json
import time
import threading
import requests
from typing import Dict, List, Optional, Any, Tuple
from flask import Flask, request, jsonify, Response, stream_with_context


# 支持的供应商及其默认配置
SUPPORTED_PROVIDERS = {
    "openai": {
        "name": "OpenAI",
        "base_url": "https://api.openai.com/v1",
        "models": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo"],
        "auth_mode": "bearer",
    },
    "anthropic": {
        "name": "Anthropic Claude",
        "base_url": "https://api.anthropic.com/v1",
        "models": ["claude-sonnet-4-20250514", "claude-opus-4-20250514", "claude-3-5-haiku-20241022"],
        "auth_mode": "x-api-key",
    },
    "google": {
        "name": "Google Gemini",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "models": ["gemini-3.7-flash", "gemini-3.6-flash", "gemini-2.5-pro"],
        "auth_mode": "bearer",
    },
    "gcli2api": {
        "name": "Gemini CLI 反代 (gcli2api)",
        "base_url": "http://127.0.0.1:7861/v1",
        "models": ["gemini-2.5-pro"],
        "auth_mode": "bearer",
    },
    "deepseek": {
        "name": "DeepSeek",
        "base_url": "https://api.deepseek.com/v1",
        "models": ["deepseek-chat", "deepseek-reasoner"],
        "auth_mode": "bearer",
    },
    "kimi": {
        "name": "Kimi (月之暗面)",
        "base_url": "https://api.moonshot.cn/v1",
        "models": ["moonshot-v1-8k", "moonshot-v1-32k", "moonshot-v1-128k"],
        "auth_mode": "bearer",
    },
    "longcat": {
        "name": "LongCat",
        "base_url": "https://api.longcat.chat/openai",
        "models": ["LongCat-2.0", "LongCat-Flash-Chat"],
        "auth_mode": "bearer",
    },
    "openrouter": {
        "name": "OpenRouter",
        "base_url": "https://openrouter.ai/api/v1",
        "models": ["anthropic/claude-sonnet-4", "openai/gpt-4o", "google/gemini-1.5-pro"],
        "auth_mode": "bearer",
    },
    "custom": {
        "name": "自定义 OpenAI Compatible",
        "base_url": "",
        "models": [],
        "auth_mode": "bearer",
    },
}


class GatewayServer:
    """本地 AI 网关服务器"""

    def __init__(self, db_manager=None, logger=None, host: str = "127.0.0.1", port: int = 8787):
        self.host = host
        self.port = port
        self.db = db_manager
        self.logger = logger
        self.app = Flask(__name__)
        self.server_thread: Optional[threading.Thread] = None
        self._running = False
        self._setup_routes()

    def _setup_routes(self):
        """设置路由"""
        self.app.add_url_rule("/v1/chat/completions", view_func=self._chat_completions, methods=["POST"])
        self.app.add_url_rule("/v1/models", view_func=self._list_models, methods=["GET"])
        self.app.add_url_rule("/v1/health", view_func=self._health_check, methods=["GET"])

    def get_base_url(self) -> str:
        """获取网关基础 URL"""
        return f"http://{self.host}:{self.port}"

    def is_running(self) -> bool:
        """检查网关是否正在运行"""
        return self._running

    def start(self) -> Tuple[bool, str]:
        """启动网关服务"""
        if self._running:
            return True, f"网关已在运行: {self.get_base_url()}"

        def run_flask():
            import logging
            log = logging.getLogger("werkzeug")
            log.setLevel(logging.ERROR)
            self.app.run(host=self.host, port=self.port, debug=False, use_reloader=False)

        self.server_thread = threading.Thread(target=run_flask, daemon=True, name="gateway-server")
        self.server_thread.start()
        self._running = True

        if self.logger:
            self.logger.info(f"AI Gateway 已启动: {self.get_base_url()}")

        return True, f"网关已启动: {self.get_base_url()}"

    def stop(self) -> Tuple[bool, str]:
        """停止网关服务"""
        # Flask 没有优雅的停止方式，daemon 线程会在主进程结束时自动停止
        self._running = False
        if self.logger:
            self.logger.info("AI Gateway 已停止")
        return True, "网关已停止"

    def _health_check(self):
        """健康检查端点"""
        return jsonify({
            "status": "ok",
            "service": "AI Gateway",
            "version": "1.0.0",
            "url": self.get_base_url()
        })

    def _list_models(self):
        """列出可用模型"""
        models = []
        if self.db:
            enabled_models = self.db.get_enabled_models()
            for m in enabled_models:
                models.append({
                    "id": m.get("model_name", ""),
                    "object": "model",
                    "created": int(time.time()),
                    "owned_by": m.get("provider_name", "unknown"),
                    "permission": [{
                        "id": f"modelperm-{m.get('id', 0)}",
                        "object": "model_permission",
                        "created": int(time.time()),
                        "allow_create_engine": False,
                        "allow_sampling": True,
                        "allow_logprobs": True,
                        "allow_search_indices": False,
                        "allow_view": True,
                        "allow_fine_tuning": False,
                        "organization": "*",
                        "group": None,
                        "is_blocking": False
                    }]
                })

        return jsonify({
            "object": "list",
            "data": models
        })

    def _chat_completions(self):
        """聊天补全端点 - OpenAI 兼容"""
        start_time = time.monotonic()

        # 解析请求
        try:
            data = request.get_json(force=True)
        except Exception:
            return jsonify({"error": {"message": "无效的 JSON 请求", "type": "invalid_request_error"}}), 400

        model_name = data.get("model", "")
        messages = data.get("messages", [])
        stream = data.get("stream", False)
        temperature = data.get("temperature", 0.7)
        max_tokens = data.get("max_tokens", 4096)

        if not model_name:
            return jsonify({"error": {"message": "未指定模型", "type": "invalid_request_error"}}), 400

        if not messages:
            return jsonify({"error": {"message": "消息列表为空", "type": "invalid_request_error"}}), 400

        # 查找模型配置
        model_config = None
        if self.db:
            model_config = self.db.get_model_by_name(model_name)

        if not model_config:
            elapsed = int((time.monotonic() - start_time) * 1000)
            self._log_request(model_name, 0, 0, 0, elapsed, "error", f"模型未找到: {model_name}")
            return jsonify({"error": {"message": f"模型未找到或已禁用: {model_name}", "type": "model_not_found"}}), 404

        # 获取供应商 API Key
        provider_id = model_config.get("provider_id")
        api_key = ""
        base_url = model_config.get("base_url", "")
        auth_mode = model_config.get("auth_mode", "bearer")

        if self.db:
            provider = self.db.get_provider(provider_id)
            if provider:
                api_key = provider.get("api_key", "")
                if not base_url:
                    base_url = provider.get("base_url", "")
                if not auth_mode:
                    auth_mode = provider.get("auth_mode", "bearer")

        if not api_key:
            elapsed = int((time.monotonic() - start_time) * 1000)
            self._log_request(model_name, 0, 0, 0, elapsed, "error", "API Key 未配置")
            return jsonify({"error": {"message": "API Key 未配置", "type": "auth_error"}}), 401

        # 构建请求
        headers = {
            "Content-Type": "application/json",
        }
        if auth_mode == "x-api-key":
            headers["x-api-key"] = api_key
            headers["anthropic-version"] = "2023-06-01"
        else:
            headers["Authorization"] = f"Bearer {api_key}"

        # 判断是 Anthropic 还是 OpenAI 格式
        is_anthropic = "/anthropic" in base_url or model_config.get("provider_type") == "anthropic"

        if is_anthropic:
            return self._proxy_anthropic(data, model_config, base_url, headers, stream, start_time)
        else:
            return self._proxy_openai(data, model_config, base_url, headers, stream, start_time)

    def _proxy_openai(self, data: Dict, model_config: Dict, base_url: str,
                      headers: Dict, stream: bool, start_time: float):
        """代理 OpenAI 格式请求"""
        target_url = base_url.rstrip("/")
        if not target_url.endswith("/chat/completions"):
            target_url = f"{target_url}/chat/completions"

        payload = {
            "model": data.get("model"),
            "messages": data.get("messages", []),
            "temperature": data.get("temperature", 0.7),
            "max_tokens": data.get("max_tokens", 4096),
            "stream": stream,
        }
        if data.get("tools"):
            payload["tools"] = data["tools"]
        if data.get("tool_choice"):
            payload["tool_choice"] = data["tool_choice"]

        try:
            if stream:
                return self._stream_openai(target_url, headers, payload, data.get("model", ""), start_time)
            else:
                return self._sync_openai(target_url, headers, payload, data.get("model", ""), start_time)
        except requests.exceptions.Timeout:
            elapsed = int((time.monotonic() - start_time) * 1000)
            self._log_request(data.get("model", ""), 0, 0, 0, elapsed, "error", "请求超时")
            return jsonify({"error": {"message": "请求超时", "type": "timeout_error"}}), 504
        except requests.exceptions.RequestException as e:
            elapsed = int((time.monotonic() - start_time) * 1000)
            self._log_request(data.get("model", ""), 0, 0, 0, elapsed, "error", str(e)[:200])
            return jsonify({"error": {"message": f"代理请求失败: {str(e)[:100]}", "type": "proxy_error"}}), 502

    def _sync_openai(self, url: str, headers: Dict, payload: Dict, model: str, start_time: float):
        """同步 OpenAI 请求"""
        resp = requests.post(url, headers=headers, json=payload, timeout=120)
        elapsed = int((time.monotonic() - start_time) * 1000)

        result = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}

        # 提取 token 使用量
        usage = result.get("usage", {})
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)
        total_tokens = usage.get("total_tokens", prompt_tokens + completion_tokens)

        self._log_request(model, prompt_tokens, completion_tokens, total_tokens, elapsed,
                         "success" if resp.status_code == 200 else "error",
                         "" if resp.status_code == 200 else f"HTTP {resp.status_code}")

        response = {
            "id": result.get("id", f"chatcmpl-{int(time.time())}"),
            "object": "chat.completion",
            "created": int(time.time()),
            "model": model,
            "choices": result.get("choices", []),
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
            }
        }
        return jsonify(response), resp.status_code

    def _stream_openai(self, url: str, headers: Dict, payload: Dict, model: str, start_time: float):
        """流式 OpenAI 请求"""
        def generate():
            prompt_tokens = 0
            completion_tokens = 0
            try:
                with requests.post(url, headers=headers, json=payload, timeout=120, stream=True) as resp:
                    for line in resp.iter_lines():
                        if line:
                            decoded = line.decode("utf-8")
                            if decoded.startswith("data: "):
                                yield decoded + "\n\n"
                                if "[DONE]" in decoded:
                                    break
            finally:
                elapsed = int((time.monotonic() - start_time) * 1000)
                self._log_request(model, prompt_tokens, completion_tokens,
                                 prompt_tokens + completion_tokens, elapsed, "success", "")

        return Response(stream_with_context(generate()), content_type="text/event-stream")

    def _proxy_anthropic(self, data: Dict, model_config: Dict, base_url: str,
                         headers: Dict, stream: bool, start_time: float):
        """代理 Anthropic 格式请求（转换为 OpenAI 格式）"""
        target_url = base_url.rstrip("/")
        if not target_url.endswith("/messages"):
            target_url = f"{target_url}/messages"

        # 转换消息格式 OpenAI -> Anthropic
        messages = data.get("messages", [])
        system_message = ""
        anthropic_messages = []

        for msg in messages:
            if msg.get("role") == "system":
                system_message = msg.get("content", "")
            else:
                anthropic_messages.append({
                    "role": msg.get("role"),
                    "content": msg.get("content", "")
                })

        payload = {
            "model": data.get("model"),
            "max_tokens": data.get("max_tokens", 4096),
            "messages": anthropic_messages,
        }
        if system_message:
            payload["system"] = system_message
        if data.get("temperature"):
            payload["temperature"] = data["temperature"]

        try:
            resp = requests.post(target_url, headers=headers, json=payload, timeout=120)
            elapsed = int((time.monotonic() - start_time) * 1000)

            if resp.status_code != 200:
                error_text = resp.text[:200]
                self._log_request(data.get("model", ""), 0, 0, 0, elapsed, "error", error_text)
                return jsonify({"error": {"message": f"API 错误: {error_text}", "type": "api_error"}}), resp.status_code

            result = resp.json()

            # 提取使用量
            usage = result.get("usage", {})
            input_tokens = usage.get("input_tokens", 0)
            output_tokens = usage.get("output_tokens", 0)

            # 提取回复文本
            content_blocks = result.get("content", [])
            reply_text = ""
            for block in content_blocks:
                if block.get("type") == "text":
                    reply_text += block.get("text", "")

            self._log_request(data.get("model", ""), input_tokens, output_tokens,
                             input_tokens + output_tokens, elapsed, "success", "")

            # 转换为 OpenAI 格式响应
            response = {
                "id": result.get("id", f"msg_{int(time.time())}"),
                "object": "chat.completion",
                "created": int(time.time()),
                "model": data.get("model", ""),
                "choices": [{
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": reply_text,
                    },
                    "finish_reason": "stop" if result.get("stop_reason") == "end_turn" else result.get("stop_reason", "stop"),
                }],
                "usage": {
                    "prompt_tokens": input_tokens,
                    "completion_tokens": output_tokens,
                    "total_tokens": input_tokens + output_tokens,
                }
            }
            return jsonify(response), 200

        except requests.exceptions.Timeout:
            elapsed = int((time.monotonic() - start_time) * 1000)
            self._log_request(data.get("model", ""), 0, 0, 0, elapsed, "error", "请求超时")
            return jsonify({"error": {"message": "请求超时", "type": "timeout_error"}}), 504
        except requests.exceptions.RequestException as e:
            elapsed = int((time.monotonic() - start_time) * 1000)
            self._log_request(data.get("model", ""), 0, 0, 0, elapsed, "error", str(e)[:200])
            return jsonify({"error": {"message": f"代理请求失败: {str(e)[:100]}", "type": "proxy_error"}}), 502

    def _log_request(self, model: str, input_tokens: int, output_tokens: int,
                     total_tokens: int, response_time_ms: int, status: str, error: str = ""):
        """记录请求日志"""
        if self.db:
            self.db.log_request({
                "model": model,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": total_tokens,
                "response_time_ms": response_time_ms,
                "status": status,
                "error": error[:500] if error else "",
            })
        if self.logger and status == "error":
            self.logger.error(f"Gateway [{model}] {status}: {error}")
