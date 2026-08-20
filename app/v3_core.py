"""
V3 个人版 OpenRouter / LiteLLM 核心模块
=====================================
架构核心：统一的服务管理器，整合所有 V1/V2/V3 功能

新增功能：
- Web 控制后台 (FastAPI)
- 用户权限系统
- 请求缓存
- Prompt 管理
- AI 智能调度
- MCP 支持
- 数据分析
- 插件系统
- Docker 部署
"""
import os
import json
import time
import hashlib
import secrets
import threading
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from datetime import datetime, date, timedelta
from enum import Enum


# ==================== 用户权限系统 ====================

class UserRole(Enum):
    """用户角色"""
    ADMIN = "admin"
    USER = "user"
    VIEWER = "viewer"


@dataclass
class User:
    """用户信息"""
    id: str
    username: str
    password_hash: str
    role: UserRole
    created_at: int = 0
    last_login: int = 0
    is_active: bool = True
    api_key: str = ""  # 个人 API Key
    rate_limit: int = 100  # 每分钟请求限制

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "username": self.username,
            "role": self.role.value,
            "created_at": self.created_at,
            "last_login": self.last_login,
            "is_active": self.is_active,
            "rate_limit": self.rate_limit,
        }


class AuthManager:
    """认证管理器"""

    def __init__(self, data_dir: str, logger=None):
        self.data_dir = data_dir
        self.logger = logger
        self._users: Dict[str, User] = {}  # username -> User
        self._sessions: Dict[str, Dict] = {}  # token -> {username, expires}
        self._lock = threading.RLock()
        self._secret = secrets.token_hex(32)
        self._users_file = os.path.join(data_dir, "v3_users.json")
        self.bootstrap_admin_password = ""
        self._load_users()

    def _load_users(self):
        """加载用户数据"""
        if os.path.exists(self._users_file):
            try:
                with open(self._users_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for username, udata in data.get("users", {}).items():
                    self._users[username] = User(
                        id=udata.get("id", ""),
                        username=username,
                        password_hash=udata.get("password_hash", ""),
                        role=UserRole(udata.get("role", "viewer")),
                        created_at=udata.get("created_at", 0),
                        last_login=udata.get("last_login", 0),
                        is_active=udata.get("is_active", True),
                        api_key=udata.get("api_key", ""),
                        rate_limit=udata.get("rate_limit", 100),
                    )
            except Exception:
                pass

        # 确保至少有一个管理员
        if not any(u.role == UserRole.ADMIN for u in self._users.values()):
            # 不使用公开项目中人人都知道的固定默认密码。
            self.bootstrap_admin_password = secrets.token_urlsafe(18)
            self.create_user("admin", self.bootstrap_admin_password, UserRole.ADMIN)
            bootstrap_file = os.path.join(self.data_dir, "v3_bootstrap_admin.txt")
            with open(bootstrap_file, "w", encoding="utf-8") as f:
                f.write("username=admin\n")
                f.write(f"password={self.bootstrap_admin_password}\n")
                f.write("首次登录并修改密码后请删除本文件。\n")

    def _save_users(self):
        """保存用户数据"""
        data = {
            "users": {
                username: {
                    "id": user.id,
                    "password_hash": user.password_hash,
                    "role": user.role.value,
                    "created_at": user.created_at,
                    "last_login": user.last_login,
                    "is_active": user.is_active,
                    "api_key": user.api_key,
                    "rate_limit": user.rate_limit,
                }
                for username, user in self._users.items()
            }
        }
        os.makedirs(self.data_dir, exist_ok=True)
        with open(self._users_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    @staticmethod
    def _hash_password(password: str, salt: str = "") -> str:
        """密码哈希"""
        if not salt:
            salt = secrets.token_hex(16)
        hash_val = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100000)
        return f"{salt}${hash_val.hex()}"

    def _verify_password(self, password: str, password_hash: str) -> bool:
        """验证密码"""
        try:
            salt, _ = password_hash.split("$", 1)
            return self._hash_password(password, salt) == password_hash
        except ValueError:
            return False

    def create_user(self, username: str, password: str,
                    role: UserRole = UserRole.USER) -> tuple:
        """创建用户"""
        with self._lock:
            if username in self._users:
                return False, "用户名已存在"

            user = User(
                id=secrets.token_hex(8),
                username=username,
                password_hash=self._hash_password(password),
                role=role,
                created_at=int(time.time()),
                api_key=secrets.token_hex(32),
            )
            self._users[username] = user
            self._save_users()
            return True, "用户创建成功"

    def authenticate(self, username: str, password: str) -> Optional[str]:
        """
        认证用户，返回 JWT token
        """
        with self._lock:
            user = self._users.get(username)
            if not user or not user.is_active:
                return None
            if not self._verify_password(password, user.password_hash):
                return None

            # 生成 token
            token = secrets.token_hex(32)
            user.last_login = int(time.time())
            self._sessions[token] = {
                "username": username,
                "expires": int(time.time()) + 86400,  # 24 小时
            }
            self._save_users()
            return token

    def verify_token(self, token: str) -> Optional[User]:
        """验证 token"""
        with self._lock:
            session = self._sessions.get(token)
            if not session:
                return None
            if int(time.time()) > session["expires"]:
                del self._sessions[token]
                return None
            return self._users.get(session["username"])

    def logout(self, token: str):
        """登出"""
        with self._lock:
            self._sessions.pop(token, None)

    def get_user(self, username: str) -> Optional[User]:
        """获取用户信息"""
        return self._users.get(username)

    def get_all_users(self) -> List[User]:
        """获取所有用户"""
        return list(self._users.values())

    def delete_user(self, username: str) -> bool:
        """删除用户"""
        with self._lock:
            if username in self._users:
                del self._users[username]
                self._save_users()
                return True
            return False

    def has_permission(self, user: User, permission: str) -> bool:
        """检查权限"""
        permissions = {
            UserRole.ADMIN: ["view_stats", "manage_keys", "call_models", "manage_users",
                           "manage_prompts", "view_logs", "manage_config", "manage_plugins"],
            UserRole.USER: ["view_stats", "call_models", "view_logs"],
            UserRole.VIEWER: ["view_stats"],
        }
        return permission in permissions.get(user.role, [])


# ==================== 请求缓存 ====================

class RequestCache:
    """请求缓存 - 相同请求优先读缓存"""

    def __init__(self, max_size: int = 1000, default_ttl: int = 300, logger=None):
        self._cache: Dict[str, Dict] = {}  # key -> {response, expires, hits}
        self._max_size = max_size
        self._default_ttl = default_ttl
        self._lock = threading.RLock()
        self.logger = logger
        self._stats = {"hits": 0, "misses": 0}

    def _make_key(self, model: str, messages: List[Dict], **kwargs) -> str:
        """生成缓存 key"""
        key_data = json.dumps({
            "model": model,
            "messages": messages,
            "temperature": kwargs.get("temperature", 0.7),
            "max_tokens": kwargs.get("max_tokens", 4096),
        }, sort_keys=True)
        return hashlib.sha256(key_data.encode()).hexdigest()

    def get(self, model: str, messages: List[Dict], **kwargs) -> Optional[Dict]:
        """获取缓存"""
        with self._lock:
            key = self._make_key(model, messages, **kwargs)
            entry = self._cache.get(key)
            if entry and entry["expires"] > int(time.time()):
                self._stats["hits"] += 1
                entry["hits"] += 1
                return entry["response"]
            elif entry:
                del self._cache[key]
            self._stats["misses"] += 1
            return None

    def set(self, model: str, messages: List[Dict], response: Dict,
            ttl: int = None, **kwargs):
        """设置缓存"""
        with self._lock:
            # LRU 淘汰
            if len(self._cache) >= self._max_size:
                # 移除最旧的条目
                oldest_key = min(self._cache, key=lambda k: self._cache[k].get("created", 0))
                del self._cache[oldest_key]

            key = self._make_key(model, messages, **kwargs)
            self._cache[key] = {
                "response": response,
                "expires": int(time.time()) + (ttl or self._default_ttl),
                "created": int(time.time()),
                "hits": 0,
            }

    def clear(self):
        """清空缓存"""
        with self._lock:
            self._cache.clear()
            self._stats = {"hits": 0, "misses": 0}

    def get_stats(self) -> Dict:
        """获取缓存统计"""
        with self._lock:
            total = self._stats["hits"] + self._stats["misses"]
            return {
                "hits": self._stats["hits"],
                "misses": self._stats["misses"],
                "hit_rate": round(self._stats["hits"] / total * 100, 1) if total > 0 else 0,
                "size": len(self._cache),
                "max_size": self._max_size,
            }

    def cleanup_expired(self):
        """清理过期缓存"""
        with self._lock:
            now = int(time.time())
            expired = [k for k, v in self._cache.items() if v["expires"] <= now]
            for k in expired:
                del self._cache[k]


# ==================== Prompt 管理 ====================

@dataclass
class PromptTemplate:
    """Prompt 模板"""
    id: str
    name: str
    description: str
    content: str
    category: str
    variables: List[str]  # 变量名列表，如 ["language", "task"]
    tags: List[str]
    created_at: int = 0
    updated_at: int = 0
    use_count: int = 0

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.content,
            "content": self.content,
            "category": self.category,
            "variables": self.variables,
            "tags": self.tags,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "use_count": self.use_count,
        }

    def render(self, **kwargs) -> str:
        """渲染模板，替换变量"""
        result = self.content
        for key, value in kwargs.items():
            placeholder = "{{" + key + "}}"
            result = result.replace(placeholder, str(value))
            brace_placeholder = "{" + key + "}"
            result = result.replace(brace_placeholder, str(value))
        return result


class PromptManager:
    """Prompt 管理器"""

    def __init__(self, data_dir: str, logger=None):
        self.data_dir = data_dir
        self.logger = logger
        self._prompts: Dict[str, PromptTemplate] = {}
        self._lock = threading.RLock()
        self._file = os.path.join(data_dir, "v3_prompts.json")
        self._load()

    def _load(self):
        """加载 Prompt"""
        if os.path.exists(self._file):
            try:
                with open(self._file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for pid, pdata in data.items():
                    self._prompts[pid] = PromptTemplate(**pdata)
            except Exception:
                pass

        # 初始化默认 Prompt
        if not self._prompts:
            self._init_defaults()

    def _save(self):
        """保存 Prompt"""
        os.makedirs(self.data_dir, exist_ok=True)
        data = {pid: p.to_dict() for pid, p in self._prompts.items()}
        with open(self._file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _init_defaults(self):
        """初始化默认 Prompt 模板"""
        defaults = [
            PromptTemplate(
                id="code_expert",
                name="程序员助手",
                description="专业编程助手，帮助编写、调试、优化代码",
                content="你是一个专业的程序员助手。请帮助用户解决编程问题。\n"
                        "要求：\n"
                        "1. 代码简洁、高效、可读性强\n"
                        "2. 添加必要的注释\n"
                        "3. 遵循最佳实践\n"
                        "4. 主动指出潜在问题\n\n"
                        "用户问题：{{task}}",
                category="编程",
                variables=["task"],
                tags=["代码", "编程", "开发"],
                created_at=int(time.time()),
                updated_at=int(time.time()),
            ),
            PromptTemplate(
                id="blender_expert",
                name="Blender 专家",
                description="Blender 3D 建模、动画、渲染专家",
                content="你是一个 Blender 3D 专家。请帮助用户完成 Blender 相关任务。\n"
                        "擅长：建模、材质、动画、渲染、Python 脚本\n\n"
                        "用户问题：{{task}}",
                category="3D设计",
                variables=["task"],
                tags=["Blender", "3D", "建模"],
                created_at=int(time.time()),
                updated_at=int(time.time()),
            ),
            PromptTemplate(
                id="paper_assistant",
                name="论文助手",
                description="学术论文写作、润色、翻译助手",
                content="你是一个专业的学术论文助手。请帮助用户完成论文相关任务。\n"
                        "擅长：论文写作、润色、翻译、文献综述、格式规范\n"
                        "领域：{{domain}}\n\n"
                        "用户请求：{{task}}",
                category="学术",
                variables=["domain", "task"],
                tags=["论文", "学术", "写作"],
                created_at=int(time.time()),
                updated_at=int(time.time()),
            ),
            PromptTemplate(
                id="translator",
                name="翻译专家",
                description="多语言专业翻译",
                content="你是一个专业翻译。请将以下内容从 {{source_lang}} 翻译成 {{target_lang}}。\n"
                        "要求：准确、自然、符合目标语言习惯\n\n"
                        "原文：{{text}}",
                category="翻译",
                variables=["source_lang", "target_lang", "text"],
                tags=["翻译", "多语言"],
                created_at=int(time.time()),
                updated_at=int(time.time()),
            ),
        ]
        for p in defaults:
            self._prompts[p.id] = p
        self._save()

    def create(self, name: str, content: str, description: str = "",
               category: str = "通用", variables: List[str] = None,
               tags: List[str] = None) -> PromptTemplate:
        """创建 Prompt"""
        with self._lock:
            prompt = PromptTemplate(
                id=secrets.token_hex(8),
                name=name,
                description=description,
                content=content,
                category=category,
                variables=variables or [],
                tags=tags or [],
                created_at=int(time.time()),
                updated_at=int(time.time()),
            )
            self._prompts[prompt.id] = prompt
            self._save()
            return prompt

    def update(self, prompt_id: str, **kwargs) -> Optional[PromptTemplate]:
        """更新 Prompt"""
        with self._lock:
            prompt = self._prompts.get(prompt_id)
            if not prompt:
                return None
            for key, value in kwargs.items():
                if hasattr(prompt, key):
                    setattr(prompt, key, value)
            prompt.updated_at = int(time.time())
            self._save()
            return prompt

    def delete(self, prompt_id: str) -> bool:
        """删除 Prompt"""
        with self._lock:
            if prompt_id in self._prompts:
                del self._prompts[prompt_id]
                self._save()
                return True
            return False

    def get(self, prompt_id: str) -> Optional[PromptTemplate]:
        """获取 Prompt"""
        return self._prompts.get(prompt_id)

    def get_all(self) -> List[PromptTemplate]:
        """获取所有 Prompt"""
        return list(self._prompts.values())

    def get_by_category(self, category: str) -> List[PromptTemplate]:
        """按分类获取"""
        return [p for p in self._prompts.values() if p.category == category]

    def search(self, query: str) -> List[PromptTemplate]:
        """搜索 Prompt"""
        query = query.lower()
        results = []
        for p in self._prompts.values():
            if (query in p.name.lower() or query in p.description.lower() or
                    any(query in t.lower() for t in p.tags)):
                results.append(p)
        return results

    def use_prompt(self, prompt_id: str, **variables) -> Optional[str]:
        """使用 Prompt（渲染并计数）"""
        with self._lock:
            prompt = self._prompts.get(prompt_id)
            if not prompt:
                return None
            prompt.use_count += 1
            self._save()
            return prompt.render(**variables)

    def get_categories(self) -> List[str]:
        """获取所有分类"""
        return list(set(p.category for p in self._prompts.values()))


# ==================== 审计日志 ====================

class AuditLogger:
    """审计日志"""

    def __init__(self, data_dir: str, logger=None):
        self.data_dir = data_dir
        self.logger = logger
        self._logs: List[Dict] = []
        self._lock = threading.Lock()
        self._file = os.path.join(data_dir, "v3_audit.jsonl")
        self._load()

    def _load(self):
        """加载历史日志"""
        if os.path.exists(self._file):
            try:
                with open(self._file, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            self._logs.append(json.loads(line))
            except Exception:
                pass

    def log(self, action: str, user: str = "system", details: Dict = None,
            ip: str = "", status: str = "success"):
        """记录审计日志"""
        entry = {
            "timestamp": int(time.time()),
            "action": action,
            "user": user,
            "details": details or {},
            "ip": ip,
            "status": status,
        }
        with self._lock:
            self._logs.append(entry)
            # 写入文件
            try:
                os.makedirs(self.data_dir, exist_ok=True)
                with open(self._file, "a", encoding="utf-8") as f:
                    f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            except Exception:
                pass

    def get_logs(self, limit: int = 100, action: str = None,
                 user: str = None) -> List[Dict]:
        """获取日志"""
        with self._lock:
            logs = self._logs
            if action:
                logs = [l for l in logs if l["action"] == action]
            if user:
                logs = [l for l in logs if l["user"] == user]
            return logs[-limit:]

    def get_stats(self) -> Dict:
        """获取审计统计"""
        with self._lock:
            actions = {}
            for log in self._logs:
                action = log["action"]
                actions[action] = actions.get(action, 0) + 1
            return {
                "total_logs": len(self._logs),
                "actions": actions,
            }
