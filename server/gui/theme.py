"""
Central style tokens and stylesheet for the S Pen on Linux desktop GUI.
Dark, Catppuccin-Mocha-inspired palette. Every widget module should size/space
things using the constants here rather than hard-coding new magic numbers.
"""

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
}

# Spacing scale (px) used for margins/gaps across every panel/section.
SPACING = {"XS": 4, "SM": 8, "MD": 16, "LG": 24}

CARD_RADIUS = 8
CONTROL_MIN_HEIGHT = 28
CONTROL_H_PADDING = 8


def build_stylesheet() -> str:
    p = PALETTE
    return f"""
        QMainWindow, QWidget {{
            background-color: {p['bg']};
            color: {p['text']};
            font-family: 'Inter', 'Segoe UI', 'Ubuntu', sans-serif;
            font-size: 13px;
        }}
        QTabWidget::pane {{
            border: 1px solid {p['border']};
            background: {p['panel']};
            border-radius: {CARD_RADIUS}px;
            top: -1px;
        }}
        QTabBar::tab {{
            background: {p['bg']};
            color: {p['text_muted']};
            padding: 9px 18px;
            margin-right: 4px;
            border-top-left-radius: 6px;
            border-top-right-radius: 6px;
            font-weight: 500;
        }}
        QTabBar::tab:selected {{
            background: {p['panel']};
            color: {p['accent_blue']};
            border-top: 2px solid {p['accent_blue']};
            font-weight: 600;
        }}
        QTabBar::tab:hover:!selected {{
            background: #252538;
            color: {p['text']};
        }}
        QGroupBox {{
            border: 1px solid {p['border']};
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
        }}
        QFrame#HeaderBar {{
            background: {p['panel']};
            border: 1px solid {p['border']};
            border-radius: {CARD_RADIUS}px;
            padding: 4px;
        }}
        QWidget#CollapsibleBoxHeader:hover {{
            background-color: #232334;
            border-radius: 6px;
        }}
        QPushButton {{
            background-color: {p['surface2']};
            color: {p['text']};
            border: 1px solid {p['surface3']};
            border-radius: 6px;
            padding: 7px 14px;
            font-weight: 500;
            min-height: {CONTROL_MIN_HEIGHT}px;
        }}
        QPushButton:hover {{
            background-color: {p['surface3']};
            border-color: {p['surface4']};
        }}
        QPushButton:pressed {{
            background-color: {p['surface4']};
        }}
        QPushButton:checked {{
            background-color: {p['accent_blue']};
            color: #11111b;
            border: 1px solid {p['accent_blue']};
            font-weight: 700;
        }}
        QPushButton:checked:hover {{
            background-color: {p['accent_blue_hover']};
        }}
        QPushButton:disabled {{
            color: #6c7086;
            background-color: {p['panel']};
            border-color: {p['border']};
        }}
        QPushButton#primaryBtn {{
            background-color: {p['accent_blue']};
            color: #11111b;
            font-weight: 600;
            border: none;
        }}
        QPushButton#primaryBtn:hover {{
            background-color: {p['accent_blue_hover']};
        }}
        QPushButton#dangerBtn {{
            background-color: {p['red']};
            color: #11111b;
            font-weight: 600;
            border: none;
        }}
        QPushButton#dangerBtn:hover {{
            background-color: #eba0ac;
        }}
        QPushButton#successBtn {{
            background-color: {p['green']};
            color: #11111b;
            font-weight: 600;
            border: none;
        }}
        QPushButton#successBtn:hover {{
            background-color: #94e2d5;
        }}
        QToolButton {{
            background: transparent;
            border: none;
            color: {p['text_muted']};
        }}
        QToolButton:hover {{
            color: {p['text']};
        }}
        QLineEdit, QComboBox, QSpinBox {{
            background-color: #11111b;
            color: {p['text']};
            border: 1px solid {p['surface3']};
            border-radius: 5px;
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
            border: 1px solid {p['border']};
            height: 6px;
            background: #11111b;
            border-radius: 3px;
        }}
        QSlider::sub-page:horizontal {{
            background: {p['accent_blue']};
            border-radius: 3px;
        }}
        QSlider::handle:horizontal {{
            background: {p['text']};
            border: 1px solid {p['accent_blue']};
            width: 16px;
            margin-top: -5px;
            margin-bottom: -5px;
            border-radius: 8px;
        }}
        QSlider::handle:horizontal:hover {{
            background: #ffffff;
        }}
        QProgressBar {{
            border: 1px solid {p['border']};
            border-radius: 4px;
            text-align: center;
            background-color: #11111b;
            color: {p['text']};
            font-size: 11px;
            height: 16px;
        }}
        QProgressBar::chunk {{
            background-color: {p['accent_blue']};
            border-radius: 3px;
        }}
        QCheckBox {{
            spacing: 8px;
        }}
        QCheckBox::indicator {{
            width: 16px;
            height: 16px;
            border-radius: 4px;
            border: 1px solid {p['surface3']};
            background-color: #11111b;
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
            border: 1px solid {p['surface3']};
            background-color: #11111b;
        }}
        QRadioButton::indicator:checked {{
            background-color: {p['accent_blue']};
            border-color: {p['accent_blue']};
        }}
        QTextEdit {{
            background-color: #11111b;
            border: 1px solid {p['border']};
            border-radius: 6px;
            color: {p['text_muted']};
            font-family: 'JetBrains Mono', 'Fira Code', 'Monospace';
            font-size: 11px;
        }}
        QListWidget {{
            background-color: {p['panel']};
            border: none;
            border-radius: 6px;
            color: {p['text']};
            padding: 4px;
        }}
        QListWidget::item {{
            padding: 0px;
            border-radius: 4px;
            margin-bottom: 2px;
        }}
        QListWidget::item:selected {{
            background-color: {p['surface2']};
        }}
        QListWidget::item:hover:!selected {{
            background-color: #232334;
        }}
        QScrollArea {{
            border: none;
            background: transparent;
        }}
        QLabel[pillState="ok"] {{
            background-color: {p['surface2']};
            color: {p['green']};
            font-weight: bold;
            padding: 3px 8px;
            border-radius: 4px;
            font-size: 11px;
        }}
        QLabel[pillState="bad"] {{
            background-color: {p['surface2']};
            color: {p['red']};
            font-weight: bold;
            padding: 3px 8px;
            border-radius: 4px;
            font-size: 11px;
        }}
        QLabel[pillState="warn"] {{
            background-color: {p['surface2']};
            color: {p['orange']};
            font-weight: bold;
            padding: 3px 8px;
            border-radius: 4px;
            font-size: 11px;
        }}
        QLabel[pillState="idle"] {{
            background-color: {p['surface2']};
            color: #6c7086;
            padding: 3px 8px;
            border-radius: 4px;
            font-size: 11px;
        }}
        QLabel[pillState="customized"] {{
            background-color: {p['surface2']};
            color: {p['purple']};
            font-weight: bold;
            padding: 2px 6px;
            border-radius: 4px;
            font-size: 10px;
        }}
        QWidget#MatchChip {{
            background-color: {p['surface2']};
            border: 1px solid {p['border']};
            border-radius: 11px;
        }}
        QWidget#MatchChip[activeMatch="true"] {{
            border: 1px solid {p['green']};
        }}
    """
