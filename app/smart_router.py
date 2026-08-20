"""
V2 智能模型路由模块
根据任务类型自动选择最优模型：

- 代码任务：优先 Claude / DeepSeek Coder
- 普通聊天：GPT / Gemini
- 低成本：DeepSeek / Kimi
- 复杂任务：自动选择高级模型

支持用户自定义路由规则。
"""
import re
import threading
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass


# 任务类型定义
TASK_TYPES = {
    "code": {
        "name": "代码任务",
        "description": "代码生成、调试、重构、代码审查等",
        "keywords": ["代码", "编程", "code", "function", "class", "debug", "refactor",
                     "实现", "编写", "函数", "算法", "python", "javascript", "java",
                     "程序", "开发", "coding", "programming"],
    },
    "chat": {
        "name": "普通聊天",
        "description": "日常对话、问答、翻译、写作等",
        "keywords": ["聊天", "对话", "问答", "翻译", "写作", "chat", "talk",
                     "hello", "hi", "你好", "帮我", "请问", "解释", "介绍"],
    },
    "cheap": {
        "name": "低成本",
        "description": "简单任务，优先使用低价模型",
        "keywords": ["简单", "快速", "摘要", "总结", "cheap", "simple", "quick"],
    },
    "complex": {
        "name": "复杂任务",
        "description": "复杂推理、深度分析、大型项目等",
        "keywords": ["复杂", "分析", "推理", "深度", "架构", "complex", "analyze",
                     "reasoning", "architecture", "设计", "方案", "research"],
    },
}


@dataclass
class RoutingRule:
    """路由规则"""
    task_type: str
    description: str
    preferred_models: List[str]  # 优先模型列表
    fallback_models: List[str]   # 备选模型列表
    enabled: bool = True
    max_cost_per_request: float = 0.1  # 单次请求最大成本（美元）

    def to_dict(self) -> Dict:
        return {
            "task_type": self.task_type,
            "description": self.description,
            "preferred_models": self.preferred_models,
            "fallback_models": self.fallback_models,
            "enabled": self.enabled,
            "max_cost_per_request": self.max_cost_per_request,
        }


@dataclass
class ModelCapability:
    """模型能力信息"""
    model_name: str
    provider_name: str
    provider_id: str
    base_url: str
    api_key: str
    auth_mode: str
    provider_type: str
    input_price: float  # $/1M tokens
    output_price: float  # $/1M tokens
    context_length: int
    capabilities: List[str]  # code, chat, reasoning, vision, etc.
    speed: str = "medium"  # fast | medium | slow
    enabled: bool = True


class TaskClassifier:
    """任务分类器 - 根据消息内容判断任务类型"""

    @staticmethod
    def classify(messages: List[Dict], explicit_type: str = None, **kwargs) -> str:
        """
        判断任务类型
        :param messages: 消息列表
        :param explicit_type: 显式指定的任务类型
        :return: 任务类型代码
        """
        if explicit_type and explicit_type in TASK_TYPES:
            return explicit_type

        # 合并所有消息内容
        full_text = " ".join(
            msg.get("content", "") if isinstance(msg.get("content"), str) else
            " ".join(b.get("text", "") for b in msg.get("content", []) if isinstance(b, dict))
            for msg in messages
        ).lower()

        # 关键词匹配
        scores = {}
        for task_type, info in TASK_TYPES.items():
            score = sum(1 for kw in info["keywords"] if kw.lower() in full_text)
            scores[task_type] = score

        # 特殊规则：代码相关关键词权重更高
        code_signals = [
            r"```", r"def\s+\w+", r"class\s+\w+", r"function\s+\w+", r"import\s+\w+",
            r"const\s+\w+\s*=", r"let\s+\w+\s*=", r"var\s+\w+\s*=",
            r"public\s+class", r"private\s+\w+", r"#include",
            r"写一个", r"编写", r"实现", r"帮我写", r"代码", r"程序",
        ]
        for pattern in code_signals:
            if re.search(pattern, full_text, re.IGNORECASE):
                scores["code"] = scores.get("code", 0) + 2

        # 复杂任务信号
        complex_signals = [
            r"架构", r"系统设计", r"深度分析", r"详细方案", r"research",
            r"comprehensive", r"in-depth", r"architecture",
        ]
        for pattern in complex_signals:
            if re.search(pattern, full_text, re.IGNORECASE):
                scores["complex"] = scores.get("complex", 0) + 2

        # 返回得分最高的类型
        if scores:
            best = max(scores, key=scores.get)
            if scores[best] > 0:
                return best

        return "chat"  # 默认聊天


class SmartRouter:
    """智能模型路由器"""

    def __init__(self, default_task_type: str = "chat", logger=None):
        self.default_task_type = default_task_type
        self.logger = logger
        self._lock = threading.RLock()

        # 模型能力表
        self._models: Dict[str, ModelCapability] = {}

        # 路由规则
        self._rules: Dict[str, RoutingRule] = {}

        # 初始化默认规则
        self._init_default_rules()

    def _init_default_rules(self):
        """初始化默认路由规则"""
        self._rules = {
            "code": RoutingRule(
                task_type="code",
                description="代码任务：优先 Claude / DeepSeek Coder",
                preferred_models=["claude-sonnet-4-20250514", "deepseek-chat"],
                fallback_models=["gpt-4o", "moonshot-v1-32k"],
            ),
            "chat": RoutingRule(
                task_type="chat",
                description="普通聊天：GPT / Gemini",
                preferred_models=["gpt-4o", "gemini-1.5-flash"],
                fallback_models=["claude-3-5-haiku-20241022", "deepseek-chat"],
            ),
            "cheap": RoutingRule(
                task_type="cheap",
                description="低成本：DeepSeek / Kimi",
                preferred_models=["deepseek-chat", "moonshot-v1-8k"],
                fallback_models=["gpt-4o-mini", "LongCat-Flash-Chat"],
            ),
            "complex": RoutingRule(
                task_type="complex",
                description="复杂任务：自动选择高级模型",
                preferred_models=["claude-opus-4-20250514", "gpt-4o"],
                fallback_models=["claude-sonnet-4-20250514", "deepseek-reasoner"],
            ),
        }

    def register_model(self, model: ModelCapability):
        """注册模型能力"""
        with self._lock:
            self._models[model.model_name] = model

    def unregister_model(self, model_name: str):
        """注销模型"""
        with self._lock:
            self._models.pop(model_name, None)

    def update_models(self, models: List[ModelCapability]):
        """批量更新模型列表"""
        with self._lock:
            self._models = {m.model_name: m for m in models}

    def set_rule(self, task_type: str, rule: RoutingRule):
        """设置路由规则"""
        with self._lock:
            self._rules[task_type] = rule

    def get_rule(self, task_type: str) -> Optional[RoutingRule]:
        """获取路由规则"""
        with self._lock:
            return self._rules.get(task_type)

    def get_all_rules(self) -> Dict[str, RoutingRule]:
        """获取所有路由规则"""
        with self._lock:
            return dict(self._rules)

    def route(self, messages: List[Dict], explicit_task_type: str = None,
              preferred_model: str = None, exclude_models: List[str] = None) -> Optional[ModelCapability]:
        """
        智能路由：根据消息内容选择最优模型
        :param messages: 消息列表
        :param explicit_task_type: 显式任务类型
        :param preferred_model: 用户指定的模型
        :param exclude_models: 排除的模型列表
        :return: 选中的模型能力信息
        """
        with self._lock:
            # 1. 如果用户指定了模型，优先使用
            if preferred_model and preferred_model in self._models:
                model = self._models[preferred_model]
                if model.enabled and preferred_model not in (exclude_models or []):
                    return model

            # 2. 分类任务
            task_type = TaskClassifier.classify(messages, explicit_task_type)
            rule = self._rules.get(task_type)
            if not rule or not rule.enabled:
                rule = self._rules.get("chat")  # 回退到聊天规则

            if not rule:
                # 没有规则，返回第一个可用模型
                for m in self._models.values():
                    if m.enabled:
                        return m
                return None

            # 3. 按优先级选择模型
            exclude = exclude_models or []

            # 先尝试优先模型
            for model_name in rule.preferred_models:
                if model_name in self._models:
                    model = self._models[model_name]
                    if model.enabled and model_name not in exclude:
                        return model

            # 再尝试备选模型
            for model_name in rule.fallback_models:
                if model_name in self._models:
                    model = self._models[model_name]
                    if model.enabled and model_name not in exclude:
                        return model

            # 最后尝试任何可用模型
            for model in self._models.values():
                if model.enabled and model.model_name not in exclude:
                    return model

            return None

    def route_by_name(self, model_name: str) -> Optional[ModelCapability]:
        """根据模型名称获取模型信息"""
        with self._lock:
            return self._models.get(model_name)

    def get_routing_info(self, messages: List[Dict],
                         explicit_task_type: str = None) -> Dict:
        """获取路由决策信息（用于显示）"""
        task_type = TaskClassifier.classify(messages, explicit_task_type)
        rule = self._rules.get(task_type)
        selected = self.route(messages, explicit_task_type)

        return {
            "detected_task_type": task_type,
            "task_type_name": TASK_TYPES.get(task_type, {}).get("name", task_type),
            "rule_description": rule.description if rule else "无规则",
            "selected_model": selected.model_name if selected else "无可用模型",
            "selected_provider": selected.provider_name if selected else "",
            "available_models": [m.model_name for m in self._models.values() if m.enabled],
        }

    def get_all_models(self) -> List[ModelCapability]:
        """获取所有已注册模型"""
        with self._lock:
            return list(self._models.values())

    def get_cheapest_model(self, task_type: str = None) -> Optional[ModelCapability]:
        """获取最便宜的模型"""
        with self._lock:
            models = [m for m in self._models.values() if m.enabled]
            if not models:
                return None
            return min(models, key=lambda m: m.input_price + m.output_price)

    def get_fastest_model(self) -> Optional[ModelCapability]:
        """获取最快的模型"""
        with self._lock:
            fast_models = [m for m in self._models.values()
                          if m.enabled and m.speed == "fast"]
            if fast_models:
                return fast_models[0]
            medium_models = [m for m in self._models.values()
                           if m.enabled and m.speed == "medium"]
            if medium_models:
                return medium_models[0]
            return None
