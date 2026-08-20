"""
V2 成本控制模块
功能：
- 每日预算
- 每月预算
- 80% 提醒
- 100% 自动切换低成本模型
"""
import time
import threading
from typing import Dict, Optional, Callable, List
from dataclasses import dataclass
from datetime import date, timedelta


@dataclass
class BudgetStatus:
    """预算状态"""
    daily_limit: float
    daily_used: float
    daily_remaining: float
    daily_percent: float
    monthly_limit: float
    monthly_used: float
    monthly_remaining: float
    monthly_percent: float
    warning_triggered: bool
    budget_exceeded: bool
    currency: str = "USD"

    def to_dict(self) -> Dict:
        return {
            "daily_limit": self.daily_limit,
            "daily_used": self.daily_used,
            "daily_remaining": self.daily_remaining,
            "daily_percent": self.daily_percent,
            "monthly_limit": self.monthly_limit,
            "monthly_used": self.monthly_used,
            "monthly_remaining": self.monthly_remaining,
            "monthly_percent": self.monthly_percent,
            "warning_triggered": self.warning_triggered,
            "budget_exceeded": self.budget_exceeded,
            "currency": self.currency,
        }


class CostController:
    """成本控制器"""

    def __init__(self, daily_limit: float = 5.0, monthly_limit: float = 100.0,
                 warning_threshold: float = 0.8, auto_switch_cheap: bool = True,
                 currency: str = "USD", logger=None):
        self.daily_limit = daily_limit
        self.monthly_limit = monthly_limit
        self.warning_threshold = warning_threshold
        self.auto_switch_cheap = auto_switch_cheap
        self.currency = currency
        self.logger = logger

        # 使用量追踪 {date_str: {model: cost}}
        self._daily_usage: Dict[str, Dict[str, float]] = {}
        self._lock = threading.Lock()

        # 回调
        self._warning_callbacks: List[Callable] = []
        self._exceeded_callbacks: List[Callable] = []

        # 状态
        self._warning_triggered_today = False
        self._budget_exceeded_today = False
        self._last_reset_date = date.today().isoformat()

    def record_cost(self, cost: float, model: str = "unknown"):
        """
        记录一次请求的花费
        :param cost: 花费金额（美元）
        :param model: 模型名称
        """
        with self._lock:
            self._check_day_reset()
            today = date.today().isoformat()
            if today not in self._daily_usage:
                self._daily_usage[today] = {}
            if model not in self._daily_usage[today]:
                self._daily_usage[today][model] = 0
            self._daily_usage[today][model] += cost

    def get_status(self) -> BudgetStatus:
        """获取当前预算状态"""
        with self._lock:
            self._check_day_reset()
            today = date.today().isoformat()

            # 今日花费
            daily_used = sum(self._daily_usage.get(today, {}).values())

            # 本月花费
            month_start = date.today().replace(day=1).isoformat()
            monthly_used = 0
            for date_str, models in self._daily_usage.items():
                if date_str >= month_start:
                    monthly_used += sum(models.values())

            daily_remaining = max(0, self.daily_limit - daily_used)
            monthly_remaining = max(0, self.monthly_limit - monthly_used)
            daily_percent = (daily_used / self.daily_limit * 100) if self.daily_limit > 0 else 0
            monthly_percent = (monthly_used / self.monthly_limit * 100) if self.monthly_limit > 0 else 0

            warning = daily_percent >= (self.warning_threshold * 100) or \
                     monthly_percent >= (self.warning_threshold * 100)
            exceeded = daily_percent >= 100 or monthly_percent >= 100

            # 触发回调
            if warning and not self._warning_triggered_today:
                self._warning_triggered_today = True
                for cb in self._warning_callbacks:
                    try:
                        cb("warning", self.to_dict(daily_used, monthly_used,
                            daily_remaining, monthly_remaining,
                            daily_percent, monthly_percent))
                    except Exception:
                        pass

            if exceeded and not self._budget_exceeded_today:
                self._budget_exceeded_today = True
                for cb in self._exceeded_callbacks:
                    try:
                        cb("exceeded", self.to_dict(daily_used, monthly_used,
                            daily_remaining, monthly_remaining,
                            daily_percent, monthly_percent))
                    except Exception:
                        pass

            return BudgetStatus(
                daily_limit=self.daily_limit,
                daily_used=round(daily_used, 4),
                daily_remaining=round(daily_remaining, 4),
                daily_percent=round(daily_percent, 1),
                monthly_limit=self.monthly_limit,
                monthly_used=round(monthly_used, 4),
                monthly_remaining=round(monthly_remaining, 4),
                monthly_percent=round(monthly_percent, 1),
                warning_triggered=self._warning_triggered_today,
                budget_exceeded=self._budget_exceeded_today,
                currency=self.currency,
            )

    def to_dict(self, daily_used, monthly_used, daily_remaining,
                monthly_remaining, daily_percent, monthly_percent) -> Dict:
        return {
            "daily_used": round(daily_used, 4),
            "daily_limit": self.daily_limit,
            "daily_remaining": round(daily_remaining, 4),
            "daily_percent": round(daily_percent, 1),
            "monthly_used": round(monthly_used, 4),
            "monthly_limit": self.monthly_limit,
            "monthly_remaining": round(monthly_remaining, 4),
            "monthly_percent": round(monthly_percent, 1),
        }

    def should_switch_to_cheap(self) -> bool:
        """是否应该切换到低成本模型"""
        if not self.auto_switch_cheap:
            return False
        status = self.get_status()
        return status.budget_exceeded

    def is_within_budget(self) -> bool:
        """是否还在预算内"""
        status = self.get_status()
        return not status.budget_exceeded

    def get_daily_usage_by_model(self) -> Dict[str, float]:
        """获取今日各模型花费"""
        with self._lock:
            today = date.today().isoformat()
            return dict(self._daily_usage.get(today, {}))

    def get_monthly_usage_by_model(self) -> Dict[str, float]:
        """获取本月各模型花费"""
        with self._lock:
            month_start = date.today().replace(day=1).isoformat()
            model_costs: Dict[str, float] = {}
            for date_str, models in self._daily_usage.items():
                if date_str >= month_start:
                    for model, cost in models.items():
                        model_costs[model] = model_costs.get(model, 0) + cost
            return model_costs

    def set_daily_limit(self, limit: float):
        """设置每日预算"""
        self.daily_limit = max(0, limit)

    def set_monthly_limit(self, limit: float):
        """设置每月预算"""
        self.monthly_limit = max(0, limit)

    def set_warning_threshold(self, threshold: float):
        """设置警告阈值"""
        self.warning_threshold = max(0, min(1, threshold))

    def on_warning(self, callback: Callable):
        """注册预算警告回调"""
        self._warning_callbacks.append(callback)

    def on_exceeded(self, callback: Callable):
        """注册预算超限回调"""
        self._exceeded_callbacks.append(callback)

    def reset_daily(self):
        """重置每日统计"""
        with self._lock:
            today = date.today().isoformat()
            self._daily_usage.pop(today, None)
            self._warning_triggered_today = False
            self._budget_exceeded_today = False

    def cleanup_old_data(self, days: int = 30):
        """清理旧数据"""
        with self._lock:
            cutoff = (date.today() - timedelta(days=days)).isoformat()
            self._daily_usage = {
                k: v for k, v in self._daily_usage.items()
                if k >= cutoff
            }

    def _check_day_reset(self):
        """检查是否需要重置每日状态"""
        today = date.today().isoformat()
        if today != self._last_reset_date:
            self._warning_triggered_today = False
            self._budget_exceeded_today = False
            self._last_reset_date = today
