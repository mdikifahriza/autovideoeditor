from __future__ import annotations

from PySide6.QtWidgets import QWidget


def repolish(widget: QWidget | None) -> QWidget | None:
    if widget is None:
        return None
    style = widget.style()
    if style is not None:
        style.unpolish(widget)
        style.polish(widget)
    widget.update()
    return widget


def set_widget_props(widget: QWidget, **props) -> QWidget:
    for key, value in props.items():
        widget.setProperty(key, value)
    return repolish(widget) or widget
