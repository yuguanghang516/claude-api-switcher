"""
V2 Token 价格计算模块
根据模型价格自动计算：
- 美元费用
- 人民币费用
统计：
- 今日花费
- 本月花费
- 各模型花费比例
"""
import threading
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from datetime import date, timedelta


# 汇率（默认，可通过 API 更新）
DEFAULT_USD_TO_CNY = 7.2

# 模型价格表（美元/1M tokens）
# 来源：各模型官方定价（2025年数据）
MODEL_PRICING = {
    # OpenAI
    "gpt-4o": {"input": 2.50, "output": 10.00, "provider": "OpenAI"},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60, "provider": "OpenAI"},
    "gpt-4-turbo": {"input": 10.00, "output": 30.00, "provider": "OpenAI"},
    "gpt-3.5-turbo": {"input": 0.50, "output": 1.50, "provider": "OpenAI"},
    "o1-preview": {"input": 15.00, "output": 60.00, "provider": "OpenAI"},
    "o1-mini": {"input": 3.00, "output": 12.00, "provider": "OpenAI"},

    # Anthropic Claude
    "claude-opus-4-20250514": {"input": 15.00, "output": 75.00, "provider": "Anthropic"},
    "claude-sonnet-4-20250514": {"input": 3.00, "output": 15.00, "provider": "Anthropic"},
    "claude-3-5-sonnet-20241022": {"input": 3.00, "output": 15.00, "provider": "Anthropic"},
    "claude-3-5-haiku-20241022": {"input": 0.80, "output": 4.00, "provider": "Anthropic"},
    "claude-3-opus-20240229": {"input": 15.00, "output": 75.00, "provider": "Anthropic"},

    # DeepSeek
    "deepseek-chat": {"input": 0.07, "output": 0.28, "provider": "DeepSeek"},
    "deepseek-reasoner": {"input": 0.14, "output": 0.56, "provider": "DeepSeek"},

    # Google Gemini
    "gemini-1.5-pro": {"input": 1.25, "output": 5.00, "provider": "Google"},
    "gemini-1.5-flash": {"input": 0.075, "output": 0.30, "provider": "Google"},
    "gemini-2.0-flash": {"input": 0.10, "output": 0.40, "provider": "Google"},

    # Kimi (月之暗面)
    "moonshot-v1-8k": {"input": 0.12, "output": 0.12, "provider": "Kimi"},
    "moonshot-v1-32k": {"input": 0.24, "output": 0.24, "provider": "Kimi"},
    "moonshot-v1-128k": {"input": 0.60, "output": 0.60, "provider": "Kimi"},

    # LongCat
    "LongCat-2.0": {"input": 0.10, "output": 0.20, "provider": "LongCat"},
    "LongCat-Flash-Chat": {"input": 0.05, "output": 0.10, "provider": "LongCat"},

    # OpenRouter (常用)
    "anthropic/claude-sonnet-4": {"input": 3.00, "output": 15.00, "provider": "OpenRouter"},
    "openai/gpt-4o": {"input": 2.50, "output": 10.00, "provider": "OpenRouter"},
}


@dataclass
class CostBreakdown:
    """费用明细"""
    model: str
    input_tokens: int
    output_tokens: int
    input_cost_usd: float
    output_cost_usd: float
    total_cost_usd: float
    total_cost_cny: float
    provider: str = ""

    def to_dict(self) -> Dict:
        return {
            "model": self.model,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "input_cost_usd": round(self.input_cost_usd, 6),
            "output_cost_usd": round(self.output_cost_usd, 6),
            "total_cost_usd": round(self.total_cost_usd, 6),
            "total_cost_cny": round(self.total_cost_cny, 6),
            "provider": self.provider,
        }


class PricingCalculator:
    """价格计算器"""

    def __init__(self, usd_to_cny: float = DEFAULT_USD_TO_CNY,
                 custom_pricing: Dict = None):
        self._pricing = dict(MODEL_PRICING)
        self._usd_to_cny = usd_to_cny
        self._lock = threading.Lock()

        # 合并自定义价格
        if custom_pricing:
            self._pricing.update(custom_pricing)

    def set_exchange_rate(self, rate: float):
        """设置汇率"""
        self._usd_to_cny = rate

    def get_exchange_rate(self) -> float:
        """获取当前汇率"""
        return self._usd_to_cny

    def set_model_pricing(self, model: str, input_price: float,
                          output_price: float, provider: str = ""):
        """设置模型价格"""
        with self._lock:
            self._pricing[model] = {
                "input": input_price,
                "output": output_price,
                "provider": provider,
            }

    def get_model_pricing(self, model: str) -> Optional[Dict]:
        """获取模型价格"""
        return self._pricing.get(model)

    def calculate_cost(self, model: str, input_tokens: int,
                       output_tokens: int) -> CostBreakdown:
        """
        计算请求费用
        :param model: 模型名称
        :param input_tokens: 输入 token 数
        :param output_tokens: 输出 token 数
        :return: CostBreakdown
        """
        pricing = self._pricing.get(model, {"input": 0, "output": 0, "provider": ""})

        input_cost = (input_tokens / 1_000_000) * pricing.get("input", 0)
        output_cost = (output_tokens / 1_000_000) * pricing.get("output", 0)
        total_usd = input_cost + output_cost
        total_cny = total_usd * self._usd_to_cny

        return CostBreakdown(
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            input_cost_usd=input_cost,
            output_cost_usd=output_cost,
            total_cost_usd=total_usd,
            total_cost_cny=total_cny,
            provider=pricing.get("provider", ""),
        )

    def estimate_cost(self, model: str, estimated_input_tokens: int = 1000,
                      estimated_output_tokens: int = 1000) -> CostBreakdown:
        """
        预估请求费用
        """
        return self.calculate_cost(model, estimated_input_tokens, estimated_output_tokens)

    def compare_models(self, input_tokens: int = 1000,
                       output_tokens: int = 1000) -> List[Dict]:
        """
        比较所有模型的费用
        :return: 按费用排序的模型列表
        """
        results = []
        for model in self._pricing:
            cost = self.calculate_cost(model, input_tokens, output_tokens)
            results.append({
                "model": model,
                "provider": cost.provider,
                "total_cost_usd": round(cost.total_cost_usd, 6),
                "total_cost_cny": round(cost.total_cost_cny, 6),
            })
        return sorted(results, key=lambda x: x["total_cost_usd"])

    def get_cheapest_model(self) -> str:
        """获取最便宜的模型"""
        comparison = self.compare_models(1000, 1000)
        return comparison[0]["model"] if comparison else ""

    def get_all_pricing(self) -> Dict:
        """获取所有模型价格"""
        return dict(self._pricing)

    def get_pricing_table(self) -> List[Dict]:
        """获取价格表（用于显示）"""
        table = []
        for model, pricing in sorted(self._pricing.items()):
            table.append({
                "model": model,
                "provider": pricing.get("provider", ""),
                "input_price": pricing.get("input", 0),
                "output_price": pricing.get("output", 0),
                "input_price_cny": round(pricing.get("input", 0) * self._usd_to_cny, 4),
                "output_price_cny": round(pricing.get("output", 0) * self._usd_to_cny, 4),
            })
        return table
