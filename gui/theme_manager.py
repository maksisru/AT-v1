"""Centralized color theme registry for GUI widgets."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict


@dataclass(frozen=True)
class Theme:
    """Named palette used by widgets instead of hard-coded colors."""

    name: str
    background: str
    surface: str
    text: str
    muted_text: str
    accent: str
    positive: str
    negative: str
    border: str


class ThemeManager:
    """Stores Dark, Light, and Classic palettes and exposes the active theme."""

    THEMES: Dict[str, Theme] = {
        "Dark": Theme("Dark", "#101419", "#18212b", "#f2f5f8", "#9aa7b2", "#4ea1ff", "#27c46b", "#ff5c5c", "#2c3947"),
        "Light": Theme("Light", "#f7f9fc", "#ffffff", "#17202a", "#667085", "#2368d8", "#0f9f5f", "#d92d20", "#d0d5dd"),
        "Classic": Theme("Classic", "#202020", "#2b2b2b", "#e8e0c8", "#b8ad8a", "#c7a23a", "#7fb069", "#c65d4b", "#4a4334"),
    }

    def __init__(self, active: str = "Dark") -> None:
        self.active_name = active if active in self.THEMES else "Dark"

    @property
    def active(self) -> Theme:
        """Return active palette."""
        return self.THEMES[self.active_name]

    def set_theme(self, name: str) -> Theme:
        """Activate an existing theme and return it."""
        if name not in self.THEMES:
            raise ValueError(f"Unknown theme: {name}")
        self.active_name = name
        return self.active
