"""
V3 Web 控制面板后端
===================
基于 FastAPI 的 Web 管理界面

功能：
- RESTful API
- 实时统计仪表板
- 模型/密钥/Prompt 管理
- 用户管理
- 数据分析图表
"""
import os
import json
import time
from typing import Dict, List, Optional, Any
from datetime import datetime


def create_web_app(data_dir: str, config_manager=None, auth_manager=None,
                   prompt_manager=None, analytics=None, scheduler=None,
                   mcp_server=None, plugin_manager=None, cache=None,
                   logger=None):
    """
    创建 FastAPI Web 应用
    """
    try:
        from fastapi import FastAPI, HTTPException, Depends, Request
        from fastapi.middleware.cors import CORSMiddleware
        from fastapi.responses import HTMLResponse, JSONResponse
        from fastapi.staticfiles import StaticFiles
        from pydantic import BaseModel
    except ImportError:
        # 如果没有 FastAPI，返回 None
        if logger:
            logger.warning("FastAPI 未安装，Web 控制面板不可用。请运行: pip install fastapi uvicorn")
        return None

    app = FastAPI(
        title="AI Router V3",
        description="个人版 OpenRouter / LiteLLM 控制面板",
        version="3.0.0",
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 依赖注入
    def get_auth():
        return auth_manager

    def get_current_user(request: Request, auth=Depends(get_auth)):
        token = request.headers.get("Authorization", "").replace("Bearer ", "")
        if not token:
            token = request.cookies.get("token", "")
        if not token:
            raise HTTPException(status_code=401, detail="未认证")
        user = auth.verify_token(token)
        if not user:
            raise HTTPException(status_code=401, detail="Token 无效或已过期")
        return user

    # ==================== 认证 API ====================

    class LoginRequest(BaseModel):
        username: str
        password: str

    @app.post("/api/auth/login")
    def login(req: LoginRequest):
        token = auth_manager.authenticate(req.username, req.password)
        if not token:
            raise HTTPException(status_code=401, detail="用户名或密码错误")
        return {"token": token, "username": req.username}

    @app.post("/api/auth/logout")
    def logout(request: Request):
        token = request.headers.get("Authorization", "").replace("Bearer ", "")
        auth_manager.logout(token)
        return {"message": "已登出"}

    @app.get("/api/auth/me")
    def get_me(user=Depends(get_current_user)):
        return user.to_dict()

    # ==================== 仪表板 API ====================

    @app.get("/api/dashboard")
    def dashboard(user=Depends(get_current_user)):
        """仪表板概览"""
        result = {
            "timestamp": int(time.time()),
            "user": user.to_dict(),
        }
        if analytics:
            result["overview"] = analytics.get_overview(7)
            result["daily_usage"] = analytics.get_daily_usage(7)
            result["model_distribution"] = analytics.get_model_distribution(7)
            result["performance"] = analytics.get_performance_stats(7)
        if scheduler:
            result["scheduler"] = scheduler.get_stats()
        if cache:
            result["cache"] = cache.get_stats()
        return result

    # ==================== 模型管理 API ====================

    @app.get("/api/models")
    def list_models(user=Depends(get_current_user)):
        """获取模型列表"""
        if scheduler:
            return {
                "models": scheduler.get_metrics(),
                "capabilities": scheduler._capability_scores,
            }
        return {"models": [], "capabilities": {}}

    @app.get("/api/models/recommendations")
    def model_recommendations(user=Depends(get_current_user)):
        """获取模型推荐"""
        if scheduler:
            return {"recommendations": scheduler.get_recommendations()}
        return {"recommendations": []}

    @app.post("/api/models/strategy")
    def set_strategy(strategy: str, user=Depends(get_current_user)):
        """设置调度策略"""
        if not auth_manager.has_permission(user, "manage_config"):
            raise HTTPException(status_code=403, detail="无权限")
        if scheduler:
            scheduler.set_strategy(strategy)
            return {"strategy": scheduler.get_strategy()}
        return {"strategy": "balanced"}

    # ==================== Prompt 管理 API ====================

    class PromptRequest(BaseModel):
        name: str
        description: str = ""
        content: str
        category: str = "通用"
        variables: List[str] = []
        tags: List[str] = []

    @app.get("/api/prompts")
    def list_prompts(category: str = None, user=Depends(get_current_user)):
        """获取 Prompt 列表"""
        if prompt_manager:
            if category:
                prompts = prompt_manager.get_by_category(category)
            else:
                prompts = prompt_manager.get_all()
            return {"prompts": [p.to_dict() for p in prompts]}
        return {"prompts": []}

    @app.get("/api/prompts/categories")
    def prompt_categories(user=Depends(get_current_user)):
        """获取 Prompt 分类"""
        if prompt_manager:
            return {"categories": prompt_manager.get_categories()}
        return {"categories": []}

    @app.post("/api/prompts")
    def create_prompt(req: PromptRequest, user=Depends(get_current_user)):
        """创建 Prompt"""
        if not auth_manager.has_permission(user, "manage_prompts"):
            raise HTTPException(status_code=403, detail="无权限")
        if prompt_manager:
            prompt = prompt_manager.create(**req.dict())
            return prompt.to_dict()
        raise HTTPException(status_code=500, detail="Prompt 管理器未初始化")

    @app.put("/api/prompts/{prompt_id}")
    def update_prompt(prompt_id: str, req: PromptRequest,
                      user=Depends(get_current_user)):
        """更新 Prompt"""
        if not auth_manager.has_permission(user, "manage_prompts"):
            raise HTTPException(status_code=403, detail="无权限")
        if prompt_manager:
            prompt = prompt_manager.update(prompt_id, **req.dict())
            if not prompt:
                raise HTTPException(status_code=404, detail="Prompt 不存在")
            return prompt.to_dict()
        raise HTTPException(status_code=500, detail="Prompt 管理器未初始化")

    @app.delete("/api/prompts/{prompt_id}")
    def delete_prompt(prompt_id: str, user=Depends(get_current_user)):
        """删除 Prompt"""
        if not auth_manager.has_permission(user, "manage_prompts"):
            raise HTTPException(status_code=403, detail="无权限")
        if prompt_manager:
            success = prompt_manager.delete(prompt_id)
            if not success:
                raise HTTPException(status_code=404, detail="Prompt 不存在")
            return {"message": "删除成功"}
        raise HTTPException(status_code=500, detail="Prompt 管理器未初始化")

    @app.post("/api/prompts/{prompt_id}/render")
    def render_prompt(prompt_id: str, variables: Dict[str, str] = {},
                      user=Depends(get_current_user)):
        """渲染 Prompt"""
        if prompt_manager:
            result = prompt_manager.use_prompt(prompt_id, **variables)
            if result is None:
                raise HTTPException(status_code=404, detail="Prompt 不存在")
            return {"rendered": result}
        raise HTTPException(status_code=500, detail="Prompt 管理器未初始化")

    # ==================== 用户管理 API ====================

    class UserRequest(BaseModel):
        username: str
        password: str
        role: str = "user"
        rate_limit: int = 100

    @app.get("/api/users")
    def list_users(user=Depends(get_current_user)):
        """获取用户列表"""
        if not auth_manager.has_permission(user, "manage_users"):
            raise HTTPException(status_code=403, detail="无权限")
        if auth_manager:
            users = auth_manager.get_all_users()
            return {"users": [u.to_dict() for u in users]}
        return {"users": []}

    @app.post("/api/users")
    def create_user(req: UserRequest, user=Depends(get_current_user)):
        """创建用户"""
        if not auth_manager.has_permission(user, "manage_users"):
            raise HTTPException(status_code=403, detail="无权限")
        from app.v3_core import UserRole
        success, message = auth_manager.create_user(
            req.username, req.password, UserRole(req.role)
        )
        if not success:
            raise HTTPException(status_code=400, detail=message)
        return {"message": message}

    @app.delete("/api/users/{username}")
    def delete_user_api(username: str, user=Depends(get_current_user)):
        """删除用户"""
        if not auth_manager.has_permission(user, "manage_users"):
            raise HTTPException(status_code=403, detail="无权限")
        success = auth_manager.delete_user(username)
        if not success:
            raise HTTPException(status_code=404, detail="用户不存在")
        return {"message": "删除成功"}

    # ==================== 分析 API ====================

    @app.get("/api/analytics/overview")
    def analytics_overview(days: int = 30, user=Depends(get_current_user)):
        """分析概览"""
        if analytics:
            return analytics.get_overview(days)
        return {}

    @app.get("/api/analytics/daily")
    def analytics_daily(days: int = 30, user=Depends(get_current_user)):
        """每日使用量"""
        if analytics:
            return {"data": analytics.get_daily_usage(days)}
        return {"data": []}

    @app.get("/api/analytics/models")
    def analytics_models(days: int = 30, user=Depends(get_current_user)):
        """模型分布"""
        if analytics:
            return {"data": analytics.get_model_distribution(days)}
        return {"data": []}

    @app.get("/api/analytics/cost")
    def analytics_cost(days: int = 30, user=Depends(get_current_user)):
        """成本趋势"""
        if analytics:
            return {"data": analytics.get_cost_trend(days)}
        return {"data": []}

    @app.get("/api/analytics/performance")
    def analytics_performance(days: int = 7, user=Depends(get_current_user)):
        """性能统计"""
        if analytics:
            return analytics.get_performance_stats(days)
        return {}

    @app.get("/api/analytics/users")
    def analytics_users(days: int = 30, user=Depends(get_current_user)):
        """用户排行"""
        if analytics:
            return {"data": analytics.get_user_ranking(days)}
        return {"data": []}

    @app.get("/api/analytics/providers")
    def analytics_providers(days: int = 30, user=Depends(get_current_user)):
        """供应商统计"""
        if analytics:
            return {"data": analytics.get_provider_stats(days)}
        return {"data": []}

    @app.get("/api/analytics/hourly")
    def analytics_hourly(days: int = 7, user=Depends(get_current_user)):
        """小时分布"""
        if analytics:
            return {"data": analytics.get_hourly_distribution(days)}
        return {"data": []}

    # ==================== MCP API ====================

    @app.get("/api/mcp/tools")
    def mcp_tools(user=Depends(get_current_user)):
        """获取 MCP 工具列表"""
        if mcp_server:
            return {"tools": [t.to_dict() for t in mcp_server.get_tools()]}
        return {"tools": []}

    @app.post("/api/mcp/tools/{tool_name}/call")
    def mcp_call_tool(tool_name: str, arguments: Dict = {},
                      user=Depends(get_current_user)):
        """调用 MCP 工具"""
        if not auth_manager.has_permission(user, "call_models"):
            raise HTTPException(status_code=403, detail="无权限")
        if mcp_server:
            return mcp_server.call_tool(tool_name, arguments)
        raise HTTPException(status_code=500, detail="MCP 服务器未初始化")

    # ==================== 插件 API ====================

    @app.get("/api/plugins")
    def list_plugins(user=Depends(get_current_user)):
        """获取插件列表"""
        if plugin_manager:
            return {"plugins": [p.to_dict() for p in plugin_manager.get_all_plugins()]}
        return {"plugins": []}

    @app.post("/api/plugins/{plugin_id}/enable")
    def enable_plugin(plugin_id: str, user=Depends(get_current_user)):
        """启用插件"""
        if not auth_manager.has_permission(user, "manage_plugins"):
            raise HTTPException(status_code=403, detail="无权限")
        if plugin_manager:
            success = plugin_manager.enable_plugin(plugin_id)
            if not success:
                raise HTTPException(status_code=404, detail="插件不存在")
            return {"message": "已启用"}
        raise HTTPException(status_code=500, detail="插件管理器未初始化")

    @app.post("/api/plugins/{plugin_id}/disable")
    def disable_plugin(plugin_id: str, user=Depends(get_current_user)):
        """禁用插件"""
        if not auth_manager.has_permission(user, "manage_plugins"):
            raise HTTPException(status_code=403, detail="无权限")
        if plugin_manager:
            success = plugin_manager.disable_plugin(plugin_id)
            if not success:
                raise HTTPException(status_code=404, detail="插件不存在")
            return {"message": "已禁用"}
        raise HTTPException(status_code=500, detail="插件管理器未初始化")

    # ==================== 缓存 API ====================

    @app.get("/api/cache/stats")
    def cache_stats(user=Depends(get_current_user)):
        """缓存统计"""
        if cache:
            return cache.get_stats()
        return {}

    @app.post("/api/cache/clear")
    def clear_cache(user=Depends(get_current_user)):
        """清空缓存"""
        if not auth_manager.has_permission(user, "manage_config"):
            raise HTTPException(status_code=403, detail="无权限")
        if cache:
            cache.clear()
            return {"message": "缓存已清空"}
        return {"message": "缓存未初始化"}

    # ==================== 审计日志 API ====================

    @app.get("/api/audit/logs")
    def audit_logs(limit: int = 100, user=Depends(get_current_user)):
        """审计日志"""
        if not auth_manager.has_permission(user, "view_logs"):
            raise HTTPException(status_code=403, detail="无权限")
        return {"logs": []}  # 由外部填充

    # ==================== 静态文件和页面 ====================

    @app.get("/", response_class=HTMLResponse)
    def index():
        """主页面"""
        return DASHBOARD_HTML

    @app.get("/api/health")
    def health():
        """健康检查"""
        return {"status": "ok", "version": "3.0.0", "timestamp": int(time.time())}

    return app


# ==================== 内嵌 Dashboard HTML ====================

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AI Router V3 - 控制面板</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
               background: #0f1117; color: #e1e4e8; min-height: 100vh; }
        .header { background: #161b22; padding: 1rem 2rem; border-bottom: 1px solid #30363d;
                  display: flex; justify-content: space-between; align-items: center; }
        .header h1 { font-size: 1.5rem; color: #58a6ff; }
        .nav { display: flex; gap: 1rem; }
        .nav a { color: #8b949e; text-decoration: none; padding: 0.5rem 1rem;
                 border-radius: 6px; transition: all 0.2s; }
        .nav a:hover, .nav a.active { color: #58a6ff; background: #21262d; }
        .container { max-width: 1400px; margin: 0 auto; padding: 2rem; }
        .cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
                 gap: 1.5rem; margin-bottom: 2rem; }
        .card { background: #161b22; border: 1px solid #30363d; border-radius: 12px;
                padding: 1.5rem; transition: transform 0.2s; }
        .card:hover { transform: translateY(-2px); border-color: #58a6ff; }
        .card-title { font-size: 0.85rem; color: #8b949e; margin-bottom: 0.5rem; }
        .card-value { font-size: 2rem; font-weight: 700; color: #58a6ff; }
        .card-sub { font-size: 0.8rem; color: #6e7681; margin-top: 0.25rem; }
        .section { background: #161b22; border: 1px solid #30363d; border-radius: 12px;
                   padding: 1.5rem; margin-bottom: 1.5rem; }
        .section-title { font-size: 1.1rem; font-weight: 600; margin-bottom: 1rem;
                         color: #e1e4e8; border-bottom: 1px solid #30363d; padding-bottom: 0.5rem; }
        table { width: 100%; border-collapse: collapse; }
        th, td { padding: 0.75rem; text-align: left; border-bottom: 1px solid #21262d; }
        th { color: #8b949e; font-weight: 500; font-size: 0.85rem; }
        td { font-size: 0.9rem; }
        .badge { display: inline-block; padding: 0.2rem 0.6rem; border-radius: 12px;
                 font-size: 0.75rem; font-weight: 500; }
        .badge-success { background: #238636; color: #fff; }
        .badge-warning { background: #9e6a03; color: #fff; }
        .badge-error { background: #da3633; color: #fff; }
        .progress { height: 8px; background: #21262d; border-radius: 4px; overflow: hidden; }
        .progress-bar { height: 100%; background: linear-gradient(90deg, #58a6ff, #1f6feb);
                        border-radius: 4px; transition: width 0.3s; }
        .login-container { max-width: 400px; margin: 5rem auto; }
        .login-input { width: 100%; padding: 0.75rem 1rem; margin-bottom: 1rem;
                       background: #0d1117; border: 1px solid #30363d; border-radius: 8px;
                       color: #e1e4e8; font-size: 1rem; }
        .login-input:focus { outline: none; border-color: #58a6ff; }
        .btn { padding: 0.75rem 1.5rem; background: #238636; color: #fff; border: none;
               border-radius: 8px; font-size: 1rem; cursor: pointer; transition: background 0.2s; }
        .btn:hover { background: #2ea043; }
        .btn-secondary { background: #21262d; border: 1px solid #30363d; }
        .btn-secondary:hover { background: #30363d; }
        .chart-placeholder { height: 200px; display: flex; align-items: center;
                             justify-content: center; color: #6e7681;
                             border: 1px dashed #30363d; border-radius: 8px; }
    </style>
</head>
<body>
    <div class="header">
        <h1>🚀 AI Router V3</h1>
        <div class="nav">
            <a href="#" class="active" onclick="showSection('dashboard')">仪表板</a>
            <a href="#" onclick="showSection('models')">模型</a>
            <a href="#" onclick="showSection('prompts')">Prompts</a>
            <a href="#" onclick="showSection('analytics')">分析</a>
            <a href="#" onclick="showSection('settings')">设置</a>
            <a href="#" onclick="logout()">登出</a>
        </div>
    </div>

    <div class="container">
        <!-- 仪表板 -->
        <div id="dashboard-section">
            <div class="cards" id="stats-cards">
                <div class="card">
                    <div class="card-title">总请求数</div>
                    <div class="card-value" id="stat-requests">-</div>
                    <div class="card-sub">近7天</div>
                </div>
                <div class="card">
                    <div class="card-title">总Token</div>
                    <div class="card-value" id="stat-tokens">-</div>
                    <div class="card-sub">近7天</div>
                </div>
                <div class="card">
                    <div class="card-title">总费用</div>
                    <div class="card-value" id="stat-cost">-</div>
                    <div class="card-sub">USD</div>
                </div>
                <div class="card">
                    <div class="card-title">成功率</div>
                    <div class="card-value" id="stat-success">-</div>
                    <div class="card-sub">近7天</div>
                </div>
            </div>

            <div class="section">
                <div class="section-title">📊 每日使用趋势</div>
                <div class="chart-placeholder" id="daily-chart">加载中...</div>
            </div>

            <div class="section">
                <div class="section-title">🤖 模型分布</div>
                <table>
                    <thead><tr><th>模型</th><th>请求数</th><th>Token</th><th>费用</th><th>平均延迟</th></tr></thead>
                    <tbody id="models-table"></tbody>
                </table>
            </div>
        </div>

        <!-- 模型管理 -->
        <div id="models-section" style="display:none">
            <div class="section">
                <div class="section-title">🧠 模型推荐</div>
                <table>
                    <thead><tr><th>场景</th><th>推荐模型</th><th>原因</th><th>置信度</th></tr></thead>
                    <tbody id="recommendations-table"></tbody>
                </table>
            </div>
            <div class="section">
                <div class="section-title">📈 模型性能</div>
                <table>
                    <thead><tr><th>模型</th><th>请求数</th><th>成功率</th><th>平均延迟</th><th>总费用</th></tr></thead>
                    <tbody id="model-metrics-table"></tbody>
                </table>
            </div>
        </div>

        <!-- Prompt 管理 -->
        <div id="prompts-section" style="display:none">
            <div class="section">
                <div class="section-title" style="display:flex;justify-content:space-between">
                    <span>📝 Prompt 模板</span>
                    <button class="btn" onclick="showCreatePrompt()">+ 新建</button>
                </div>
                <table>
                    <thead><tr><th>名称</th><th>分类</th><th>标签</th><th>使用次数</th><th>操作</th></tr></thead>
                    <tbody id="prompts-table"></tbody>
                </table>
            </div>
        </div>

        <!-- 数据分析 -->
        <div id="analytics-section" style="display:none">
            <div class="section">
                <div class="section-title">📉 成本趋势</div>
                <div class="chart-placeholder" id="cost-chart">加载中...</div>
            </div>
            <div class="section">
                <div class="section-title">👥 用户排行</div>
                <table>
                    <thead><tr><th>用户</th><th>请求数</th><th>Token</th><th>费用</th></tr></thead>
                    <tbody id="users-table"></tbody>
                </table>
            </div>
            <div class="section">
                <div class="section-title">⚡ 性能统计</div>
                <div class="cards" id="performance-cards"></div>
            </div>
        </div>

        <!-- 设置 -->
        <div id="settings-section" style="display:none">
            <div class="section">
                <div class="section-title">⚙️ 调度策略</div>
                <p style="margin-bottom:1rem;color:#8b949e">选择 AI 调度策略</p>
                <select id="strategy-select" onchange="setStrategy(this.value)"
                        style="padding:0.5rem 1rem;background:#0d1117;border:1px solid #30363d;
                               border-radius:8px;color:#e1e4e8;font-size:1rem">
                    <option value="balanced">均衡模式</option>
                    <option value="speed">速度优先</option>
                    <option value="cost">成本优先</option>
                    <option value="quality">质量优先</option>
                </select>
            </div>
            <div class="section">
                <div class="section-title">🔧 缓存</div>
                <p style="margin-bottom:1rem;color:#8b949e" id="cache-stats">加载中...</p>
                <button class="btn btn-secondary" onclick="clearCache()">清空缓存</button>
            </div>
            <div class="section">
                <div class="section-title">🔌 插件</div>
                <table>
                    <thead><tr><th>插件</th><th>类型</th><th>状态</th><th>操作</th></tr></thead>
                    <tbody id="plugins-table"></tbody>
                </table>
            </div>
        </div>
    </div>

    <script>
        const API_BASE = '/api';
        let token = localStorage.getItem('token') || '';

        async function api(path, options = {}) {
            const headers = { 'Content-Type': 'application/json' };
            if (token) headers['Authorization'] = 'Bearer ' + token;
            const res = await fetch(API_BASE + path, { ...options, headers });
            if (res.status === 401) { showLogin(); return null; }
            return res.json();
        }

        function showLogin() {
            document.body.innerHTML = `
                <div class="login-container">
                    <h2 style="text-align:center;margin-bottom:2rem;color:#58a6ff">AI Router V3</h2>
                    <input class="login-input" id="login-user" placeholder="用户名" value="admin">
                    <input class="login-input" id="login-pass" type="password" placeholder="密码" autocomplete="current-password">
                    <button class="btn" style="width:100%" onclick="doLogin()">登录</button>
                </div>`;
        }

        async function doLogin() {
            const username = document.getElementById('login-user').value;
            const password = document.getElementById('login-pass').value;
            const res = await fetch(API_BASE + '/auth/login', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username, password })
            });
            const data = await res.json();
            if (data.token) {
                token = data.token;
                localStorage.setItem('token', token);
                location.reload();
            } else {
                alert(data.detail || '登录失败');
            }
        }

        function logout() {
            localStorage.removeItem('token');
            token = '';
            location.reload();
        }

        function showSection(name) {
            document.querySelectorAll('[id$="-section"]').forEach(el => el.style.display = 'none');
            document.getElementById(name + '-section').style.display = 'block';
            document.querySelectorAll('.nav a').forEach(a => a.classList.remove('active'));
            event.target.classList.add('active');

            if (name === 'dashboard') loadDashboard();
            if (name === 'models') loadModels();
            if (name === 'prompts') loadPrompts();
            if (name === 'analytics') loadAnalytics();
            if (name === 'settings') loadSettings();
        }

        async function loadDashboard() {
            const data = await api('/dashboard');
            if (!data) return;
            const ov = data.overview || {};
            document.getElementById('stat-requests').textContent = ov.total_requests || 0;
            document.getElementById('stat-tokens').textContent = (ov.total_tokens || 0).toLocaleString();
            document.getElementById('stat-cost').textContent = '$' + (ov.total_cost_usd || 0).toFixed(4);
            document.getElementById('stat-success').textContent = (ov.success_rate || 100) + '%';

            // 模型分布
            const models = data.model_distribution || [];
            const tbody = document.getElementById('models-table');
            tbody.innerHTML = models.map(m =>
                `<tr><td>${m.model}</td><td>${m.requests}</td><td>${m.tokens.toLocaleString()}</td>
                     <td>$${m.cost_usd.toFixed(4)}</td><td>${m.avg_time_ms}ms</td></tr>`
            ).join('');
        }

        async function loadModels() {
            const data = await api('/models');
            if (!data) return;
            const recs = data.recommendations || recommendations || [];
            const tbody = document.getElementById('recommendations-table');
            tbody.innerHTML = recs.map(r =>
                `<tr><td>${r.scenario}</td><td>${r.recommended_model}</td><td>${r.reason}</td>
                     <td>${(r.confidence * 100).toFixed(0)}%</td></tr>`
            ).join('');

            const metrics = data.models || [];
            const tbody2 = document.getElementById('model-metrics-table');
            tbody2.innerHTML = metrics.map(m =>
                `<tr><td>${m.model}</td><td>${m.total_requests}</td>
                     <td>${m.success_rate}%</td><td>${m.avg_latency_ms}ms</td>
                     <td>$${m.total_cost.toFixed(4)}</td></tr>`
            ).join('');
        }

        async function loadPrompts() {
            const data = await api('/prompts');
            if (!data) return;
            const prompts = data.prompts || [];
            const tbody = document.getElementById('prompts-table');
            tbody.innerHTML = prompts.map(p =>
                `<tr><td>${p.name}</td><td>${p.category}</td>
                    <td>${(p.tags || []).map(t=>`<span class="badge badge-success">${t}</span>`).join(' ')}</td>
                    <td>${p.use_count}</td>
                    <td><button class="btn btn-secondary" onclick="renderPrompt('${p.id}')">使用</button></td></tr>`
            ).join('');
        }

        async function loadAnalytics() {
            const [cost, users, perf] = await Promise.all([
                api('/analytics/cost'), api('/analytics/users'), api('/analytics/performance')
            ]);
            if (cost) {
                document.getElementById('cost-chart').textContent =
                    (cost.data || []).map(d => `${d.date}: $${d.cost_usd}`).join(' | ');
            }
            if (users) {
                const tbody = document.getElementById('users-table');
                tbody.innerHTML = (users.data || []).map(u =>
                    `<tr><td>${u.user}</td><td>${u.requests}</td>
                         <td>${u.tokens.toLocaleString()}</td><td>$${u.cost_usd.toFixed(4)}</td></tr>`
                ).join('');
            }
            if (perf) {
                document.getElementById('performance-cards').innerHTML = `
                    <div class="card"><div class="card-title">平均延迟</div>
                        <div class="card-value">${perf.avg_latency}ms</div></div>
                    <div class="card"><div class="card-title">P90延迟</div>
                        <div class="card-value">${perf.p90}ms</div></div>
                    <div class="card"><div class="card-title">P99延迟</div>
                        <div class="card-value">${perf.p99}ms</div></div>
                    <div class="card"><div class="card-title">错误率</div>
                        <div class="card-value">${perf.error_rate}%</div></div>`;
            }
        }

        async function loadSettings() {
            const [cache, plugins] = await Promise.all([
                api('/cache/stats'), api('/plugins')
            ]);
            if (cache) {
                document.getElementById('cache-stats').textContent =
                    `命中: ${cache.hits || 0} | 未命中: ${cache.misses || 0} | 命中率: ${cache.hit_rate || 0}%`;
            }
            if (plugins) {
                const tbody = document.getElementById('plugins-table');
                tbody.innerHTML = (plugins.plugins || []).map(p =>
                    `<tr><td>${p.name}</td><td>${p.type}</td>
                        <td><span class="badge badge-${p.state === 'enabled' ? 'success' : 'warning'}">${p.state}</span></td>
                        <td><button class="btn btn-secondary" onclick="togglePlugin('${p.id}', '${p.state}')">${p.state === 'enabled' ? '禁用' : '启用'}</button></td></tr>`
                ).join('');
            }
        }

        async function setStrategy(strategy) {
            await api('/models/strategy?strategy=' + strategy, { method: 'POST' });
        }

        async function clearCache() {
            await api('/cache/clear', { method: 'POST' });
            loadSettings();
        }

        async function togglePlugin(id, state) {
            await api('/plugins/' + id + '/' + (state === 'enabled' ? 'disable' : 'enable'), { method: 'POST' });
            loadSettings();
        }

        // 初始化
        if (!token) { showLogin(); } else { loadDashboard(); }
    </script>
</body>
</html>
"""
