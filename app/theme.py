"""Centralized semantic theme system for the Claude API Switcher desktop app.

Every panel (main window, gateway, V2 dashboard) reads its colors, spacing and
typography from here so the whole application looks like one cohesive product.
The system supports three modes — ``system``, ``light`` and ``dark`` — and the
choice is persisted by ``ConfigManager`` (see ``app.config_manager``).

The palette is *semantic*: widgets ask for ``accent`` or ``success`` rather than
hex values, so the same code renders correctly in light and dark. The design
direction is a restrained Windows developer tool:

* neutral surfaces
* cobalt primary actions
* violet reserved for AI / model identity
* green / red reserved for status

Typography uses Microsoft YaHei UI with a Segoe UI fallback, a 4/8/12/16/24
spacing scale, and 8–12 px radii.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, List, Optional

import customtkinter as ctk

# ---------------------------------------------------------------------------
# Typography & spacing
# ---------------------------------------------------------------------------

FONT_FAMILY = "Microsoft YaHei UI"
FONT_FAMILY_FALLBACK = "Segoe UI"
FONT_MONO = "Consolas"

PAD_XS = 4
PAD_SM = 8
PAD_MD = 12
PAD_LG = 16
PAD_XL = 24

RADIUS_SM = 8
RADIUS_MD = 10
RADIUS_LG = 12


# ---------------------------------------------------------------------------
# Semantic palette
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Palette:
    """All colors a widget might need, named by meaning not by value."""

    # Surfaces
    bg_primary: str
    bg_surface: str
    bg_elevated: str
    bg_input: str

    # Text
    text_primary: str
    text_secondary: str
    text_muted: str

    # Borders
    border: str
    border_strong: str

    # Primary actions (cobalt)
    accent: str
    accent_hover: str
    accent_text: str

    # AI / model identity (violet)
    ai: str
    ai_hover: str
    ai_text: str

    # Status
    success: str
    success_dark: str
    danger: str
    danger_dark: str
    info: str
    info_dark: str
    warning: str

    # Misc widget colors
    hover: str          # hover for transparent / secondary buttons
    subtle: str         # subtle filled chip / row background


# Windows 11 inspired light palette.
LIGHT = Palette(
    bg_primary="#f3f3f3",
    bg_surface="#ffffff",
    bg_elevated="#f5f5f5",
    bg_input="#ffffff",
    text_primary="#1a1a1a",
    text_secondary="#616161",
    text_muted="#767676",
    border="#e0e0e0",
    border_strong="#c4c4c4",
    accent="#0f6cbd",
    accent_hover="#115ea3",
    accent_text="#ffffff",
    ai="#7c3aed",
    ai_hover="#6d28d9",
    ai_text="#ffffff",
    success="#0f9d58",
    success_dark="#0b8043",
    danger="#d13438",
    danger_dark="#a4262c",
    info="#0078d4",
    info_dark="#005a9e",
    warning="#f7630c",
    hover="#e5e5e5",
    subtle="#efefef",
)

# Windows 11 inspired dark palette.
DARK = Palette(
    bg_primary="#1e1e1e",
    bg_surface="#252526",
    bg_elevated="#2d2d2d",
    bg_input="#333333",
    text_primary="#f1f5f9",
    text_secondary="#94a3b8",
    # Keep muted copy visually subordinate while still meeting WCAG AA against
    # the darkest input surface used by the app (#333333).
    text_muted="#8d9db2",
    border="#3c3c3c",
    border_strong="#5a5a5a",
    accent="#4cc2ff",
    accent_hover="#2f8fff",
    accent_text="#000000",
    ai="#9b6dff",
    ai_hover="#7c3aed",
    ai_text="#ffffff",
    success="#3fb950",
    success_dark="#2ea043",
    danger="#f85149",
    danger_dark="#da3633",
    info="#79c0ff",
    info_dark="#58a6ff",
    warning="#d29922",
    hover="#3a3a3d",
    subtle="#2a2a2e",
)

_PALETTES = {"light": LIGHT, "dark": DARK}


# ---------------------------------------------------------------------------
# Theme manager (singleton)
# ---------------------------------------------------------------------------


class ThemeManager:
    """Holds the current theme mode and notifies listeners on change.

    Persistence is intentionally *not* done here: this module has no dependency
    on ``ConfigManager`` to avoid a circular import.  Callers read the stored
    mode at startup, call :meth:`set_mode`, and persist the value themselves.
    """

    def __init__(self, mode: str = "system") -> None:
        self._mode = mode if mode in ("system", "light", "dark") else "system"
        self._listeners: List[Callable[[], None]] = []

    # -- mode ----------------------------------------------------------------

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def resolved_mode(self) -> str:
        """``light`` or ``dark`` — resolves ``system`` via the OS."""
        if self._mode in ("light", "dark"):
            return self._mode
        return _detect_system_mode()

    @property
    def palette(self) -> Palette:
        return _PALETTES[self.resolved_mode]

    def set_mode(self, mode: str) -> None:
        """Switch theme mode, update customtkinter, and notify listeners."""
        if mode not in ("system", "light", "dark"):
            mode = "system"
        if mode == self._mode:
            return
        self._mode = mode
        ctk.set_appearance_mode(self.resolved_mode)
        self._notify()

    def apply_mode(self, mode: str) -> None:
        """Like :meth:`set_mode` but always reapplies even if unchanged."""
        if mode not in ("system", "light", "dark"):
            mode = "system"
        self._mode = mode
        ctk.set_appearance_mode(self.resolved_mode)
        self._notify()

    # -- listeners -----------------------------------------------------------

    def register(self, listener: Callable[[], None]) -> None:
        if listener not in self._listeners:
            self._listeners.append(listener)

    def unregister(self, listener: Callable[[], None]) -> None:
        try:
            self._listeners.remove(listener)
        except ValueError:
            pass

    def _notify(self) -> None:
        for listener in list(self._listeners):
            try:
                listener()
            except Exception:
                # A failing listener must never break the others.
                pass


# The shared singleton.  Import this from anywhere.
theme = ThemeManager()


# ---------------------------------------------------------------------------
# System detection
# ---------------------------------------------------------------------------


def _detect_system_mode() -> str:
    """Return ``dark`` or ``light`` based on the OS setting (best effort)."""
    try:
        import darkdetect  # type: ignore
        detected = darkdetect.theme()
        if detected and detected.lower() == "dark":
            return "dark"
        return "light"
    except Exception:
        return "light"


# ---------------------------------------------------------------------------
# Font helpers
# ---------------------------------------------------------------------------


def _font(size: int = 13, weight: str = "normal", family: Optional[str] = None) -> ctk.CTkFont:
    return ctk.CTkFont(family=family or FONT_FAMILY, size=size, weight=weight)


def font(size: int = 13, weight: str = "normal") -> ctk.CTkFont:
    return _font(size, weight)


def title_font(size: int = 20, weight: str = "bold") -> ctk.CTkFont:
    return _font(size, weight)


def heading_font(size: int = 14, weight: str = "bold") -> ctk.CTkFont:
    return _font(size, weight)


def mono_font(size: int = 10) -> ctk.CTkFont:
    return ctk.CTkFont(family=FONT_MONO, size=size)


# ---------------------------------------------------------------------------
# Component helpers — build consistently styled widgets from the palette
# ---------------------------------------------------------------------------


def card(parent, palette: Optional[Palette] = None, **kwargs) -> ctk.CTkFrame:
    """A raised surface card."""
    p = palette or theme.palette
    kwargs.setdefault("fg_color", p.bg_surface)
    kwargs.setdefault("corner_radius", RADIUS_LG)
    kwargs.setdefault("border_width", 1)
    kwargs.setdefault("border_color", p.border)
    return ctk.CTkFrame(parent, **kwargs)


def section_title(parent, text: str = "", palette: Optional[Palette] = None,
                  **kwargs) -> ctk.CTkLabel:
    p = palette or theme.palette
    kwargs.setdefault("text", text)
    kwargs.setdefault("text_color", p.text_primary)
    kwargs.setdefault("font", heading_font())
    return ctk.CTkLabel(parent, **kwargs)


def field_label(parent, text: str = "", palette: Optional[Palette] = None,
                **kwargs) -> ctk.CTkLabel:
    p = palette or theme.palette
    kwargs.setdefault("text", text)
    kwargs.setdefault("text_color", p.text_secondary)
    return ctk.CTkLabel(parent, **kwargs)


def help_text(parent, text: str = "", palette: Optional[Palette] = None,
              **kwargs) -> ctk.CTkLabel:
    p = palette or theme.palette
    kwargs.setdefault("text", text)
    kwargs.setdefault("text_color", p.text_muted)
    kwargs.setdefault("font", _font(10))
    return ctk.CTkLabel(parent, **kwargs)


def primary_button(parent, palette: Optional[Palette] = None, **kwargs) -> ctk.CTkButton:
    p = palette or theme.palette
    kwargs.setdefault("fg_color", p.accent)
    kwargs.setdefault("hover_color", p.accent_hover)
    kwargs.setdefault("text_color", p.accent_text)
    kwargs.setdefault("corner_radius", RADIUS_MD)
    return ctk.CTkButton(parent, **kwargs)


def secondary_button(parent, palette: Optional[Palette] = None, **kwargs) -> ctk.CTkButton:
    p = palette or theme.palette
    kwargs.setdefault("fg_color", "transparent")
    kwargs.setdefault("hover_color", p.hover)
    kwargs.setdefault("text_color", p.text_primary)
    kwargs.setdefault("border_width", 1)
    kwargs.setdefault("border_color", p.border)
    kwargs.setdefault("corner_radius", RADIUS_MD)
    return ctk.CTkButton(parent, **kwargs)


def danger_button(parent, palette: Optional[Palette] = None, **kwargs) -> ctk.CTkButton:
    p = palette or theme.palette
    kwargs.setdefault("fg_color", "transparent")
    kwargs.setdefault("hover_color", p.danger_dark)
    kwargs.setdefault("text_color", p.danger)
    kwargs.setdefault("border_width", 1)
    kwargs.setdefault("border_color", p.danger)
    kwargs.setdefault("corner_radius", RADIUS_MD)
    return ctk.CTkButton(parent, **kwargs)


def elevated_button(parent, palette: Optional[Palette] = None, **kwargs) -> ctk.CTkButton:
    p = palette or theme.palette
    kwargs.setdefault("fg_color", p.bg_elevated)
    kwargs.setdefault("hover_color", p.hover)
    kwargs.setdefault("text_color", p.text_primary)
    kwargs.setdefault("corner_radius", RADIUS_MD)
    return ctk.CTkButton(parent, **kwargs)


def stat_card(parent, title: str, value: str, color: str,
              palette: Optional[Palette] = None, **grid_kwargs) -> ctk.CTkLabel:
    """A small KPI tile.  Returns the value label so callers can update it."""
    p = palette or theme.palette
    frame = ctk.CTkFrame(parent, fg_color=p.bg_surface, corner_radius=RADIUS_MD,
                         border_width=1, border_color=p.border)
    if grid_kwargs:
        frame.grid(**grid_kwargs)
    else:
        frame.pack(side="left", fill="both", expand=True, padx=PAD_XS)
    ctk.CTkLabel(frame, text=title, text_color=p.text_muted,
                 font=_font(10)).pack(anchor="w", padx=PAD_MD, pady=(PAD_MD, 0))
    value_label = ctk.CTkLabel(frame, text=value, text_color=color,
                               font=_font(20, "bold"))
    value_label.pack(anchor="w", padx=PAD_MD, pady=(PAD_XS, PAD_MD))
    return value_label


def status_dot(parent, color: str, palette: Optional[Palette] = None,
               **kwargs) -> ctk.CTkLabel:
    kwargs.setdefault("text", "●")
    kwargs.setdefault("text_color", color)
    kwargs.setdefault("font", _font(15))
    return ctk.CTkLabel(parent, **kwargs)
