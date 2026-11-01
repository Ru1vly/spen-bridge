"""One UI visual roles for the native Qt adaptation.

Samsung publishes design guidance, not a Qt SDK. These tokens implement that
language with native controls; they are shared by QSS and the painted widgets.
"""
from pathlib import Path

LIGHT = {
    "bg": "#f2f2f2", "panel": "#ffffff", "border": "#d7d9de",
    "text": "#17171b", "text_muted": "#565b65", "accent_blue": "#165dce",
    "accent_blue_hover": "#104da9", "green": "#187447", "red": "#b3261e",
    "orange": "#8b5100", "purple": "#6944b5", "surface2": "#e8e9ed",
    "surface3": "#d5d8df", "surface4": "#747984", "inset_bg": "#f7f7f9",
    "selection": "#e5edfc", "on_accent": "#ffffff", "disabled": "#787c85",
}
DARK = {
    "bg": "#010101", "panel": "#171719", "border": "#3c3c41",
    "text": "#f5f5f7", "text_muted": "#b1b3bc", "accent_blue": "#8ab4ff",
    "accent_blue_hover": "#aecbff", "green": "#81d5a6", "red": "#ffb4ab",
    "orange": "#ffcb8a", "purple": "#d0b5ff", "surface2": "#29292d",
    "surface3": "#414149", "surface4": "#90909b", "inset_bg": "#222225",
    "selection": "#203452", "on_accent": "#092653", "disabled": "#92929c",
}
PALETTE = dict(LIGHT)
SPACING = {"XS": 4, "SM": 8, "MD": 16, "LG": 24}
CARD_RADIUS = 24
CONTROL_RADIUS = 16
CONTROL_MIN_HEIGHT = 28
CONTROL_H_PADDING = 12


def configure(dark=False):
    """Select roles before constructing widgets, retaining imported references."""
    PALETTE.clear()
    PALETTE.update(DARK if dark else LIGHT)


def apply_elevation_to_cards(root):
    """One UI groups use tonal separation, without expensive subtree shadows."""
    return


def build_stylesheet() -> str:
    p = PALETTE
    assets = Path(__file__).parent / "assets"
    dark = p["bg"] == DARK["bg"]
    check = (assets / ("check-dark.svg" if dark else "check.svg")).as_posix()
    down = (assets / ("down-dark.svg" if dark else "down-light.svg")).as_posix()
    up = (assets / ("up-dark.svg" if dark else "up-light.svg")).as_posix()
    return f"""
        QMainWindow, QDialog, QWidget {{
            background-color: {p['bg']}; color: {p['text']};
            font-family: 'SamsungOne', 'SamsungOne UI', 'Segoe UI', 'Noto Sans', sans-serif;
        }}
        QLabel {{ background: transparent; }}
        QLabel#pageTitle {{ font-size: 26px; font-weight: 700; }}
        QLabel#workspaceTitle {{ font-size: 23px; font-weight: 600; margin-bottom: 8px; }}
        QListWidget#workspaceList {{ background: transparent; padding: 0; }}
        QListWidget#workspaceList::item {{ padding: 10px 14px; margin-bottom: 8px; }}
        QLabel#supportingText {{ color: {p['text_muted']}; }}
        QFrame#HeaderBar {{ background: transparent; border: none; }}
        QTabWidget::pane {{ border: none; background: {p['bg']}; }}
        QTabBar::tab {{
            background: transparent; color: {p['text_muted']};
            padding: 12px 22px; margin: 0 8px 8px 0; border-radius: 18px;
            font-weight: 600;
        }}
        QTabBar::tab:selected {{ background: {p['selection']}; color: {p['accent_blue']}; }}
        QTabBar::tab:hover:!selected {{ background: {p['surface2']}; }}
        QGroupBox {{
            border: none; border-radius: {CARD_RADIUS}px; margin-top: 28px;
            padding: 20px 16px 16px 16px; background: {p['panel']};
        }}
        QGroupBox::title {{
            subcontrol-origin: margin; subcontrol-position: top left;
            left: 16px; padding: 0 0 8px 0; color: {p['text_muted']}; font-weight: 600;
        }}
        QGroupBox#CollapsibleBox {{ margin: 0; padding: 0; border: none; background: transparent; }}
        QPushButton {{
            background: {p['surface2']}; color: {p['text']};
            border: 2px solid transparent; border-radius: {CONTROL_RADIUS}px;
            padding: 6px 14px; min-height: {CONTROL_MIN_HEIGHT}px; font-weight: 600;
        }}
        QPushButton:hover {{ background: {p['surface3']}; }}
        QPushButton:pressed {{ background: {p['selection']}; color: {p['accent_blue']}; }}
        QPushButton:checked {{ background: {p['selection']}; color: {p['accent_blue']}; }}
        QPushButton:disabled {{ color: {p['disabled']}; background: {p['surface2']}; }}
        QPushButton#primaryBtn, QPushButton#successBtn {{
            background: {p['accent_blue']}; color: {p['on_accent']};
        }}
        QPushButton#primaryBtn:hover, QPushButton#successBtn:hover {{ background: {p['accent_blue_hover']}; }}
        QPushButton#dangerBtn {{ background: {p['panel']}; color: {p['red']}; border-color: {p['border']}; }}
        QPushButton#dangerBtn:disabled, QPushButton#primaryBtn:disabled, QPushButton#successBtn:disabled {{ color: {p['disabled']}; background: {p['surface2']}; border-color: {p['border']}; }}
        QPushButton#dangerBtn:hover {{ border-color: {p['red']}; }}
        QPushButton:focus, QToolButton:focus {{ border: 2px solid {p['accent_blue']}; }}
        QPushButton#CollapsibleBoxHeader {{ background: {p['inset_bg']}; text-align: left; }}
        QToolButton {{ background: transparent; color: {p['text_muted']}; border: 2px solid transparent; border-radius: 10px; padding: 4px; }}
        QToolButton:hover {{ background: {p['surface2']}; }}
        QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {{
            background: {p['inset_bg']}; color: {p['text']}; border: 1px solid {p['border']};
            border-radius: 12px; padding: 8px {CONTROL_H_PADDING}px;
            min-height: {CONTROL_MIN_HEIGHT}px; selection-background-color: {p['selection']};
            selection-color: {p['text']};
        }}
        QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {{ border: 1px solid {p['accent_blue']}; }}
        QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled {{ color: {p['disabled']}; }}
        QComboBox::drop-down {{ border: none; width: 24px; }}
        QComboBox::down-arrow {{ image: url({down}); width: 20px; height: 20px; }}
        QSpinBox::up-button, QDoubleSpinBox::up-button {{ subcontrol-origin: border; subcontrol-position: top right; width: 26px; border: none; }}
        QSpinBox::down-button, QDoubleSpinBox::down-button {{ subcontrol-origin: border; subcontrol-position: bottom right; width: 26px; border: none; }}
        QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{ image: url({up}); width: 14px; height: 14px; }}
        QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{ image: url({down}); width: 14px; height: 14px; }}
        QComboBox QAbstractItemView {{ background: {p['panel']}; color: {p['text']}; selection-background-color: {p['selection']}; selection-color: {p['accent_blue']}; border: 1px solid {p['border']}; padding: 8px; }}
        QSlider {{ background: transparent; }}
        QSlider::groove:horizontal {{ height: 6px; background: {p['surface3']}; border-radius: 3px; }}
        QSlider::sub-page:horizontal {{ background: {p['accent_blue']}; border-radius: 3px; }}
        QSlider::handle:horizontal {{ background: {p['accent_blue']}; width: 20px; margin: -7px 0; border-radius: 10px; }}
        QSlider::handle:horizontal:focus {{ border: 2px solid {p['text']}; }}
        QProgressBar {{ border: none; border-radius: 6px; text-align: center; background: {p['surface2']}; color: {p['text']}; min-height: 12px; }}
        QProgressBar::chunk {{ background: {p['accent_blue']}; border-radius: 6px; }}
        QCheckBox, QRadioButton {{ spacing: 10px; padding: 4px 0; background: transparent; }}
        QCheckBox::indicator, QRadioButton::indicator {{ width: 20px; height: 20px; border: 2px solid {p['surface4']}; background: {p['panel']}; border-radius: 6px; }}
        QRadioButton::indicator {{ border-radius: 12px; }}
        QCheckBox::indicator:checked {{ background: {p['accent_blue']}; border-color: {p['accent_blue']}; image: url({check}); }}
        QRadioButton::indicator:checked {{ border: 6px solid {p['accent_blue']}; width: 12px; height: 12px; background: {p['panel']}; }}
        QCheckBox:focus, QRadioButton:focus {{ color: {p['accent_blue']}; }}
        QTextEdit, QPlainTextEdit {{ background: {p['inset_bg']}; color: {p['text_muted']}; border: 1px solid {p['border']}; border-radius: 12px; padding: 8px; font-family: 'Cascadia Mono', 'DejaVu Sans Mono', monospace; }}
        QListWidget {{ background: {p['panel']}; border: none; border-radius: 20px; padding: 8px; outline: none; }}
        QListWidget::item {{ padding: 2px; border: 2px solid transparent; border-radius: 12px; margin: 2px 0; }}
        QListWidget::item:selected {{ background: {p['selection']}; color: {p['accent_blue']}; }}
        QListWidget::item:focus {{ border-color: {p['accent_blue']}; }}
        QListWidget::item:hover:!selected {{ background: {p['inset_bg']}; }}
        QScrollArea {{ border: none; background: transparent; }}
        QScrollBar:vertical {{ background: transparent; width: 10px; margin: 0; }}
        QScrollBar::handle:vertical {{ background: {p['surface4']}; min-height: 28px; border-radius: 4px; margin: 2px; }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}
        QScrollBar:horizontal {{ background: transparent; height: 10px; }}
        QScrollBar::handle:horizontal {{ background: {p['surface4']}; min-width: 28px; border-radius: 4px; }}
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
        QSplitter::handle {{ background: transparent; width: 16px; }}
        QMenu {{ background: {p['panel']}; color: {p['text']}; border: 1px solid {p['border']}; padding: 8px; }}
        QMenu::item {{ padding: 8px 24px; border-radius: 8px; }}
        QMenu::item:selected {{ background: {p['selection']}; color: {p['accent_blue']}; }}
        QToolTip {{ background: {p['panel']}; color: {p['text']}; border: 1px solid {p['border']}; padding: 8px; }}
        QLabel[pillState] {{ background: {p['surface2']}; color: {p['text_muted']}; padding: 5px 10px; border-radius: 11px; font-weight: 600; }}
        QLabel[pillState="ok"] {{ color: {p['green']}; }}
        QLabel[pillState="bad"] {{ color: {p['red']}; }}
        QLabel[pillState="warn"] {{ color: {p['orange']}; }}
        QLabel[pillState="customized"] {{ color: {p['purple']}; }}
        QWidget#MatchChip {{ background: {p['surface2']}; border-radius: 12px; }}
        QWidget#MatchChip[activeMatch="true"] {{ border: 1px solid {p['green']}; }}
    """
