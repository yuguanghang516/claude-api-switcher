"""
增强版 AI 网关服务器
集成网关增强功能：
- API 余额检测
- 多 Key 自动轮询
- 自动故障转移
- 智能模型路由
- 成本控制
- Token 价格计算
- 通知系统
- 无重启热切换
"""
import json
import time
import threading
import requests
from typing import Dict, List, Optional, Any, Tuple
from flask import Flask, request, jsonify, Response, stream_with_context

from .balance_checker import BalanceChecker, BalanceInfo
from .key_rotator import MultiKeyRotator
from .failover import FailoverEngine, FailoverTarget, FailoverExhausted
from .smart_router import SmartRouter, ModelCapability
from .cost_controller import CostController
from .pricing import PricingCalculator
from .notifier import Notifier, Notification, NotificationType, NotificationPriority
from .v2_config import V2ConfigManager
from .hot_reload import ConfigHotSwapper
from .gateway_server import SUPPORTED_PROVIDERS


class GatewayServerV2:
    """增强版 AI 网关服务器。"""

    def __init__(self, db_manager=None, logger=None, v2_config: V2ConfigManager = None,
                 host: str = "127.0.0.1", port: int = 8787):
        self.host = host
        self.port = port
        self.db = db_manager
        self.logger = logger
        self.app = Flask(__name__)
        self.server_thread: Optional[threading.Thread] = None
        self._running = False

        # V2 模块
        self.v2_config = v2_config or V2ConfigManager(
            db_manager.data_dir if db_manager else "data"
        )
        self.balance_checker = BalanceChecker(logger=logger)
        self.key_rotator = MultiKeyRotator(
            strategy=self.v2_config.get_rotation_strategy(),
            logger=logger,
        )
        self.failover_engine = FailoverEngine(
            max_retries=self.v2_config.get_failover().get("max_retries", 3),
            retry_delay_ms=self.v2_config.get_failover().get("retry_delay_ms", 1000),
            timeout_seconds=self.v2_config.get_failover().get("timeout_seconds", 30),
            circuit_threshold=self.v2_config.get_failover().get("circuit_breaker_threshold", 5),
            circuit_reset_seconds=self.v2_config.get_failover().get("circuit_breaker_reset_seconds", 60),
            logger=logger,
        )
        self.smart_router = SmartRouter(
            default_task_type=self.v2_config.get_default_task_type(),
            logger=logger,
        )
        self.cost_controller = CostController(
            daily_limit=self.v2_config.get_daily_limit(),
            monthly_limit=self.v2_config.get_monthly_limit(),
            warning_threshold=self.v2_config.get_budget().get("warning_threshold", 0.8),
            auto_switch_cheap=self.v2_config.get_budget().get("auto_switch_cheap", True),
            currency=self.v2_config.get_budget().get("currency", "USD"),
            logger=logger,
        )
        self.pricing = PricingCalculator()
        self.notifier = Notifier(
            desktop_enabled=self.v2_config.get_notifications().get("desktop_enabled", True),
            webhook_enabled=self.v2_config.get_notifications().get("webhook_enabled", False),
            webhook_url=self.v2_config.get_notifications().get("webhook_url", ""),
            logger=logger,
        )
        self.hot_swapper = ConfigHotSwapper(
            v2_config=self.v2_config,
            db_manager=db_manager,
            logger=logger,
        )

        # 设置回调
        self._setup_callbacks()

        # 注册路由
        self._setup_routes()

    def _setup_callbacks(self):
        """设置回调函数"""
        # 预算警告
        self.cost_controller.on_warning(self._on_budget_warning)
        self.cost_controller.on_exceeded(self._on_budget_exceeded)

        # 配置热切换
        self.hot_swapper.register_handler("v2_config", self._on_config_changed)

    def _on_budget_warning(self, event_type, data):
        """预算警告回调"""
        self.notifier.notify_budget_warning(
            data.get("daily_percent", 0),
            data.get("monthly_percent", 0),
            data.get("currency", "USD"),
        )

    def _on_budget_exceeded(self, event_type, data):
        """预算超限回调"""
        self.notifier.notify_budget_exceeded(
            data.get("daily_used", 0),
            data.get("daily_limit", 0),
            data.get("monthly_used", 0),
            data.get("monthly_limit", 0),
            data.get("currency", "USD"),
        )

    def _on_config_changed(self, path):
        """配置变更回调"""
        if self.logger:
            self.logger.info(f"配置已热更新: {path}")
        # 重新加载相关配置
        self._reload_config()

    def _reload_config(self):
        """重新加载配置"""
        # 更新成本控制
        budget = self.v2_config.get_budget()
        self.cost_controller.daily_limit = budget.get("daily_limit_usd", 5.0)
        self.cost_controller.monthly_limit = budget.get("monthly_limit_usd", 100.0)
        self.cost_controller.warning_threshold = budget.get("warning_threshold", 0.8)
        self.cost_controller.auto_switch_cheap = budget.get("auto_switch_cheap", True)

        # 更新轮询策略
        self.key_rotator.set_strategy(self.v2_config.get_rotation_strategy())

        # 更新通知设置
        notif = self.v2_config.get_notifications()
        self.notifier.configure(
            desktop_enabled=notif.get("desktop_enabled", True),
            webhook_enabled=notif.get("webhook_enabled", False),
            webhook_url=notif.get("webhook_url", ""),
        )

        # 更新路由规则
        rules = self.v2_config.get_routing_rules()
        for task_type, rule_data in rules.items():
            from .smart_router import RoutingRule
            self.smart_router.set_rule(task_type, RoutingRule(
                task_type=task_type,
                description=rule_data.get("description", ""),
                preferred_models=rule_data.get("preferred_models", []),
                fallback_models=rule_data.get("fallback_models", []),
                enabled=rule_data.get("enabled", True),
            ))

    def _setup_routes(self):
        """设置路由"""
        # V1 兼容路由
        self.app.add_url_rule("/v1/chat/completions", view_func=self._chat_completions, methods=["POST"])
        self.app.add_url_rule("/v1/models", view_func=self._list_models, methods=["GET"])
        self.app.add_url_rule("/v1/health", view_func=self._health_check, methods=["GET"])

        # V2 新增路由
        self.app.add_url_rule("/v2/balance", view_func=self._get_balance, methods=["GET"])
        self.app.add_url_rule("/v2/balance/refresh", view_func=self._refresh_balance, methods=["POST"])
        self.app.add_url_rule("/v2/status", view_func=self._get_status, methods=["GET"])
        self.app.add_url_rule("/v2/cost", view_func=self._get_cost, methods=["GET"])
        self.app.add_url_rule("/v2/routing/info", view_func=self._get_routing_info, methods=["POST"])
        self.app.add_url_rule("/v2/config", view_func=self._get_config, methods=["GET"])
        self.app.add_url_rule("/v2/config", view_func=self._update_config, methods=["PUT"])
        self.app.add_url_rule("/v2/notifications", view_func=self._get_notifications, methods=["GET"])
        self.app.add_url_rule("/v2/pricing", view_func=self._get_pricing, methods=["GET"])
        self.app.add_url_rule("/v2/keys/<provider_id>", view_func=self._manage_keys, methods=["GET", "POST", "DELETE"])
        self.app.add_url_rule("/v2/failover/status", view_func=self._get_failover_status, methods=["GET"])
        self.app.add_url_rule("/v2/failover/reset", view_func=self._reset_failover, methods=["POST"])

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

        self.server_thread = threading.Thread(target=run_flask, daemon=True, name="gateway-server-v2")
        self.server_thread.start()
        self._running = True

        # 启动热切换
        if self.v2_config.is_hot_reload_enabled():
            self.hot_swapper.start()

        # 启动余额自动刷新
        balance_config = self.v2_config.get_balance_check()
        if balance_config.get("enabled", True):
            self._start_balance_auto_refresh(balance_config.get("auto_refresh_interval", 300))

        if self.logger:
            self.logger.info(f"V2 AI Gateway 已启动: {self.get_base_url()}")

        return True, f"V2 网关已启动: {self.get_base_url()}"

    def stop(self) -> Tuple[bool, str]:
        """停止网关服务"""
        self._running = False
        self.balance_checker.stop_auto_refresh()
        self.failover_engine.stop_health_check()
        self.hot_swapper.stop()

        if self.logger:
            self.logger.info("V2 AI Gateway 已停止")
        return True, "网关已停止"

    def _start_balance_auto_refresh(self, interval: int):
        """启动余额自动刷新"""
        providers = self._get_all_providers_for_balance()
        if providers:
            self.balance_checker.start_auto_refresh(
                interval=interval,
                providers=providers,
                callback=self._on_balance_refreshed,
            )

    def _get_all_providers_for_balance(self) -> List[Dict]:
        """获取所有供应商（用于余额检测）"""
        if self.db:
            all_providers = self.db.get_all_providers()
            return [{
                "name": p.get("name", ""),
                "type": p.get("provider_type", "custom"),
                "api_key": p.get("api_key", ""),
                "base_url": p.get("base_url", ""),
            } for p in all_providers if p.get("api_key")]
        return []

    def _on_balance_refreshed(self, balances: Dict[str, BalanceInfo]):
        """余额刷新回调"""
        for name, info in balances.items():
            if info.status in {"official", "ok"} and info.balance < self.v2_config.get_notifications().get("low_balance_threshold", 10):
                self.notifier.notify_low_balance(
                    provider=name,
                    balance=info.balance,
                    threshold=self.v2_config.get_notifications().get("low_balance_threshold", 10),
                    currency=info.currency,
                )

    # ==================== V1 兼容接口 ====================

    def _health_check(self):
        """健康检查"""
        return jsonify({
            "status": "ok",
            "service": "AI Gateway V2",
            "version": "2.0.0",
            "url": self.get_base_url(),
            "features": [
                "balance_check",
                "key_rotation",
                "failover",
                "smart_routing",
                "cost_control",
                "pricing",
                "notifications",
                "hot_reload",
            ],
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
                    "input_price": m.get("input_price", 0),
                    "output_price": m.get("output_price", 0),
                    "context_length": m.get("context_length", 128000),
                })

        return jsonify({"object": "list", "data": models})

    def _chat_completions(self):
        """V2 聊天补全 - 集成智能路由和故障转移"""
        start_time = time.monotonic()

        try:
            data = request.get_json(force=True)
        except Exception:
            return jsonify({"error": {"message": "无效的 JSON 请求", "type": "invalid_request_error"}}), 400

        model_name = data.get("model", "")
        messages = data.get("messages", [])
        stream = data.get("stream", False)
        temperature = data.get("temperature", 0.7)
        max_tokens = data.get("max_tokens", 4096)
        explicit_task_type = data.get("task_type")  # V2: 显式任务类型

        if not messages:
            return jsonify({"error": {"message": "消息列表为空", "type": "invalid_request_error"}}), 400

        # 检查预算
        if self.cost_controller.should_switch_to_cheap():
            # 预算超限，强制使用最便宜模型
            cheapest = self.smart_router.get_cheapest_model()
            if cheapest:
                model_name = cheapest.model_name
                if self.logger:
                    self.logger.info(f"预算超限，自动切换至低成本模型: {model_name}")

        # 智能路由选择模型
        if self.v2_config.is_routing_enabled() and not model_name:
            selected = self.smart_router.route(
                messages=messages,
                explicit_task_type=explicit_task_type,
                preferred_model=model_name,
            )
            if selected:
                model_name = selected.model_name

        if not model_name:
            return jsonify({"error": {"message": "未指定模型且路由无可用模型", "type": "model_not_found"}}), 400

        # 获取模型配置
        model_config = None
        if self.db:
            model_config = self.db.get_model_by_name(model_name)

        if not model_config:
            elapsed = int((time.monotonic() - start_time) * 1000)
            self._log_request(model_name, 0, 0, 0, elapsed, "error", f"模型未找到: {model_name}")
            return jsonify({"error": {"message": f"模型未找到: {model_name}", "type": "model_not_found"}}), 404

        # 获取 API Key（支持多 Key 轮询）
        provider_id = model_config.get("provider_id")
        api_key = self._get_api_key_with_rotation(provider_id, model_config)
        if not api_key:
            return jsonify({"error": {"message": "无可用 API Key", "type": "auth_error"}}), 401

        # 构建请求
        base_url = model_config.get("base_url", "")
        auth_mode = model_config.get("auth_mode", "bearer")
        provider_type = model_config.get("provider_type", "custom")

        headers = {"Content-Type": "application/json"}
        if auth_mode == "x-api-key":
            headers["x-api-key"] = api_key
            headers["anthropic-version"] = "2023-06-01"
        else:
            headers["Authorization"] = f"Bearer {api_key}"

        # 构建目标列表用于故障转移
        targets = self._build_failover_targets(model_name, model_config)
        self.failover_engine.set_targets(targets)

        # 执行请求（带故障转移）
        payload = {
            "model": model_name,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,  # V2 暂不通过故障转移支持流式
        }
        if data.get("tools"):
            payload["tools"] = data["tools"]
        if data.get("tool_choice"):
            payload["tool_choice"] = data["tool_choice"]

        try:
            response, used_target = self.failover_engine.execute_with_failover(
                payload, stream=False,
                on_failover=lambda target, attempt: self.notifier.notify_failover(
                    model_name, target.model_name
                ),
            )

            elapsed = int((time.monotonic() - start_time) * 1000)
            result = response.json()

            # 提取使用量
            usage = result.get("usage", {})
            if provider_type == "anthropic":
                prompt_tokens = usage.get("input_tokens", 0)
                completion_tokens = usage.get("output_tokens", 0)
            else:
                prompt_tokens = usage.get("prompt_tokens", 0)
                completion_tokens = usage.get("completion_tokens", 0)
            total_tokens = usage.get("total_tokens", prompt_tokens + completion_tokens)

            # 计算费用
            cost = self.pricing.calculate_cost(model_name, prompt_tokens, completion_tokens)
            self.cost_controller.record_cost(cost.total_cost_usd, model_name)

            # 记录 Key 使用成功
            self.key_rotator.report_success(provider_id, api_key)

            # 记录日志
            self._log_request(model_name, prompt_tokens, completion_tokens, total_tokens,
                             elapsed, "success", "", provider=used_target.provider_name)

            # 构建响应
            if provider_type == "anthropic":
                content_blocks = result.get("content", [])
                reply_text = ""
                for block in content_blocks:
                    if block.get("type") == "text":
                        reply_text += block.get("text", "")
                response_data = {
                    "id": result.get("id", f"chatcmpl-{int(time.time())}"),
                    "object": "chat.completion",
                    "created": int(time.time()),
                    "model": used_target.model_name,
                    "choices": [{
                        "index": 0,
                        "message": {"role": "assistant", "content": reply_text},
                        "finish_reason": "stop" if result.get("stop_reason") == "end_turn" else result.get("stop_reason", "stop"),
                    }],
                    "usage": {
                        "prompt_tokens": prompt_tokens,
                        "completion_tokens": completion_tokens,
                        "total_tokens": total_tokens,
                    },
                    "cost": {
                        "usd": round(cost.total_cost_usd, 6),
                        "cny": round(cost.total_cost_cny, 6),
                    },
                }
            else:
                response_data = {
                    "id": result.get("id", f"chatcmpl-{int(time.time())}"),
                    "object": "chat.completion",
                    "created": int(time.time()),
                    "model": used_target.model_name,
                    "choices": result.get("choices", []),
                    "usage": {
                        "prompt_tokens": prompt_tokens,
                        "completion_tokens": completion_tokens,
                        "total_tokens": total_tokens,
                    },
                    "cost": {
                        "usd": round(cost.total_cost_usd, 6),
                        "cny": round(cost.total_cost_cny, 6),
                    },
                }

            return jsonify(response_data), 200

        except FailoverExhausted as e:
            elapsed = int((time.monotonic() - start_time) * 1000)
            self._log_request(model_name, 0, 0, 0, elapsed, "error", str(e))
            self.notifier.notify_api_error(
                provider=model_config.get("provider_name", "unknown"),
                error=str(e),
                model=model_name,
            )
            return jsonify({"error": {"message": str(e), "type": "failover_exhausted"}}), 503

        except requests.exceptions.Timeout:
            elapsed = int((time.monotonic() - start_time) * 1000)
            self._log_request(model_name, 0, 0, 0, elapsed, "error", "请求超时")
            return jsonify({"error": {"message": "请求超时", "type": "timeout_error"}}), 504

        except requests.exceptions.RequestException as e:
            elapsed = int((time.monotonic() - start_time) * 1000)
            error_str = str(e)[:200]
            self._log_request(model_name, 0, 0, 0, elapsed, "error", error_str)

            # 报告 Key 错误
            if hasattr(e, 'response') and e.response:
                status = e.response.status_code
                if status == 429:
                    self.key_rotator.report_rate_limit(provider_id, api_key)
                elif status in (401, 403):
                    self.key_rotator.report_error(provider_id, api_key, f"认证失败: {status}")
                elif status >= 500:
                    self.key_rotator.report_error(provider_id, api_key, f"服务器错误: {status}")

            return jsonify({"error": {"message": f"请求失败: {error_str}", "type": "proxy_error"}}), 502

    def _get_api_key_with_rotation(self, provider_id: str, model_config: Dict) -> str:
        """获取 API Key（支持多 Key 轮询）"""
        # 先尝试多 Key 轮询
        rotator_key = self.key_rotator.get_current_key(provider_id)
        if rotator_key:
            return rotator_key

        # 回退到数据库中的 Key
        if self.db:
            provider = self.db.get_provider(provider_id)
            if provider:
                return provider.get("api_key", "")
        return model_config.get("api_key", "")

    def _build_failover_targets(self, model_name: str, model_config: Dict) -> List[FailoverTarget]:
        """构建故障转移目标列表"""
        targets = []
        provider_id = model_config.get("provider_id", "")
        provider_type = model_config.get("provider_type", "custom")
        base_url = model_config.get("base_url", "")
        auth_mode = model_config.get("auth_mode", "bearer")

        # 主目标
        api_key = self._get_api_key_with_rotation(provider_id, model_config)
        if api_key:
            targets.append(FailoverTarget(
                model_name=model_name,
                provider_id=provider_id,
                provider_name=model_config.get("provider_name", ""),
                base_url=base_url,
                api_key=api_key,
                auth_mode=auth_mode,
                provider_type=provider_type,
                priority=0,
            ))

        # 添加其他可用模型作为备选
        if self.db and self.v2_config.is_routing_enabled():
            all_models = self.db.get_enabled_models()
            rule = self.v2_config.get_routing_rule("chat")
            if rule:
                for i, fallback_model in enumerate(rule.get("fallback_models", [])):
                    for m in all_models:
                        if m.get("model_name") == fallback_model and m.get("model_name") != model_name:
                            targets.append(FailoverTarget(
                                model_name=m.get("model_name"),
                                provider_id=m.get("provider_id", ""),
                                provider_name=m.get("provider_name", ""),
                                base_url=m.get("base_url", ""),
                                api_key=m.get("api_key", ""),
                                auth_mode=m.get("auth_mode", "bearer"),
                                provider_type=m.get("provider_type", "custom"),
                                priority=i + 1,
                            ))

        return targets

    def _log_request(self, model: str, input_tokens: int, output_tokens: int,
                     total_tokens: int, response_time_ms: int, status: str, error: str = "",
                     provider: str = ""):
        """记录请求日志"""
        if self.db:
            if not provider and model:
                model_config = self.db.get_model_by_name(model)
                provider = (model_config or {}).get("provider_name", "")
            self.db.log_request({
                "model": model,
                "provider": provider,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": total_tokens,
                "response_time_ms": response_time_ms,
                "status": status,
                "error": error[:500] if error else "",
            })
        if self.logger and status == "error":
            self.logger.error(f"Gateway [{model}] {status}: {error}")

    # ==================== V2 新增接口 ====================

    def _get_balance(self):
        """获取余额信息"""
        cached = self.balance_checker.get_all_cached()
        if not cached:
            # 首次检测
            providers = self._get_all_providers_for_balance()
            if providers:
                cached = self.balance_checker.check_all(providers)

        result = {}
        for name, info in cached.items():
            result[name] = info.to_dict()
        return jsonify({"balances": result})

    def _refresh_balance(self):
        """刷新余额信息"""
        providers = self._get_all_providers_for_balance()
        if not providers:
            return jsonify({"error": "无可用供应商"}), 400

        def _do_refresh():
            self.balance_checker.check_all(providers)

        threading.Thread(target=_do_refresh, daemon=True).start()
        return jsonify({"message": "余额刷新已启动", "providers": len(providers)})

    def _get_status(self):
        """获取网关状态"""
        return jsonify({
            "status": "running" if self._running else "stopped",
            "version": "2.0.0",
            "url": self.get_base_url(),
            "balance_check": self.v2_config.get_balance_check().get("enabled", True),
            "routing_enabled": self.v2_config.is_routing_enabled(),
            "key_rotation_enabled": self.v2_config.is_key_rotation_enabled(),
            "hot_reload": self.hot_swapper.is_running(),
            "uptime": int(time.time()),
        })

    def _get_cost(self):
        """获取费用统计"""
        status = self.cost_controller.get_status()
        daily_by_model = self.cost_controller.get_daily_usage_by_model()
        monthly_by_model = self.cost_controller.get_monthly_usage_by_model()

        return jsonify({
            "daily": {
                "limit": status.daily_limit,
                "used": status.daily_used,
                "remaining": status.daily_remaining,
                "percent": status.daily_percent,
                "by_model": daily_by_model,
            },
            "monthly": {
                "limit": status.monthly_limit,
                "used": status.monthly_used,
                "remaining": status.monthly_remaining,
                "percent": status.monthly_percent,
                "by_model": monthly_by_model,
            },
            "currency": status.currency,
            "warning_triggered": status.warning_triggered,
            "budget_exceeded": status.budget_exceeded,
        })

    def _get_routing_info(self):
        """获取路由信息"""
        data = request.get_json(force=True) if request.data else {}
        messages = data.get("messages", [])
        explicit_type = data.get("task_type")

        info = self.smart_router.get_routing_info(messages, explicit_type)
        return jsonify(info)

    def _get_config(self):
        """获取 V2 配置"""
        return jsonify(self.v2_config.export_config())

    def _update_config(self):
        """更新 V2 配置（热切换）"""
        data = request.get_json(force=True)
        if self.v2_config.import_config(data):
            self._reload_config()
            return jsonify({"message": "配置已更新"})
        return jsonify({"error": "配置更新失败"}), 400

    def _get_notifications(self):
        """获取通知历史"""
        history = self.notifier.get_history(50)
        return jsonify({
            "notifications": [n.to_dict() for n in history],
            "count": len(history),
        })

    def _get_pricing(self):
        """获取价格表"""
        return jsonify({
            "exchange_rate": self.pricing.get_exchange_rate(),
            "models": self.pricing.get_pricing_table(),
        })

    def _manage_keys(self, provider_id: str):
        """管理供应商的多 Key"""
        if request.method == "GET":
            # 获取 Key 状态
            status = self.key_rotator.get_key_status(provider_id)
            summary = self.key_rotator.get_rotation_summary(provider_id)
            return jsonify({"keys": status, "summary": summary})

        elif request.method == "POST":
            # 添加 Key
            data = request.get_json(force=True)
            api_key = data.get("api_key", "")
            if api_key:
                self.key_rotator.add_key(provider_id, api_key)
                # 同步到 V2 配置
                self.v2_config.add_key(provider_id, api_key)
                return jsonify({"message": "Key 已添加"})
            return jsonify({"error": "缺少 api_key"}), 400

        elif request.method == "DELETE":
            # 删除 Key
            data = request.get_json(force=True)
            index = data.get("index", -1)
            if self.key_rotator.remove_key(provider_id, index):
                return jsonify({"message": "Key 已删除"})
            return jsonify({"error": "删除失败"}), 400

    def _get_failover_status(self):
        """获取故障转移状态"""
        status = self.failover_engine.get_target_status()
        return jsonify({"targets": status})

    def _reset_failover(self):
        """重置故障转移"""
        self.failover_engine.reset_all_circuits()
        return jsonify({"message": "故障转移已重置"})
