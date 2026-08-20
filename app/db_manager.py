"""
SQLite 数据库管理模块
管理模型、供应商、Token 统计、请求日志

所有数据存储在本地 SQLite 文件中，支持：
- 模型管理（启用/禁用、价格、上下文长度）
- Token 统计（按天/模型聚合）
- 请求日志（完整请求记录）
"""
import os
import sqlite3
import threading
import time
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Any, Tuple


class DatabaseManager:
    """SQLite 数据库管理器"""

    def __init__(self, data_dir: str):
        self.data_dir = data_dir
        os.makedirs(data_dir, exist_ok=True)
        self.db_path = os.path.join(data_dir, "gateway.db")
        self._local = threading.local()
        self._lock = threading.Lock()
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        """获取当前线程的数据库连接"""
        if not hasattr(self._local, "conn") or self._local.conn is None:
            conn = sqlite3.connect(self.db_path, timeout=30)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            self._local.conn = conn
        return self._local.conn

    def _init_db(self):
        """初始化数据库表"""
        conn = self._get_conn()
        cursor = conn.cursor()

        # 供应商表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS providers (
                id TEXT PRIMARY KEY,
                name TEXT UNIQUE NOT NULL,
                provider_type TEXT DEFAULT 'custom',
                base_url TEXT DEFAULT '',
                api_key TEXT DEFAULT '',
                auth_mode TEXT DEFAULT 'bearer',
                status TEXT DEFAULT 'active',
                created_at INTEGER DEFAULT 0,
                updated_at INTEGER DEFAULT 0
            )
        """)

        # 模型表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS models (
                id TEXT PRIMARY KEY,
                provider_id TEXT NOT NULL,
                provider_name TEXT DEFAULT '',
                model_name TEXT NOT NULL,
                display_name TEXT DEFAULT '',
                input_price REAL DEFAULT 0,
                output_price REAL DEFAULT 0,
                context_length INTEGER DEFAULT 128000,
                status TEXT DEFAULT 'enabled',
                created_at INTEGER DEFAULT 0,
                updated_at INTEGER DEFAULT 0,
                FOREIGN KEY (provider_id) REFERENCES providers(id) ON DELETE CASCADE
            )
        """)

        # 请求日志表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS request_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                request_time INTEGER DEFAULT 0,
                model TEXT DEFAULT '',
                provider TEXT DEFAULT '',
                input_tokens INTEGER DEFAULT 0,
                output_tokens INTEGER DEFAULT 0,
                total_tokens INTEGER DEFAULT 0,
                response_time_ms INTEGER DEFAULT 0,
                status TEXT DEFAULT 'success',
                error TEXT DEFAULT '',
                endpoint TEXT DEFAULT '/v1/chat/completions'
            )
        """)

        # Token 统计表（按天聚合）
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS token_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                stat_date TEXT NOT NULL,
                model TEXT DEFAULT '',
                total_requests INTEGER DEFAULT 0,
                success_requests INTEGER DEFAULT 0,
                failed_requests INTEGER DEFAULT 0,
                input_tokens INTEGER DEFAULT 0,
                output_tokens INTEGER DEFAULT 0,
                total_tokens INTEGER DEFAULT 0,
                avg_response_time_ms INTEGER DEFAULT 0,
                UNIQUE(stat_date, model)
            )
        """)

        # 创建索引
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_logs_time ON request_logs(request_time)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_logs_model ON request_logs(model)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_logs_status ON request_logs(status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_stats_date ON token_stats(stat_date)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_models_provider ON models(provider_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_models_status ON models(status)")

        conn.commit()

    # ==================== 供应商管理 ====================

    def add_provider(self, provider: Dict[str, Any]) -> Tuple[bool, str]:
        """添加供应商"""
        try:
            with self._lock:
                conn = self._get_conn()
                now = int(time.time())
                conn.execute("""
                    INSERT INTO providers (id, name, provider_type, base_url, api_key, auth_mode, status, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    provider.get("id", ""),
                    provider.get("name", ""),
                    provider.get("provider_type", "custom"),
                    provider.get("base_url", ""),
                    provider.get("api_key", ""),
                    provider.get("auth_mode", "bearer"),
                    provider.get("status", "active"),
                    now, now
                ))
                conn.commit()
            return True, "供应商添加成功"
        except sqlite3.IntegrityError:
            return False, "供应商名称已存在"
        except Exception as e:
            return False, f"添加失败: {str(e)[:100]}"

    def update_provider(self, provider_id: str, data: Dict[str, Any]) -> Tuple[bool, str]:
        """更新供应商"""
        try:
            with self._lock:
                conn = self._get_conn()
                now = int(time.time())
                fields = []
                values = []
                for key in ["name", "provider_type", "base_url", "api_key", "auth_mode", "status"]:
                    if key in data:
                        fields.append(f"{key}=?")
                        values.append(data[key])
                fields.append("updated_at=?")
                values.append(now)
                values.append(provider_id)

                conn.execute(f"UPDATE providers SET {', '.join(fields)} WHERE id=?", values)
                conn.commit()
            return True, "供应商更新成功"
        except Exception as e:
            return False, f"更新失败: {str(e)[:100]}"

    def delete_provider(self, provider_id: str) -> Tuple[bool, str]:
        """删除供应商"""
        try:
            with self._lock:
                conn = self._get_conn()
                conn.execute("DELETE FROM models WHERE provider_id=?", (provider_id,))
                conn.execute("DELETE FROM providers WHERE id=?", (provider_id,))
                conn.commit()
            return True, "供应商已删除"
        except Exception as e:
            return False, f"删除失败: {str(e)[:100]}"

    def get_provider(self, provider_id: str) -> Optional[Dict[str, Any]]:
        """获取单个供应商"""
        conn = self._get_conn()
        row = conn.execute("SELECT * FROM providers WHERE id=?", (provider_id,)).fetchone()
        return dict(row) if row else None

    def get_provider_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """按名称获取供应商"""
        conn = self._get_conn()
        row = conn.execute("SELECT * FROM providers WHERE name=?", (name,)).fetchone()
        return dict(row) if row else None

    def get_all_providers(self) -> List[Dict[str, Any]]:
        """获取所有供应商"""
        conn = self._get_conn()
        rows = conn.execute("SELECT * FROM providers ORDER BY created_at").fetchall()
        return [dict(r) for r in rows]

    def get_active_providers(self) -> List[Dict[str, Any]]:
        """获取活跃的供应商"""
        conn = self._get_conn()
        rows = conn.execute("SELECT * FROM providers WHERE status='active' ORDER BY name").fetchall()
        return [dict(r) for r in rows]

    # ==================== 模型管理 ====================

    def add_model(self, model: Dict[str, Any]) -> Tuple[bool, str]:
        """添加模型"""
        try:
            with self._lock:
                conn = self._get_conn()
                now = int(time.time())
                conn.execute("""
                    INSERT INTO models (id, provider_id, provider_name, model_name, display_name,
                                       input_price, output_price, context_length, status, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    model.get("id", ""),
                    model.get("provider_id", ""),
                    model.get("provider_name", ""),
                    model.get("model_name", ""),
                    model.get("display_name", ""),
                    model.get("input_price", 0),
                    model.get("output_price", 0),
                    model.get("context_length", 128000),
                    model.get("status", "enabled"),
                    now, now
                ))
                conn.commit()
            return True, "模型添加成功"
        except Exception as e:
            return False, f"添加失败: {str(e)[:100]}"

    def update_model(self, model_id: str, data: Dict[str, Any]) -> Tuple[bool, str]:
        """更新模型"""
        try:
            with self._lock:
                conn = self._get_conn()
                now = int(time.time())
                fields = []
                values = []
                for key in ["provider_id", "provider_name", "model_name", "display_name",
                           "input_price", "output_price", "context_length", "status"]:
                    if key in data:
                        fields.append(f"{key}=?")
                        values.append(data[key])
                fields.append("updated_at=?")
                values.append(now)
                values.append(model_id)

                conn.execute(f"UPDATE models SET {', '.join(fields)} WHERE id=?", values)
                conn.commit()
            return True, "模型更新成功"
        except Exception as e:
            return False, f"更新失败: {str(e)[:100]}"

    def delete_model(self, model_id: str) -> Tuple[bool, str]:
        """删除模型"""
        try:
            with self._lock:
                conn = self._get_conn()
                conn.execute("DELETE FROM models WHERE id=?", (model_id,))
                conn.commit()
            return True, "模型已删除"
        except Exception as e:
            return False, f"删除失败: {str(e)[:100]}"

    def get_model_by_name(self, model_name: str) -> Optional[Dict[str, Any]]:
        """按模型名称获取"""
        conn = self._get_conn()
        row = conn.execute(
            "SELECT * FROM models WHERE model_name=? AND status='enabled'", (model_name,)
        ).fetchone()
        return dict(row) if row else None

    def get_models_by_provider(self, provider_id: str) -> List[Dict[str, Any]]:
        """获取供应商的所有模型"""
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM models WHERE provider_id=? ORDER BY model_name", (provider_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    def get_all_models(self) -> List[Dict[str, Any]]:
        """获取所有模型"""
        conn = self._get_conn()
        rows = conn.execute("""
            SELECT m.*, p.base_url, p.api_key, p.auth_mode, p.provider_type
            FROM models m
            LEFT JOIN providers p ON m.provider_id = p.id
            ORDER BY m.provider_name, m.model_name
        """).fetchall()
        return [dict(r) for r in rows]

    def get_enabled_models(self) -> List[Dict[str, Any]]:
        """获取已启用的模型"""
        conn = self._get_conn()
        rows = conn.execute("""
            SELECT m.*, p.base_url, p.api_key, p.auth_mode, p.provider_type
            FROM models m
            LEFT JOIN providers p ON m.provider_id = p.id
            WHERE m.status = 'enabled' AND p.status = 'active'
            ORDER BY m.provider_name, m.model_name
        """).fetchall()
        return [dict(r) for r in rows]

    def toggle_model_status(self, model_id: str) -> Tuple[bool, str]:
        """切换模型启用/禁用状态"""
        try:
            with self._lock:
                conn = self._get_conn()
                row = conn.execute("SELECT status FROM models WHERE id=?", (model_id,)).fetchone()
                if not row:
                    return False, "模型不存在"
                new_status = "disabled" if row["status"] == "enabled" else "enabled"
                conn.execute("UPDATE models SET status=?, updated_at=? WHERE id=?",
                           (new_status, int(time.time()), model_id))
                conn.commit()
            return True, f"模型已{'启用' if new_status == 'enabled' else '禁用'}"
        except Exception as e:
            return False, f"操作失败: {str(e)[:100]}"

    # ==================== 请求日志 ====================

    def log_request(self, log: Dict[str, Any]):
        """记录请求日志"""
        try:
            with self._lock:
                conn = self._get_conn()
                now = int(time.time())
                conn.execute("""
                    INSERT INTO request_logs (request_time, model, provider, input_tokens,
                                            output_tokens, total_tokens, response_time_ms,
                                            status, error, endpoint)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    now,
                    log.get("model", ""),
                    log.get("provider", ""),
                    log.get("input_tokens", 0),
                    log.get("output_tokens", 0),
                    log.get("total_tokens", 0),
                    log.get("response_time_ms", 0),
                    log.get("status", "success"),
                    log.get("error", ""),
                    log.get("endpoint", "/v1/chat/completions"),
                ))

                # 更新统计
                stat_date = date.today().isoformat()
                conn.execute("""
                    INSERT INTO token_stats (stat_date, model, total_requests, success_requests,
                                          failed_requests, input_tokens, output_tokens, total_tokens,
                                          avg_response_time_ms)
                    VALUES (?, ?, 1, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(stat_date, model) DO UPDATE SET
                        total_requests = total_requests + 1,
                        success_requests = success_requests + ?,
                        failed_requests = failed_requests + ?,
                        input_tokens = input_tokens + ?,
                        output_tokens = output_tokens + ?,
                        total_tokens = total_tokens + ?,
                        avg_response_time_ms = (avg_response_time_ms * total_requests + ?) / (total_requests + 1)
                """, (
                    stat_date,
                    log.get("model", ""),
                    1 if log.get("status") == "success" else 0,
                    0 if log.get("status") == "success" else 1,
                    log.get("input_tokens", 0),
                    log.get("output_tokens", 0),
                    log.get("total_tokens", 0),
                    log.get("response_time_ms", 0),
                    # ON CONFLICT 部分
                    1 if log.get("status") == "success" else 0,
                    0 if log.get("status") == "success" else 1,
                    log.get("input_tokens", 0),
                    log.get("output_tokens", 0),
                    log.get("total_tokens", 0),
                    log.get("response_time_ms", 0),
                ))

                conn.commit()
        except Exception as e:
            # 日志写入失败不应影响主流程
            pass

    def get_recent_logs(self, limit: int = 100) -> List[Dict[str, Any]]:
        """获取最近的请求日志"""
        conn = self._get_conn()
        rows = conn.execute("""
            SELECT * FROM request_logs ORDER BY request_time DESC LIMIT ?
        """, (limit,)).fetchall()
        return [dict(r) for r in rows]

    def get_logs_by_date(self, target_date: str) -> List[Dict[str, Any]]:
        """获取指定日期的日志"""
        conn = self._get_conn()
        # target_date format: YYYY-MM-DD
        try:
            dt = datetime.strptime(target_date, "%Y-%m-%d")
            start = int(dt.replace(hour=0, minute=0, second=0).timestamp())
            end = start + 86400
        except ValueError:
            return []

        rows = conn.execute("""
            SELECT * FROM request_logs WHERE request_time >= ? AND request_time < ?
            ORDER BY request_time DESC
        """, (start, end)).fetchall()
        return [dict(r) for r in rows]

    def get_logs_by_model(self, model: str, limit: int = 50) -> List[Dict[str, Any]]:
        """获取指定模型的日志"""
        conn = self._get_conn()
        rows = conn.execute("""
            SELECT * FROM request_logs WHERE model=? ORDER BY request_time DESC LIMIT ?
        """, (model, limit)).fetchall()
        return [dict(r) for r in rows]

    def clear_old_logs(self, days: int = 30):
        """清理旧日志"""
        cutoff = int(time.time()) - (days * 86400)
        with self._lock:
            conn = self._get_conn()
            conn.execute("DELETE FROM request_logs WHERE request_time < ?", (cutoff,))
            conn.commit()

    # ==================== Token 统计 ====================

    def get_today_stats(self) -> Dict[str, Any]:
        """获取今日统计"""
        today = date.today().isoformat()
        conn = self._get_conn()
        row = conn.execute("""
            SELECT
                COALESCE(SUM(total_requests), 0) as total_requests,
                COALESCE(SUM(success_requests), 0) as success_requests,
                COALESCE(SUM(failed_requests), 0) as failed_requests,
                COALESCE(SUM(input_tokens), 0) as input_tokens,
                COALESCE(SUM(output_tokens), 0) as output_tokens,
                COALESCE(SUM(total_tokens), 0) as total_tokens,
                COALESCE(AVG(avg_response_time_ms), 0) as avg_response_time
            FROM token_stats WHERE stat_date = ?
        """, (today,)).fetchone()
        return dict(row) if row else {}

    def get_stats_by_date(self, target_date: str) -> Dict[str, Any]:
        """获取指定日期统计"""
        conn = self._get_conn()
        row = conn.execute("""
            SELECT
                COALESCE(SUM(total_requests), 0) as total_requests,
                COALESCE(SUM(success_requests), 0) as success_requests,
                COALESCE(SUM(failed_requests), 0) as failed_requests,
                COALESCE(SUM(input_tokens), 0) as input_tokens,
                COALESCE(SUM(output_tokens), 0) as output_tokens,
                COALESCE(SUM(total_tokens), 0) as total_tokens,
                COALESCE(AVG(avg_response_time_ms), 0) as avg_response_time
            FROM token_stats WHERE stat_date = ?
        """, (target_date,)).fetchone()
        return dict(row) if row else {}

    def get_stats_range(self, start_date: str, end_date: str) -> List[Dict[str, Any]]:
        """获取日期范围的统计"""
        conn = self._get_conn()
        rows = conn.execute("""
            SELECT * FROM token_stats WHERE stat_date >= ? AND stat_date <= ?
            ORDER BY stat_date DESC
        """, (start_date, end_date)).fetchall()
        return [dict(r) for r in rows]

    def get_model_stats(self) -> List[Dict[str, Any]]:
        """获取各模型使用统计"""
        conn = self._get_conn()
        rows = conn.execute("""
            SELECT model,
                   SUM(total_requests) as total_requests,
                   SUM(total_tokens) as total_tokens,
                   SUM(success_requests) as success_requests,
                   SUM(failed_requests) as failed_requests
            FROM token_stats GROUP BY model ORDER BY total_requests DESC
        """).fetchall()
        return [dict(r) for r in rows]

    def get_dashboard_stats(self) -> Dict[str, Any]:
        """获取仪表板统计数据"""
        today = date.today().isoformat()
        conn = self._get_conn()

        # 今日统计
        today_stats = self.get_today_stats()

        # 总模型数
        model_count = conn.execute(
            "SELECT COUNT(*) FROM models WHERE status='enabled'"
        ).fetchone()[0]

        # 总供应商数
        provider_count = conn.execute(
            "SELECT COUNT(*) FROM providers WHERE status='active'"
        ).fetchone()[0]

        # 总请求数
        total_requests = conn.execute(
            "SELECT COUNT(*) FROM request_logs"
        ).fetchone()[0]

        # 最近 7 天统计
        week_ago = (date.today() - timedelta(days=7)).isoformat()
        week_stats = conn.execute("""
            SELECT COALESCE(SUM(total_requests), 0) as requests,
                   COALESCE(SUM(total_tokens), 0) as tokens
            FROM token_stats WHERE stat_date >= ?
        """, (week_ago,)).fetchone()

        return {
            "today_requests": today_stats.get("total_requests", 0),
            "today_tokens": today_stats.get("total_tokens", 0),
            "today_success": today_stats.get("success_requests", 0),
            "today_failed": today_stats.get("failed_requests", 0),
            "model_count": model_count,
            "provider_count": provider_count,
            "total_requests": total_requests,
            "week_requests": week_stats["requests"] if week_stats else 0,
            "week_tokens": week_stats["tokens"] if week_stats else 0,
            "avg_response_time": int(today_stats.get("avg_response_time", 0)),
        }

    def close(self):
        """关闭数据库连接"""
        if hasattr(self._local, "conn") and self._local.conn:
            self._local.conn.close()
            self._local.conn = None
