"""
i18n 国际化模块测试
"""
import pytest
from app.i18n import t, LANGUAGES, TEXTS


class TestI18n:
    """国际化测试"""

    def test_all_languages_have_two_options(self):
        """支持的语言列表包含中英文"""
        codes = [code for name, code in LANGUAGES]
        assert "zh" in codes
        assert "en" in codes

    def test_t_zh_returns_chinese(self):
        """中文模式返回中文"""
        result = t("set_current", "zh")
        assert result == "设为当前"

    def test_t_en_returns_english(self):
        """英文模式返回英文"""
        result = t("set_current", "en")
        assert result == "Set Active"

    def test_t_missing_key_returns_key(self):
        """不存在的 key 返回 key 本身"""
        result = t("nonexistent_key_xyz", "zh")
        assert result == "nonexistent_key_xyz"

    def test_t_format_args(self):
        """格式化参数正确替换"""
        result = t("priority_label", "zh", 1)
        assert "1" in result
        result_en = t("priority_label", "en", 2)
        assert "2" in result_en

    def test_all_keys_have_both_languages(self):
        """所有翻译键都包含中英文"""
        for key, entry in TEXTS.items():
            assert "zh" in entry, f"Key '{key}' missing 'zh'"
            assert "en" in entry, f"Key '{key}' missing 'en'"
            assert entry["zh"], f"Key '{key}' zh is empty"
            assert entry["en"], f"Key '{key}' en is empty"

    def test_tooltip_keys_exist(self):
        """Tooltip 相关键存在"""
        tooltip_keys = [
            "tooltip_url", "tooltip_model", "tooltip_fast_model",
            "tooltip_key", "tooltip_priority", "tooltip_fallback",
            "tooltip_enable"
        ]
        for key in tooltip_keys:
            assert key in TEXTS, f"Missing tooltip key: {key}"
            assert len(TEXTS[key]["zh"]) > 10, f"Tooltip {key} zh too short"
            assert len(TEXTS[key]["en"]) > 10, f"Tooltip {key} en too short"

    def test_no_empty_translations(self):
        """没有空翻译"""
        for key, entry in TEXTS.items():
            for lang, text in entry.items():
                assert text.strip(), f"Empty translation for {key}/{lang}"
