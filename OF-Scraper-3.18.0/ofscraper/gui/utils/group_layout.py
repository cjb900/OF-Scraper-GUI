"""Shared QGroupBox layout tuning for consistent section chrome."""

from __future__ import annotations

from PyQt6.QtWidgets import QGridLayout, QGroupBox, QLayout, QSizePolicy

# Match Content Areas / compact filter sections across the Areas page.
GROUP_MARGINS = (10, 8, 10, 8)
GROUP_SPACING = 6


def tune_group_layout(layout: QLayout) -> QLayout:
    """Apply uniform margins/spacing to a group box's layout."""
    layout.setContentsMargins(*GROUP_MARGINS)
    if isinstance(layout, QGridLayout):
        layout.setHorizontalSpacing(12)
        layout.setVerticalSpacing(GROUP_SPACING)
    else:
        layout.setSpacing(GROUP_SPACING)
    return layout


def compact_group(group: QGroupBox) -> QGroupBox:
    """Keep group boxes content-sized (no vertical stretch gaps)."""
    group.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
    return group
