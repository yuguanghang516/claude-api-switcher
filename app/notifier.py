"""
V2 通知系统模块
支持：
- 余额不足提醒
- API 异常提醒
- 预算超限提醒

通知方式：
- 桌面通知
- Webhook（可选）
"""
import json
import threading
import time
import requests
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass, field
from enum import Enum


class NotificationType(Enum):
    """通知类型"""
    LOW_BALANCE = "low_balance"
    API_ERROR = "api_error"
    BUDGET_EXCEEDED = "budget_exceeded"
    BUDGET_WARNING = "budget_warning"
    KEY_ROTATED = "key_rotated"
    FAILOVER_TRIGGERED = "failover_triggered"
    INFO = "info"


class NotificationPriority(Enum):
    """通知优先级"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class Notification:
    """通知数据"""
    type: NotificationType
    title: str
    message: str
    priority: NotificationPriority = NotificationPriority.MEDIUM
    timestamp: int = 0
    data: Dict = field(default_factory=dict)

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = int(time.time())

    def to_dict(self) -> Dict:
        return {
            "type": self.type.value,
            "title": self.title,
            "message": self.message,
            "priority": self.priority.value,
            "timestamp": self.timestamp,
            "data": self.data,
        }


class Notifier:
    """通知管理器"""

    def __init__(self, desktop_enabled: bool = True,
                 webhook_enabled: bool = False,
                 webhook_url: str = "",
                 min_interval: int = 60,
                 logger=None):
        self.desktop_enabled = desktop_enabled
        self.webhook_enabled = webhook_enabled
        self.webhook_url = webhook_url
        self.logger = logger

        self._history: List[Notification] = []
        self._max_history = 100
        self._lock = threading.Lock()
        self._callbacks: List[Callable] = []

        # 通知去重（同类型通知最小间隔）
        self._last_notification_time: Dict[str, int] = {}
        self._min_interval = min_interval  # 同类型通知最小间隔（秒）

    def configure(self, desktop_enabled: bool = None,
                  webhook_enabled: bool = None,
                  webhook_url: str = None,
                  min_interval: int = None):
        """配置通知设置"""
        if desktop_enabled is not None:
            self.desktop_enabled = desktop_enabled
        if webhook_enabled is not None:
            self.webhook_enabled = webhook_enabled
        if webhook_url is not None:
            self.webhook_url = webhook_url
        if min_interval is not None:
            self._min_interval = min_interval

    def notify(self, notification: Notification) -> bool:
        """
        发送通知
        :return: 是否成功发送
        """
        # 去重检查
        now = int(time.time())
        last_time = self._last_notification_time.get(notification.type.value, 0)
        if now - last_time < self._min_interval:
            return False

        self._last_notification_time[notification.type.value] = now

        # 保存历史
        with self._lock:
            self._history.append(notification)
            if len(self._history) > self._max_history:
                self._history = self._history[-self._max_history:]

        # 桌面通知
        if self.desktop_enabled:
            self._send_desktop(notification)

        # Webhook 通知
        if self.webhook_enabled and self.webhook_url:
            self._send_webhook(notification)

        # 回调
        for cb in self._callbacks:
            try:
                cb(notification)
            except Exception:
                pass

        if self.logger:
            self.logger.info(f"通知: [{notification.type.value}] {notification.title}")

        return True

    def notify_low_balance(self, provider: str, balance: float,
                           threshold: float, currency: str = "USD"):
        """余额不足通知"""
        return self.notify(Notification(
            type=NotificationType.LOW_BALANCE,
            title=f"⚠️ {provider} 余额不足",
            message=f"{provider} 剩余额度: {currency} {balance:.2f}，低于阈值 {currency} {threshold:.2f}",
            priority=NotificationPriority.HIGH,
            data={"provider": provider, "balance": balance, "threshold": threshold},
        ))

    def notify_api_error(self, provider: str, error: str,
                         model: str = ""):
        """API 异常通知"""
        return self.notify(Notification(
            type=NotificationType.API_ERROR,
            title=f"{provider} API 异常",
            message=f"模型: {model}\n错误: {error}" if model else f"错误: {error}",
            priority=NotificationPriority.HIGH,
            data={"provider": provider, "error": error, "model": model},
        ))

    def notify_budget_exceeded(self, daily_used: float, daily_limit: float,
                               monthly_used: float, monthly_limit: float,
                               currency: str = "USD"):
        """预算超限通知"""
        return self.notify(Notification(
            type=NotificationType.BUDGET_EXCEEDED,
            title="🚨 预算已超限",
            message=(f"今日: {currency} {daily_used:.2f} / {daily_limit:.2f}\n"
                    f"本月: {currency} {monthly_used:.2f} / {monthly_limit:.2f}\n"
                    f"已自动切换至低成本模型"),
            priority=NotificationPriority.CRITICAL,
            data={
                "daily_used": daily_used,
                "daily_limit": daily_limit,
                "monthly_used": monthly_used,
                "monthly_limit": monthly_limit,
            },
        ))

    def notify_budget_warning(self, daily_percent: float, monthly_percent: float,
                              currency: str = "USD"):
        """预算警告通知"""
        return self.notify(Notification(
            type=NotificationType.BUDGET_WARNING,
            title="⚡ 预算即将用完",
            message=(f"今日已使用: {daily_percent:.0f}%\n"
                    f"本月已使用: {monthly_percent:.0f}%\n"
                    f"请注意控制使用量"),
            priority=NotificationPriority.MEDIUM,
            data={"daily_percent": daily_percent, "monthly_percent": monthly_percent},
        ))

    def notify_key_rotated(self, provider: str, from_key: str, to_key: str):
        """Key 轮转通知"""
        return self.notify(Notification(
            type=NotificationType.KEY_ROTATED,
            title=f"{provider} Key 已切换",
            message=f"从 {from_key} 切换到 {to_key}",
            priority=NotificationPriority.LOW,
            data={"provider": provider, "from": from_key, "to": to_key},
        ))

    def notify_failover(self, from_model: str, to_model: str, reason: str = ""):
        """故障转移通知"""
        return self.notify(Notification(
            type=NotificationType.FAILOVER_TRIGGERED,
            title="🔀 故障转移",
            message=f"从 {from_model} 切换到 {to_model}" + (f"\n原因: {reason}" if reason else ""),
            priority=NotificationPriority.MEDIUM,
            data={"from_model": from_model, "to_model": to_model, "reason": reason},
        ))

    def _send_desktop(self, notification: Notification):
        """发送桌面通知"""
        try:
            # Windows 桌面通知
            try:
                from win10toast import ToastNotifier
                toaster = ToastNotifier()
                toaster.show_toast(
                    notification.title,
                    notification.message,
                    duration=5,
                    threaded=True,
                )
                return
            except ImportError:
                pass

            # 备选：使用 plyer
            try:
                from plyer import notification as plyer_notification
                plyer_notification.notify(
                    title=notification.title,
                    message=notification.message,
                    timeout=5,
                )
                return
            except ImportError:
                pass

            # 备选：使用 tkinter 消息框（非阻塞）
            try:
                import tkinter as tk
                from tkinter import messagebox
                root = tk.Tk()
                root.withdraw()
                root.after(100, lambda: messagebox.showinfo(
                    notification.title, notification.message))
                root.after(5000, root.destroy)
                root.mainloop()
            except Exception:
                pass

        except Exception as e:
            if self.logger:
                self.logger.error(f"桌面通知失败: {e}")

    def _send_webhook(self, notification: Notification):
        """发送 Webhook 通知"""
        try:
            payload = {
                "text": f"**{notification.title}**\n{notification.message}",
                "notification": notification.to_dict(),
            }
            resp = requests.post(
                self.webhook_url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=10,
            )
            if resp.status_code not in (200, 201, 204):
                if self.logger:
                    self.logger.warning(f"Webhook 返回: HTTP {resp.status_code}")
        except Exception as e:
            if self.logger:
                self.logger.error(f"Webhook 发送失败: {e}")

    def get_history(self, limit: int = 50) -> List[Notification]:
        """获取通知历史"""
        with self._lock:
            return self._history[-limit:]

    def clear_history(self):
        """清空通知历史"""
        with self._lock:
            self._history.clear()

    def on_notification(self, callback: Callable):
        """注册通知回调"""
        self._callbacks.append(callback)
