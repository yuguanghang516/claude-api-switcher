"""
V3 数据分析模块
===============
用量报告、趋势分析、成本统计

功能：
- 使用量统计（按天/周/月/模型/用户）
- 成本分析（趋势、分布、预测）
- 性能分析（响应时间、成功率、延迟分布）
- 导出报告（JSON/CSV）
"""
import os
import json
import time
import sqlite3
import threading
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime, date, timedelta
from collections import defaultdict


@dataclass
class UsageRecord:
    """使用记录"""
    timestamp: int
    model: str
    provider: str
    user: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_usd: float
    cost_cny: float
    response_time_ms: int
    status: str  # success / error
    error_type: str = ""

    def to_dict(self) -> Dict:
        return {
            "timestamp": self.timestamp,
            "model": self.model,
            "provider": self.provider,
            "user": self.user,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "cost_usd": self.cost_usd,
            "cost_cny": self.cost_cny,
            "response_time_ms": self.response_time_ms,
            "status": self.status,
            "error_type": self.error_type,
        }


class AnalyticsEngine:
    """分析引擎"""

    def __init__(self, data_dir: str, logger=None):
        self.data_dir = data_dir
        self.logger = logger
        self._records: List[UsageRecord] = []
        self._lock = threading.RLock()
        self._db_path = os.path.join(data_dir, "v3_analytics.db")
        self._init_db()
        self._load_records()

    def _init_db(self):
        """初始化数据库"""
        conn = sqlite3.connect(self._db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS usage_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp INTEGER,
                model TEXT,
                provider TEXT,
                user TEXT,
                prompt_tokens INTEGER,
                completion_tokens INTEGER,
                total_tokens INTEGER,
                cost_usd REAL,
                cost_cny REAL,
                response_time_ms INTEGER,
                status TEXT,
                error_type TEXT
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_timestamp ON usage_records(timestamp)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_model ON usage_records(model)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_user ON usage_records(user)")
        conn.commit()
        conn.close()

    def _load_records(self):
        """加载近期记录"""
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            "SELECT * FROM usage_records ORDER BY timestamp DESC LIMIT 10000"
        )
        for row in cursor:
            self._records.append(UsageRecord(
                timestamp=row["timestamp"],
                model=row["model"],
                provider=row["provider"],
                user=row["user"],
                prompt_tokens=row["prompt_tokens"],
                completion_tokens=row["completion_tokens"],
                total_tokens=row["total_tokens"],
                cost_usd=row["cost_usd"],
                cost_cny=row["cost_cny"],
                response_time_ms=row["response_time_ms"],
                status=row["status"],
                error_type=row["error_type"] or "",
            ))
        conn.close()

    def record(self, record: UsageRecord):
        """记录使用"""
        with self._lock:
            self._records.append(record)
            # 写入数据库
            conn = sqlite3.connect(self._db_path)
            conn.execute("""
                INSERT INTO usage_records
                (timestamp, model, provider, user, prompt_tokens, completion_tokens,
                 total_tokens, cost_usd, cost_cny, response_time_ms, status, error_type)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                record.timestamp, record.model, record.provider, record.user,
                record.prompt_tokens, record.completion_tokens, record.total_tokens,
                record.cost_usd, record.cost_cny, record.response_time_ms,
                record.status, record.error_type,
            ))
            conn.commit()
            conn.close()

    def get_overview(self, days: int = 30) -> Dict:
        """获取概览统计"""
        with self._lock:
            cutoff = int(time.time()) - days * 86400
            records = [r for r in self._records if r.timestamp >= cutoff]

            if not records:
                return {
                    "total_requests": 0,
                    "total_tokens": 0,
                    "total_cost_usd": 0,
                    "total_cost_cny": 0,
                    "avg_response_time_ms": 0,
                    "success_rate": 100,
                    "days": days,
                }

            success_count = sum(1 for r in records if r.status == "success")
            return {
                "total_requests": len(records),
                "total_tokens": sum(r.total_tokens for r in records),
                "total_cost_usd": round(sum(r.cost_usd for r in records), 4),
                "total_cost_cny": round(sum(r.cost_cny for r in records), 2),
                "avg_response_time_ms": round(
                    sum(r.response_time_ms for r in records) / len(records)
                ),
                "success_rate": round(success_count / len(records) * 100, 1),
                "days": days,
            }

    def get_daily_usage(self, days: int = 30) -> List[Dict]:
        """获取每日使用量"""
        with self._lock:
            cutoff = int(time.time()) - days * 86400
            records = [r for r in self._records if r.timestamp >= cutoff]

            daily = defaultdict(lambda: {
                "requests": 0, "tokens": 0, "cost_usd": 0.0, "cost_cny": 0.0
            })
            for r in records:
                day = datetime.fromtimestamp(r.timestamp).strftime("%Y-%m-%d")
                daily[day]["requests"] += 1
                daily[day]["tokens"] += r.total_tokens
                daily[day]["cost_usd"] += r.cost_usd
                daily[day]["cost_cny"] += r.cost_cny

            return [
                {"date": d, **stats}
                for d, stats in sorted(daily.items())
            ]

    def get_model_distribution(self, days: int = 30) -> List[Dict]:
        """获取模型使用分布"""
        with self._lock:
            cutoff = int(time.time()) - days * 86400
            records = [r for r in self._records if r.timestamp >= cutoff]

            models = defaultdict(lambda: {
                "requests": 0, "tokens": 0, "cost_usd": 0.0, "avg_time_ms": 0
            })
            for r in records:
                models[r.model]["requests"] += 1
                models[r.model]["tokens"] += r.total_tokens
                models[r.model]["cost_usd"] += r.cost_usd
                models[r.model]["avg_time_ms"] += r.response_time_ms

            result = []
            for model, stats in models.items():
                result.append({
                    "model": model,
                    "requests": stats["requests"],
                    "tokens": stats["tokens"],
                    "cost_usd": round(stats["cost_usd"], 4),
                    "avg_time_ms": round(stats["avg_time_ms"] / stats["requests"]),
                })
            return sorted(result, key=lambda x: x["requests"], reverse=True)

    def get_user_ranking(self, days: int = 30, limit: int = 20) -> List[Dict]:
        """获取用户用量排行"""
        with self._lock:
            cutoff = int(time.time()) - days * 86400
            records = [r for r in self._records if r.timestamp >= cutoff]

            users = defaultdict(lambda: {
                "requests": 0, "tokens": 0, "cost_usd": 0.0
            })
            for r in records:
                users[r.user]["requests"] += 1
                users[r.user]["tokens"] += r.total_tokens
                users[r.user]["cost_usd"] += r.cost_usd

            result = [
                {"user": u, **stats}
                for u, stats in users.items()
            ]
            return sorted(result, key=lambda x: x["tokens"], reverse=True)[:limit]

    def get_hourly_distribution(self, days: int = 7) -> List[Dict]:
        """获取小时分布（24小时）"""
        with self._lock:
            cutoff = int(time.time()) - days * 86400
            records = [r for r in self._records if r.timestamp >= cutoff]

            hours = defaultdict(int)
            for r in records:
                hour = datetime.fromtimestamp(r.timestamp).hour
                hours[hour] += 1

            return [
                {"hour": h, "requests": hours.get(h, 0)}
                for h in range(24)
            ]

    def get_cost_trend(self, days: int = 30) -> List[Dict]:
        """获取成本趋势"""
        daily = self.get_daily_usage(days)
        return [
            {"date": d["date"], "cost_usd": round(d["cost_usd"], 4), "cost_cny": round(d["cost_cny"], 2)}
            for d in daily
        ]

    def get_performance_stats(self, days: int = 7) -> Dict:
        """获取性能统计"""
        with self._lock:
            cutoff = int(time.time()) - days * 86400
            records = [r for r in self._records if r.timestamp >= cutoff and r.status == "success"]

            if not records:
                return {"avg_latency": 0, "p50": 0, "p90": 0, "p99": 0, "error_rate": 0}

            times = sorted(r.response_time_ms for r in records)
            errors = sum(1 for r in self._records if r.timestamp >= cutoff and r.status == "error")
            total = len(records) + errors

            return {
                "avg_latency": round(sum(times) / len(times)),
                "p50": times[len(times) // 2],
                "p90": times[int(len(times) * 0.9)],
                "p99": times[int(len(times) * 0.99)],
                "error_rate": round(errors / total * 100, 1) if total > 0 else 0,
            }

    def get_provider_stats(self, days: int = 30) -> List[Dict]:
        """获取供应商统计"""
        with self._lock:
            cutoff = int(time.time()) - days * 86400
            records = [r for r in self._records if r.timestamp >= cutoff]

            providers = defaultdict(lambda: {
                "requests": 0, "tokens": 0, "cost_usd": 0.0,
                "success": 0, "error": 0, "total_time_ms": 0
            })
            for r in records:
                p = providers[r.provider]
                p["requests"] += 1
                p["tokens"] += r.total_tokens
                p["cost_usd"] += r.cost_usd
                p["total_time_ms"] += r.response_time_ms
                if r.status == "success":
                    p["success"] += 1
                else:
                    p["error"] += 1

            result = []
            for provider, stats in providers.items():
                result.append({
                    "provider": provider,
                    "requests": stats["requests"],
                    "tokens": stats["tokens"],
                    "cost_usd": round(stats["cost_usd"], 4),
                    "success_rate": round(stats["success"] / stats["requests"] * 100, 1),
                    "avg_time_ms": round(stats["total_time_ms"] / stats["requests"]),
                })
            return sorted(result, key=lambda x: x["requests"], reverse=True)

    def export_csv(self, output_path: str, days: int = 30) -> str:
        """导出 CSV 报告"""
        import csv
        with self._lock:
            cutoff = int(time.time()) - days * 86400
            records = [r for r in self._records if r.timestamp >= cutoff]

            with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "时间", "模型", "供应商", "用户", "提示Token",
                    "完成Token", "总Token", "费用(USD)", "费用(CNY)",
                    "响应时间(ms)", "状态"
                ])
                for r in records:
                    writer.writerow([
                        datetime.fromtimestamp(r.timestamp).strftime("%Y-%m-%d %H:%M:%S"),
                        r.model, r.provider, r.user, r.prompt_tokens,
                        r.completion_tokens, r.total_tokens,
                        r.cost_usd, r.cost_cny, r.response_time_ms, r.status,
                    ])
        return output_path

    def export_json(self, output_path: str, days: int = 30) -> str:
        """导出 JSON 报告"""
        with self._lock:
            cutoff = int(time.time()) - days * 86400
            records = [r for r in self._records if r.timestamp >= cutoff]

            data = {
                "generated_at": datetime.now().isoformat(),
                "days": days,
                "total_records": len(records),
                "overview": self.get_overview(days),
                "records": [r.to_dict() for r in records],
            }
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        return output_path

    def get_stats(self) -> Dict:
        """获取统计摘要"""
        with self._lock:
            return {
                "total_records": len(self._records),
                "db_size_mb": round(
                    os.path.getsize(self._db_path) / 1024 / 1024, 2
                ) if os.path.exists(self._db_path) else 0,
                "first_record": datetime.fromtimestamp(
                    self._records[-1].timestamp
                ).isoformat() if self._records else None,
                "last_record": datetime.fromtimestamp(
                    self._records[0].timestamp
                ).isoformat() if self._records else None,
            }
