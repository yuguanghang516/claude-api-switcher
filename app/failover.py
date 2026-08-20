"""
V2 自动故障转移模块
实现：
请求失败 → 模型A → 失败 → 模型B → 失败 → 模型C
用户无感

特性：
- 熔断器模式：连续失败达到阈值后自动熔断
- 自动恢复：熔断后经过重置时间自动尝试恢复
- 指数退避：重试间隔递增
- 健康检查：定期检测已熔断的模型是否恢复
"""
import time
import threading
import requests
from typing import Dict, List, Optional, Callable, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum


class CircuitState(Enum):
    """熔断器状态"""
    CLOSED = "closed"       # 正常
    OPEN = "open"           # 熔断
    HALF_OPEN = "half_open"  # 半开（尝试恢复）


@dataclass
class FailoverTarget:
    """故障转移目标"""
    model_name: str
    provider_id: str
    provider_name: str
    base_url: str
    api_key: str
    auth_mode: str = "bearer"
    provider_type: str = "custom"
    priority: int = 0  # 越小优先级越高
    is_healthy: bool = True
    consecutive_failures: int = 0
    last_failure_time: int = 0
    total_requests: int = 0
    failed_requests: int = 0

    def to_dict(self) -> Dict:
        return {
            "model_name": self.model_name,
            "provider_name": self.provider_name,
            "priority": self.priority,
            "is_healthy": self.is_healthy,
            "consecutive_failures": self.consecutive_failures,
            "total_requests": self.total_requests,
            "failed_requests": self.failed_requests,
        }


class CircuitBreaker:
    """熔断器"""

    def __init__(self, threshold: int = 5, reset_seconds: int = 60):
        self.threshold = threshold
        self.reset_seconds = reset_seconds
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time = 0
        self._lock = threading.Lock()

    @property
    def state(self) -> CircuitState:
        with self._lock:
            if self._state == CircuitState.OPEN:
                # 检查是否到了恢复时间
                if int(time.time()) - self._last_failure_time >= self.reset_seconds:
                    self._state = CircuitState.HALF_OPEN
            return self._state

    def record_success(self):
        """记录成功"""
        with self._lock:
            self._failure_count = 0
            self._state = CircuitState.CLOSED

    def record_failure(self):
        """记录失败"""
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = int(time.time())
            if self._failure_count >= self.threshold:
                self._state = CircuitState.OPEN

    def can_execute(self) -> bool:
        """是否可以执行"""
        state = self.state
        return state in (CircuitState.CLOSED, CircuitState.HALF_OPEN)

    def reset(self):
        """手动重置"""
        with self._lock:
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._last_failure_time = 0


class FailoverEngine:
    """故障转移引擎"""

    def __init__(self, max_retries: int = 3, retry_delay_ms: int = 1000,
                 timeout_seconds: int = 30, circuit_threshold: int = 5,
                 circuit_reset_seconds: int = 60, logger=None):
        self.max_retries = max_retries
        self.retry_delay_ms = retry_delay_ms
        self.timeout_seconds = timeout_seconds
        self.logger = logger

        # 故障转移目标列表
        self._targets: List[FailoverTarget] = []
        self._circuit_breakers: Dict[str, CircuitBreaker] = {}
        self._circuit_threshold = circuit_threshold
        self._circuit_reset_seconds = circuit_reset_seconds

        self._lock = threading.RLock()
        self._health_check_timer: Optional[threading.Timer] = None

    def set_targets(self, targets: List[FailoverTarget]):
        """设置故障转移目标列表"""
        with self._lock:
            self._targets = sorted(targets, key=lambda t: t.priority)
            # 为每个目标创建熔断器
            self._circuit_breakers = {}
            for t in self._targets:
                key = f"{t.provider_id}:{t.model_name}"
                self._circuit_breakers[key] = CircuitBreaker(
                    threshold=self._circuit_threshold,
                    reset_seconds=self._circuit_reset_seconds,
                )

    def add_target(self, target: FailoverTarget):
        """添加故障转移目标"""
        with self._lock:
            key = f"{target.provider_id}:{target.model_name}"
            if key not in self._circuit_breakers:
                self._circuit_breakers[key] = CircuitBreaker(
                    threshold=self._circuit_threshold,
                    reset_seconds=self._circuit_reset_seconds,
                )
            self._targets.append(target)
            self._targets.sort(key=lambda t: t.priority)

    def remove_target(self, model_name: str, provider_id: str):
        """移除故障转移目标"""
        with self._lock:
            self._targets = [t for t in self._targets
                           if not (t.model_name == model_name and t.provider_id == provider_id)]
            key = f"{provider_id}:{model_name}"
            self._circuit_breakers.pop(key, None)

    def get_healthy_targets(self) -> List[FailoverTarget]:
        """获取健康的目标列表"""
        with self._lock:
            healthy = []
            for t in self._targets:
                key = f"{t.provider_id}:{t.model_name}"
                cb = self._circuit_breakers.get(key)
                if cb and cb.can_execute():
                    healthy.append(t)
            return healthy

    def execute_with_failover(self, payload: Dict, stream: bool = False,
                              on_failover: Callable = None) -> Tuple[Any, Optional[FailoverTarget]]:
        """
        执行请求，自动故障转移
        :param payload: 请求数据
        :param stream: 是否流式
        :param failover: 每次失败时调用
        :return: (response, used_target)
        """
        targets = self.get_healthy_targets()
        if not targets:
            # 尝试重置所有熔断器
            self.reset_all_circuits()
            targets = self.get_healthy_targets()

        if not targets:
            raise FailoverExhausted("所有故障转移目标均不可用")

        last_error = None
        for attempt, target in enumerate(targets):
            key = f"{target.provider_id}:{target.model_name}"
            cb = self._circuit_breakers.get(key)

            if not cb or not cb.can_execute():
                continue

            # 重试逻辑
            for retry in range(self.max_retries):
                try:
                    response = self._do_request(target, payload, stream)
                    # 成功
                    cb.record_success()
                    target.is_healthy = True
                    target.consecutive_failures = 0
                    target.total_requests += 1

                    if attempt > 0 and on_failover:
                        on_failover(target, attempt)

                    return response, target

                except requests.exceptions.Timeout:
                    last_error = "请求超时"
                    target.consecutive_failures += 1
                except requests.exceptions.ConnectionError as e:
                    last_error = f"连接失败: {str(e)[:50]}"
                    target.consecutive_failures += 1
                except requests.exceptions.HTTPError as e:
                    status = e.response.status_code if e.response else 0
                    if status == 429:
                        last_error = "请求限流"
                        target.consecutive_failures += 1
                    elif status >= 500:
                        last_error = f"服务器错误: HTTP {status}"
                        target.consecutive_failures += 1
                    else:
                        last_error = f"HTTP 错误: {status}"
                        target.consecutive_failures += 1
                        break  # 4xx 错误不重试
                except Exception as e:
                    last_error = str(e)[:100]
                    target.consecutive_failures += 1

                # 指数退避
                if retry < self.max_retries - 1:
                    delay = (self.retry_delay_ms / 1000) * (2 ** retry)
                    time.sleep(delay)

            # 所有重试失败
            cb.record_failure()
            target.failed_requests += 1
            target.last_failure_time = int(time.time())
            target.is_healthy = target.consecutive_failures < self._circuit_threshold

        raise FailoverExhausted(f"所有目标执行失败，最后一个错误: {last_error}")

    def _do_request(self, target: FailoverTarget, payload: Dict,
                    stream: bool) -> requests.Response:
        """执行实际请求"""
        url = target.base_url.rstrip("/")
        if target.provider_type == "anthropic":
            if not url.endswith("/messages"):
                url = f"{url}/messages"
        else:
            if not url.endswith("/chat/completions"):
                url = f"{url}/chat/completions"

        headers = {"Content-Type": "application/json"}
        if target.auth_mode == "x-api-key":
            headers["x-api-key"] = target.api_key
            headers["anthropic-version"] = "2023-06-01"
        else:
            headers["Authorization"] = f"Bearer {target.api_key}"

        resp = requests.post(
            url, headers=headers, json=payload,
            timeout=self.timeout_seconds, stream=stream,
        )
        resp.raise_for_status()
        return resp

    def get_target_status(self) -> List[Dict]:
        """获取所有目标状态"""
        with self._lock:
            result = []
            for t in self._targets:
                key = f"{t.provider_id}:{t.model_name}"
                cb = self._circuit_breakers.get(key)
                info = t.to_dict()
                info["circuit_state"] = cb.state.value if cb else "unknown"
                result.append(info)
            return result

    def reset_all_circuits(self):
        """重置所有熔断器"""
        with self._lock:
            for cb in self._circuit_breakers.values():
                cb.reset()
            for t in self._targets:
                t.is_healthy = True
                t.consecutive_failures = 0

    def reset_circuit(self, model_name: str, provider_id: str):
        """重置指定目标的熔断器"""
        with self._lock:
            key = f"{provider_id}:{model_name}"
            cb = self._circuit_breakers.get(key)
            if cb:
                cb.reset()
            for t in self._targets:
                if t.model_name == model_name and t.provider_id == provider_id:
                    t.is_healthy = True
                    t.consecutive_failures = 0

    def start_health_check(self, interval: int = 60, callback: Callable = None):
        """启动定期健康检查"""
        def _check():
            self._run_health_check()
            if callback:
                try:
                    callback(self.get_target_status())
                except Exception:
                    pass
            self._health_check_timer = threading.Timer(interval, _check)
            self._health_check_timer.daemon = True
            self._health_check_timer.start()

        self._health_check_timer = threading.Timer(interval, _check)
        self._health_check_timer.daemon = True
        self._health_check_timer.start()

    def stop_health_check(self):
        """停止健康检查"""
        if self._health_check_timer:
            self._health_check_timer.cancel()
            self._health_check_timer = None

    def _run_health_check(self):
        """执行健康检查"""
        for target in self._targets:
            key = f"{target.provider_id}:{target.model_name}"
            cb = self._circuit_breakers.get(key)
            if not cb:
                continue

            # 只检查熔断状态的目标
            if cb.state == CircuitState.OPEN:
                try:
                    # 发送最小请求检查
                    url = target.base_url.rstrip("/")
                    if target.provider_type == "anthropic":
                        if not url.endswith("/messages"):
                            url = f"{url}/messages"
                        payload = {
                            "model": target.model_name,
                            "max_tokens": 1,
                            "messages": [{"role": "user", "content": "hi"}],
                        }
                    else:
                        if not url.endswith("/chat/completions"):
                            url = f"{url}/chat/completions"
                        payload = {
                            "model": target.model_name,
                            "max_tokens": 1,
                            "messages": [{"role": "user", "content": "hi"}],
                        }

                    headers = {"Content-Type": "application/json"}
                    if target.auth_mode == "x-api-key":
                        headers["x-api-key"] = target.api_key
                        headers["anthropic-version"] = "2023-06-01"
                    else:
                        headers["Authorization"] = f"Bearer {target.api_key}"

                    resp = requests.post(url, headers=headers, json=payload, timeout=10)
                    if resp.status_code == 200:
                        cb.reset()
                        target.is_healthy = True
                        target.consecutive_failures = 0
                except Exception:
                    pass


class FailoverExhausted(Exception):
    """所有故障转移目标均失败"""
    pass
