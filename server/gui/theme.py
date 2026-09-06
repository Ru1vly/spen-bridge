"""
Central style tokens and stylesheet for the S Pen on Linux desktop GUI.
Dark, Catppuccin-Mocha-inspired palette, styled as soft/neumorphic UI: cards
and controls sit at the same tone as their background and get their depth
from a light/dark bevel pair instead of flat borders — raised for resting
controls, inverted (inset) for anything "pressed", active, or selected.
Every widget module should size/space things using the constants here rather
than hard-coding new magic numbers.
"""

from PySide6.QtGui import QColor
from PySide6.QtWidgets import QGraphicsDropShadowEffect

PALETTE = {
    "bg": "#1e1e2e",
    "panel": "#181825",
    "border": "#313244",
    "text": "#cdd6f4",
    "text_muted": "#a6adc8",
    "accent_blue": "#89b4fa",
    "accent_blue_hover": "#b4befe",
    "green": "#a6e3a1",
    "red": "#f38ba8",
    "orange": "#fab387",
    "purple": "#cba6f7",
    "surface2": "#313244",
    "surface3": "#45475a",
    "surface4": "#585b70",
    # Neumorphic bevel edges: a translucent white/black pair layered on top
    # of whatever the surface color already is, so the same two tokens give
    # every surface (bg, panel, or a colored button fill) a consistent
    # raised/inset edge without needing a bespoke light/dark shade per color.
    "bevel_light": "rgba(255, 255, 255, 40)",
    "bevel_dark": "rgba(0, 0, 0, 115)",
    "inset_bg": "#11111b",
}

# Spacing scale (px) used for margins/gaps across every panel/section.
SPACING = {"XS": 4, "SM": 8, "MD": 16, "LG": 24}

CARD_RADIUS = 18
CONTROL_RADIUS = 12
CONTROL_MIN_HEIGHT = 28
CONTROL_H_PADDING = 8

# objectNames that opt OUT of the automatic card elevation sweep (see
# apply_elevation) because they are nested inside an already-elevated card —
# stacking a second soft shadow there just muddies the edge instead of
# reading as "more raised".
_NO_SHADOW_OBJECT_NAMES = {"CollapsibleBox"}

# Class names that opt out because their contents repaint continuously
# (a 30Hz diagnostics timer, or live pen-stroke drawing). A
# QGraphicsDropShadowEffect makes Qt re-rasterize the whole blurred subtree
# on every single repaint of any child inside it — fine for a card that only
# changes on user interaction, but on these it turns every frame of a 30Hz
# update (or every point of a pen stroke) into a full soft-shadow re-blur,
# which reads as dropped frames / input lag rather than depth.
_NO_SHADOW_CLASS_NAMES = {"DiagnosticsCard", "PressureSection", "ScratchpadPanel"}


def _raised_border(p, width=1):
    return (
        f"border-top: {width}px solid {p['bevel_light']};"
        f"border-left: {width}px solid {p['bevel_light']};"
        f"border-bottom: {width}px solid {p['bevel_dark']};"
        f"border-right: {width}px solid {p['bevel_dark']};"
    )


def _inset_border(p, width=1):
    return (
        f"border-top: {width}px solid {p['bevel_dark']};"
        f"border-left: {width}px solid {p['bevel_dark']};"
        f"border-bottom: {width}px solid {p['bevel_light']};"
        f"border-right: {width}px solid {p['bevel_light']};"
    )


def apply_elevation(widget, blur=36, y_offset=10, alpha=100):
    """Give a top-level card a soft ambient drop shadow (the part QSS alone
    can't do) to pair with its QSS bevel border. Skip widgets whose
    objectName is in _NO_SHADOW_OBJECT_NAMES (nested cards)."""
    if widget.objectName() in _NO_SHADOW_OBJECT_NAMES:
        return
    effect = QGraphicsDropShadowEffect(widget)
    effect.setBlurRadius(blur)
    effect.setOffset(0, y_offset)
    effect.setColor(QColor(0, 0, 0, alpha))
    widget.setGraphicsEffect(effect)


def apply_elevation_to_cards(root):
    """Walk the widget tree once (called from MainWindow after the UI is
    built) and elevate every card-like container, instead of every card
    module wiring up its own shadow effect."""
    from PySide6.QtWidgets import QGroupBox, QFrame

    for gb in root.findChildren(QGroupBox):
        if type(gb).__name__ in _NO_SHADOW_CLASS_NAMES:
            continue
        apply_elevation(gb)
    for frame in root.findChildren(QFrame):
        if frame.objectName() == "HeaderBar":
            apply_elevation(frame, blur=28, y_offset=6, alpha=110)


def build_stylesheet() -> str:
    p = PALETTE
    raised = _raised_border(p)
    inset = _inset_border(p)
    return f"""
        QMainWindow, QWidget {{
            background-color: {p['bg']};
            color: {p['text']};
            font-family: 'Inter', 'Segoe UI', 'Ubuntu', sans-serif;
            font-size: 13px;
        }}
        QTabWidget::pane {{
            {inset}
            background: {p['panel']};
            border-radius: {CARD_RADIUS}px;
            top: -1px;
        }}
        QTabBar::tab {{
            background: transparent;
            color: {p['text_muted']};
            padding: 9px 18px;
            margin-right: 4px;
            border-top-left-radius: {CONTROL_RADIUS}px;
            border-top-right-radius: {CONTROL_RADIUS}px;
            font-weight: 500;
        }}
        QTabBar::tab:selected {{
            background: {p['panel']};
            color: {p['accent_blue']};
            border-top: 2px solid {p['accent_blue']};
            font-weight: 600;
        }}
        QTabBar::tab:hover:!selected {{
            background: rgba(255, 255, 255, 12);
            color: {p['text']};
        }}
        QGroupBox {{
            {raised}
            border-radius: {CARD_RADIUS}px;
            margin-top: 14px;
            padding: {SPACING['MD']}px;
            background-color: {p['bg']};
            font-weight: 600;
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            subcontrol-position: top left;
            padding: 0 6px;
            color: {p['accent_blue']};
            font-size: 14px;
            font-weight: 700;
        }}
        QGroupBox#CollapsibleBox {{
            margin-top: 0px;
            padding: 0px;
            border: none;
            background: transparent;
            border-radius: {CONTROL_RADIUS}px;
        }}
        QFrame#HeaderBar {{
            background: {p['panel']};
            {raised}
            border-radius: {CARD_RADIUS}px;
            padding: 6px;
        }}
        QWidget#CollapsibleBoxHeader {{
            border-radius: {CONTROL_RADIUS}px;
        }}
        QWidget#CollapsibleBoxHeader:hover {{
            background-color: rgba(255, 255, 255, 12);
        }}
        QPushButton {{
            background-color: {p['bg']};
            color: {p['text']};
            {raised}
            border-radius: {CONTROL_RADIUS}px;
            padding: 7px 14px;
            font-weight: 500;
            min-height: {CONTROL_MIN_HEIGHT}px;
        }}
        QPushButton:hover {{
            background-color: rgba(255, 255, 255, 10);
        }}
        QPushButton:pressed {{
            background-color: {p['panel']};
            {inset}
        }}
        QPushButton:checked {{
            background-color: {p['bg']};
            color: {p['accent_blue']};
            {inset}
            font-weight: 700;
        }}
        QPushButton:checked:hover {{
            color: {p['accent_blue_hover']};
        }}
        QPushButton:disabled {{
            color: #6c7086;
            background-color: {p['panel']};
            border: 1px solid {p['border']};
        }}
        QPushButton#primaryBtn {{
            background-color: {p['accent_blue']};
            color: #11111b;
            font-weight: 600;
            {raised}
        }}
        QPushButton#primaryBtn:hover {{
            background-color: {p['accent_blue_hover']};
        }}
        QPushButton#primaryBtn:pressed {{
            background-color: {p['accent_blue']};
            {inset}
        }}
        QPushButton#dangerBtn {{
            background-color: {p['red']};
            color: #11111b;
            font-weight: 600;
            {raised}
        }}
        QPushButton#dangerBtn:hover {{
            background-color: #eba0ac;
        }}
        QPushButton#dangerBtn:pressed {{
            background-color: {p['red']};
            {inset}
        }}
        QPushButton#successBtn {{
            background-color: {p['green']};
            color: #11111b;
            font-weight: 600;
            {raised}
        }}
        QPushButton#successBtn:hover {{
            background-color: #94e2d5;
        }}
        QPushButton#successBtn:pressed {{
            background-color: {p['green']};
            {inset}
        }}
        QToolButton {{
            background: transparent;
            border: none;
            border-radius: {CONTROL_RADIUS}px;
            color: {p['text_muted']};
        }}
        QToolButton:hover {{
            color: {p['text']};
            background-color: rgba(255, 255, 255, 10);
        }}
        QLineEdit, QComboBox, QSpinBox {{
            background-color: {p['inset_bg']};
            color: {p['text']};
            {inset}
            border-radius: {CONTROL_RADIUS}px;
            padding: 5px {CONTROL_H_PADDING}px;
            min-height: {CONTROL_MIN_HEIGHT}px;
        }}
        QLineEdit:focus, QComboBox:focus, QSpinBox:focus {{
            border: 1px solid {p['accent_blue']};
        }}
        QComboBox::drop-down {{
            border: none;
            width: 20px;
        }}
        QSlider::groove:horizontal {{
            {inset}
            height: 8px;
            background: {p['inset_bg']};
            border-radius: 4px;
        }}
        QSlider::sub-page:horizontal {{
            background: {p['accent_blue']};
            border-radius: 4px;
        }}
        QSlider::handle:horizontal {{
            background: {p['bg']};
            {raised}
            width: 18px;
            margin-top: -6px;
            margin-bottom: -6px;
            border-radius: 9px;
        }}
        QSlider::handle:horizontal:hover {{
            background: {p['surface3']};
        }}
        QProgressBar {{
            {inset}
            border-radius: 8px;
            text-align: center;
            background-color: {p['inset_bg']};
            color: {p['text']};
            font-size: 11px;
            height: 16px;
        }}
        QProgressBar::chunk {{
            background-color: {p['accent_blue']};
            border-radius: 7px;
        }}
        QCheckBox {{
            spacing: 8px;
        }}
        QCheckBox::indicator {{
            width: 16px;
            height: 16px;
            border-radius: 5px;
            {inset}
            background-color: {p['inset_bg']};
        }}
        QCheckBox::indicator:checked {{
            background-color: {p['accent_blue']};
            border-color: {p['accent_blue']};
        }}
        QRadioButton {{
            spacing: 8px;
        }}
        QRadioButton::indicator {{
            width: 16px;
            height: 16px;
            border-radius: 8px;
            {inset}
            background-color: {p['inset_bg']};
        }}
        QRadioButton::indicator:checked {{
            background-color: {p['accent_blue']};
            border-color: {p['accent_blue']};
        }}
        QTextEdit {{
            background-color: {p['inset_bg']};
            {inset}
            border-radius: {CONTROL_RADIUS}px;
            color: {p['text_muted']};
            font-family: 'JetBrains Mono', 'Fira Code', 'Monospace';
            font-size: 11px;
        }}
        QListWidget {{
            background-color: {p['panel']};
            border: none;
            border-radius: {CONTROL_RADIUS + 2}px;
            color: {p['text']};
            padding: 6px;
        }}
        QListWidget::item {{
            padding: 0px;
            border-radius: {CONTROL_RADIUS}px;
            margin-bottom: 4px;
        }}
        QListWidget::item:selected {{
            background-color: {p['bg']};
            {inset}
        }}
        QListWidget::item:hover:!selected {{
            background-color: rgba(255, 255, 255, 10);
        }}
        QScrollArea {{
            border: none;
            background: transparent;
        }}
        QLabel[pillState="ok"] {{
            background-color: {p['bg']};
            color: {p['green']};
            font-weight: bold;
            padding: 3px 10px;
            border-radius: 10px;
            font-size: 11px;
            {inset}
        }}
        QLabel[pillState="bad"] {{
            background-color: {p['bg']};
            color: {p['red']};
            font-weight: bold;
            padding: 3px 10px;
            border-radius: 10px;
            font-size: 11px;
            {inset}
        }}
        QLabel[pillState="warn"] {{
            background-color: {p['bg']};
            color: {p['orange']};
            font-weight: bold;
            padding: 3px 10px;
            border-radius: 10px;
            font-size: 11px;
            {inset}
        }}
        QLabel[pillState="idle"] {{
            background-color: {p['bg']};
            color: #6c7086;
            padding: 3px 10px;
            border-radius: 10px;
            font-size: 11px;
            {inset}
        }}
        QLabel[pillState="customized"] {{
            background-color: {p['bg']};
            color: {p['purple']};
            font-weight: bold;
            padding: 2px 8px;
            border-radius: 9px;
            font-size: 10px;
            {inset}
        }}
        QWidget#MatchChip {{
            background-color: {p['bg']};
            {raised}
            border-radius: 11px;
        }}
        QWidget#MatchChip[activeMatch="true"] {{
            border: 1px solid {p['green']};
        }}
    """
