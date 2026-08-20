"""
V3 AI 智能调度器
================
智能模型选择、负载均衡、成本优化

功能：
- 基于任务特征智能选择最优模型
- 实时性能监控 + 动态调整
- 成本感知调度
- 负载均衡
"""
import time
import threading
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from collections import defaultdict


@dataclass
class ModelMetrics:
    """模型性能指标"""
    model: str
    total_requests: int = 0
    success_count: int = 0
    error_count: int = 0
    total_latency_ms: int = 0
    total_cost: float = 0.0
    last_used: int = 0
    avg_latency_ms: float = 0.0
    success_rate: float = 100.0

    def record_request(self, latency_ms: int, success: bool, cost: float):
        """记录请求"""
        self.total_requests += 1
        self.total_latency_ms += latency_ms
        self.total_cost += cost
        self.last_used = int(time.time())
        if success:
            self.success_count += 1
        else:
            self.error_count += 1
        self.avg_latency_ms = self.total_latency_ms / self.total_requests
        self.success_rate = self.success_count / self.total_requests * 100


@dataclass
class ScheduleDecision:
    """调度决策"""
    model: str
    provider: str
    reason: str
    estimated_cost: float
    estimated_latency: int
    confidence: float  # 0-1


class SmartScheduler:
    """智能调度器"""

    def __init__(self, pricing_calculator=None, logger=None):
        self.pricing_calculator = pricing_calculator
        self.logger = logger
        self._metrics: Dict[str, ModelMetrics] = {}
        self._lock = threading.RLock()
        self._strategy = "balanced"  # balanced / speed / cost / quality

        # 模型能力评分 (1-10)
        self._capability_scores = {
            "claude-opus-4": {"quality": 10, "speed": 6, "cost": 3, "coding": 10},
            "claude-sonnet-4": {"quality": 9, "speed": 7, "cost": 5, "coding": 9},
            "claude-haiku-3.5": {"quality": 7, "speed": 9, "cost": 8, "coding": 7},
            "gpt-4o": {"quality": 9, "speed": 7, "cost": 4, "coding": 8},
            "gpt-4o-mini": {"quality": 7, "speed": 9, "cost": 9, "coding": 7},
            "deepseek-chat": {"quality": 8, "speed": 8, "cost": 9, "coding": 8},
            "deepseek-reasoner": {"quality": 9, "speed": 6, "cost": 8, "coding": 9},
            "gemini-1.5-pro": {"quality": 9, "speed": 7, "cost": 5, "coding": 8},
            "gemini-2.0-flash": {"quality": 8, "speed": 9, "cost": 7, "coding": 7},
            "kimi-v1-128k": {"quality": 8, "speed": 7, "cost": 7, "coding": 7},
            "longcat-2.0": {"quality": 7, "speed": 8, "cost": 9, "coding": 7},
            "longcat-flash": {"quality": 6, "speed": 10, "cost": 10, "coding": 6},
        }

    def set_strategy(self, strategy: str):
        """设置调度策略"""
        valid = ["balanced", "speed", "cost", "quality"]
        if strategy in valid:
            self._strategy = strategy

    def get_strategy(self) -> str:
        """获取当前策略"""
        return self._strategy

    def record_result(self, model: str, latency_ms: int, success: bool,
                      cost: float):
        """记录请求结果"""
        with self._lock:
            if model not in self._metrics:
                self._metrics[model] = ModelMetrics(model=model)
            self._metrics[model].record_request(latency_ms, success, cost)

    def schedule(self, task_type: str = "chat", prompt_length: int = 0,
                 require_coding: bool = False, require_long_context: bool = False,
                 preferred_models: List[str] = None) -> ScheduleDecision:
        """
        智能调度 - 选择最优模型
        """
        with self._lock:
            candidates = preferred_models or list(self._capability_scores.keys())
            scores = []

            for model in candidates:
                capability = self._capability_scores.get(model)
                if not capability:
                    continue

                # 基础评分
                score = self._calculate_score(capability, model, task_type,
                                              require_coding, require_long_context)

                # 根据策略调整
                if self._strategy == "speed":
                    score *= capability["speed"] / 10
                elif self._strategy == "cost":
                    score *= capability["cost"] / 10
                elif self._strategy == "quality":
                    score *= capability["quality"] / 10

                # 历史性能调整
                metrics = self._metrics.get(model)
                if metrics and metrics.total_requests > 5:
                    score *= metrics.success_rate / 100
                    # 惩罚高延迟
                    if metrics.avg_latency_ms > 5000:
                        score *= 0.8

                scores.append((model, score, capability))

            if not scores:
                return ScheduleDecision(
                    model="claude-sonnet-4",
                    provider="anthropic",
                    reason="默认选择（无候选模型）",
                    estimated_cost=0.0,
                    estimated_latency=2000,
                    confidence=0.5,
                )

            # 选择最高分
            best = max(scores, key=lambda x: x[1])
            model, score, capability = best

            # 估算成本
            estimated_cost = 0.0
            if self.pricing_calculator:
                estimated_cost = self.pricing_calculator.estimate_cost(
                    model, prompt_length, 1000
                )

            # 生成决策原因
            reason = self._generate_reason(model, capability, task_type)

            return ScheduleDecision(
                model=model,
                provider=self._get_provider(model),
                reason=reason,
                estimated_cost=estimated_cost,
                estimated_latency=int(self._metrics[model].avg_latency_ms) if model in self._metrics else 2000,
                confidence=min(score / 10, 1.0),
            )

    def _calculate_score(self, capability: Dict, model: str, task_type: str,
                         require_coding: bool, require_long_context: bool) -> float:
        """计算模型评分"""
        score = capability["quality"] * 0.3 + capability["speed"] * 0.2 + capability["cost"] * 0.2

        if require_coding:
            score += capability.get("coding", 5) * 0.3

        if task_type == "code":
            score += capability.get("coding", 5) * 0.2
        elif task_type == "cheap":
            score += capability["cost"] * 0.3
        elif task_type == "complex":
            score += capability["quality"] * 0.3

        return score

    def _generate_reason(self, model: str, capability: Dict, task_type: str) -> str:
        """生成选择原因"""
        reasons = []
        if capability["quality"] >= 9:
            reasons.append("高质量")
        if capability["speed"] >= 9:
            reasons.append("响应快")
        if capability["cost"] >= 9:
            reasons.append("成本低")
        if capability.get("coding", 0) >= 9:
            reasons.append("代码能力强")

        strategy_names = {
            "balanced": "均衡策略",
            "speed": "速度优先",
            "cost": "成本优先",
            "quality": "质量优先",
        }
        strategy_name = strategy_names.get(self._strategy, "均衡策略")

        reason_str = "、".join(reasons) if reasons else "综合评分最高"
        return f"[{strategy_name}] {model}: {reason_str}"

    def _get_provider(self, model: str) -> str:
        """获取模型对应的供应商"""
        provider_map = {
            "claude": "anthropic",
            "gpt": "openai",
            "deepseek": "deepseek",
            "gemini": "google",
            "kimi": "kimi",
            "longcat": "longcat",
        }
        for key, provider in provider_map.items():
            if model.startswith(key):
                return provider
        return "unknown"

    def get_metrics(self) -> List[Dict]:
        """获取所有模型指标"""
        with self._lock:
            return [
                {
                    "model": m.model,
                    "total_requests": m.total_requests,
                    "success_rate": round(m.success_rate, 1),
                    "avg_latency_ms": round(m.avg_latency_ms),
                    "total_cost": round(m.total_cost, 4),
                    "last_used": m.last_used,
                }
                for m in self._metrics.values()
            ]

    def get_recommendations(self) -> List[Dict]:
        """获取模型推荐"""
        recommendations = []

        # 按场景推荐
        scenarios = [
            ("编程开发", {"require_coding": True, "task_type": "code"}),
            ("日常对话", {"task_type": "chat"}),
            ("低成本任务", {"task_type": "cheap"}),
            ("复杂推理", {"task_type": "complex"}),
        ]

        for name, kwargs in scenarios:
            decision = self.schedule(**kwargs)
            recommendations.append({
                "scenario": name,
                "recommended_model": decision.model,
                "reason": decision.reason,
                "confidence": decision.confidence,
            })

        return recommendations

    def get_stats(self) -> Dict:
        """获取调度统计"""
        with self._lock:
            total_requests = sum(m.total_requests for m in self._metrics.values())
            return {
                "strategy": self._strategy,
                "tracked_models": len(self._metrics),
                "total_requests": total_requests,
                "models": self.get_metrics(),
            }
