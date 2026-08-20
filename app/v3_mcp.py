"""
V3 MCP (Model Context Protocol) 支持
=====================================
实现 MCP 协议，支持工具调用、文件访问、数据库查询

MCP 功能：
- 工具注册与调用
- 文件系统访问
- 数据库查询
- 资源管理
"""
import os
import json
import time
import subprocess
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from enum import Enum


class MCPToolType(Enum):
    """MCP 工具类型"""
    FUNCTION = "function"
    FILE = "file"
    DATABASE = "database"
    SHELL = "shell"
    WEB = "web"
    CUSTOM = "custom"


@dataclass
class MCPTool:
    """MCP 工具定义"""
    name: str
    description: str
    parameters: Dict  # JSON Schema
    tool_type: MCPToolType
    handler: Optional[Callable] = None
    enabled: bool = True

    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
            "type": self.tool_type.value,
            "enabled": self.enabled,
        }


@dataclass
class MCPResource:
    """MCP 资源"""
    uri: str
    name: str
    description: str
    mime_type: str
    content: Any = None


class MCPServer:
    """MCP 服务器"""

    def __init__(self, data_dir: str, logger=None, enable_shell: bool = False):
        self.data_dir = data_dir
        self.logger = logger
        self.enable_shell = enable_shell
        self._tools: Dict[str, MCPTool] = {}
        self._resources: Dict[str, MCPResource] = {}
        self._register_defaults()

    def _register_defaults(self):
        """注册默认工具"""
        # 文件读取工具
        self.register_tool(MCPTool(
            name="read_file",
            description="读取文件内容",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "文件路径"},
                    "encoding": {"type": "string", "description": "编码格式", "default": "utf-8"},
                },
                "required": ["path"],
            },
            tool_type=MCPToolType.FILE,
            handler=self._handle_read_file,
        ))

        # 文件写入工具
        self.register_tool(MCPTool(
            name="write_file",
            description="写入文件内容",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "文件路径"},
                    "content": {"type": "string", "description": "文件内容"},
                    "encoding": {"type": "string", "description": "编码格式", "default": "utf-8"},
                },
                "required": ["path", "content"],
            },
            tool_type=MCPToolType.FILE,
            handler=self._handle_write_file,
        ))

        # 文件列表工具
        self.register_tool(MCPTool(
            name="list_files",
            description="列出目录内容",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "目录路径"},
                    "pattern": {"type": "string", "description": "文件匹配模式", "default": "*"},
                },
                "required": ["path"],
            },
            tool_type=MCPToolType.FILE,
            handler=self._handle_list_files,
        ))

        # Shell 命令属于高风险能力，开源发行版默认不注册；仅显式配置后启用。
        if self.enable_shell:
            self.register_tool(MCPTool(
                name="run_command",
                description="执行 Shell 命令（高风险，需显式启用）",
                parameters={
                    "type": "object",
                    "properties": {
                        "command": {"type": "string", "description": "命令"},
                        "timeout": {"type": "integer", "description": "超时秒数", "default": 30},
                    },
                    "required": ["command"],
                },
                tool_type=MCPToolType.SHELL,
                handler=self._handle_run_command,
            ))

        # Web 搜索工具
        self.register_tool(MCPTool(
            name="web_search",
            description="网络搜索",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索关键词"},
                    "limit": {"type": "integer", "description": "结果数量", "default": 5},
                },
                "required": ["query"],
            },
            tool_type=MCPToolType.WEB,
            handler=self._handle_web_search,
        ))

        # 数据库查询工具
        self.register_tool(MCPTool(
            name="query_db",
            description="查询 SQLite 数据库",
            parameters={
                "type": "object",
                "properties": {
                    "db_path": {"type": "string", "description": "数据库路径"},
                    "sql": {"type": "string", "description": "SQL 查询"},
                    "params": {"type": "array", "items": {"type": "string"}, "description": "参数"},
                },
                "required": ["db_path", "sql"],
            },
            tool_type=MCPToolType.DATABASE,
            handler=self._handle_query_db,
        ))

    def register_tool(self, tool: MCPTool):
        """注册工具"""
        self._tools[tool.name] = tool

    def unregister_tool(self, name: str):
        """注销工具"""
        self._tools.pop(name, None)

    def get_tools(self) -> List[MCPTool]:
        """获取所有工具"""
        return [t for t in self._tools.values() if t.enabled]

    def get_tool(self, name: str) -> Optional[MCPTool]:
        """获取工具"""
        return self._tools.get(name)

    def call_tool(self, name: str, arguments: Dict) -> Dict:
        """调用工具"""
        tool = self._tools.get(name)
        if not tool:
            return {"error": f"工具不存在: {name}"}
        if not tool.enabled:
            return {"error": f"工具已禁用: {name}"}
        if not tool.handler:
            return {"error": f"工具无处理器: {name}"}

        try:
            result = tool.handler(arguments)
            return {"success": True, "result": result}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_tools_schema(self) -> List[Dict]:
        """获取工具 Schema（OpenAI 格式）"""
        schemas = []
        for tool in self.get_tools():
            schemas.append({
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                },
            })
        return schemas

    # ==================== 工具处理器 ====================

    def _handle_read_file(self, args: Dict) -> Dict:
        """读取文件"""
        path = args["path"]
        encoding = args.get("encoding", "utf-8")
        if not os.path.exists(path):
            raise FileNotFoundError(f"文件不存在: {path}")
        with open(path, "r", encoding=encoding) as f:
            content = f.read()
        return {
            "path": path,
            "content": content,
            "size": len(content),
        }

    def _handle_write_file(self, args: Dict) -> Dict:
        """写入文件"""
        path = args["path"]
        content = args["content"]
        encoding = args.get("encoding", "utf-8")
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding=encoding) as f:
            f.write(content)
        return {"path": path, "size": len(content)}

    def _handle_list_files(self, args: Dict) -> Dict:
        """列出文件"""
        import fnmatch
        path = args["path"]
        pattern = args.get("pattern", "*")
        if not os.path.isdir(path):
            raise NotADirectoryError(f"不是目录: {path}")
        files = []
        for name in os.listdir(path):
            if fnmatch.fnmatch(name, pattern):
                full = os.path.join(path, name)
                files.append({
                    "name": name,
                    "path": full,
                    "is_dir": os.path.isdir(full),
                    "size": os.path.getsize(full) if os.path.isfile(full) else 0,
                })
        return {"path": path, "files": files, "count": len(files)}

    def _handle_run_command(self, args: Dict) -> Dict:
        """执行命令"""
        command = args["command"]
        timeout = args.get("timeout", 30)
        result = subprocess.run(
            command, shell=True, capture_output=True, text=True, timeout=timeout
        )
        return {
            "command": command,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode,
        }

    def _handle_web_search(self, args: Dict) -> Dict:
        """网络搜索（占位实现）"""
        query = args["query"]
        limit = args.get("limit", 5)
        # 实际实现需要接入搜索引擎 API
        return {
            "query": query,
            "results": [],
            "message": "需要配置搜索引擎 API (如 SerpAPI, Bing Search)",
        }

    def _handle_query_db(self, args: Dict) -> Dict:
        """查询数据库"""
        import sqlite3
        db_path = args["db_path"]
        sql = args["sql"]
        params = args.get("params", [])
        if not os.path.exists(db_path):
            raise FileNotFoundError(f"数据库不存在: {db_path}")
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(sql, params)
        rows = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return {"rows": rows, "count": len(rows)}
