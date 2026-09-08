import copy

import customtkinter as ctk

from app.theme import DARK, LIGHT, FONT_FAMILY, apply_widget_defaults


def test_desktop_widget_defaults_are_consistent_and_repeatable():
    original = copy.deepcopy(ctk.ThemeManager.theme)
    try:
        apply_widget_defaults()
        first = copy.deepcopy(ctk.ThemeManager.theme)
        apply_widget_defaults()
        assert ctk.ThemeManager.theme == first
        assert first['CTkFont']['family'] == FONT_FAMILY
        assert first['CTkFont']['size'] == 14
        for kind in ('CTkEntry', 'CTkComboBox', 'CTkOptionMenu'):
            assert first[kind]['text_color'] == [LIGHT.text_primary, DARK.text_primary]
        assert first['CTkButton']['text_color'] == [LIGHT.accent_text, DARK.accent_text]
    finally:
        ctk.ThemeManager.theme = original
