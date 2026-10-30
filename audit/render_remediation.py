"""Render changed Qt interfaces without starting network or native input devices."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
import sys
from unittest.mock import Mock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFont
from server.config import TabletConfig
from server.gui.main_window import MainWindow

app = QApplication.instance() or QApplication([])
config = TabletConfig(auto_start_server=False, auto_adb_forward=False, minimize_to_tray=False)
config.recovery_notice = 'Recovered settings from the last valid backup. Review and save to replace the damaged config.'
output = Path(__file__).parent / 'evidence'
tag = os.environ.get('SPEN_RENDER_TAG', '')
with patch('server.gui.main_window.load_config', return_value=config), \
     patch('server.gui.main_window.WindowWatcher.start'), \
     patch('server.gui.main_window.GuiState', return_value=Mock(last_tab_index=0, last_editing_profile='Default')):
    window = MainWindow()
    window.show()
    for width, height, points in [(960, 640, 10), (760, 540, 10), (960, 720, 16)]:
        app.setFont(QFont(app.font().family(), points))
        window.resize(width, height)
        for tab in range(2):
            window.tabs.setCurrentIndex(tab)
            app.processEvents()
            window.grab().save(str(output / f'remediation-qt{tag}-{width}-{points}-tab{tab}.png'))
        print(width, height, points, window.size().toTuple())
    window._dirty = False
    window.diag_timer.stop()
    window.worker.shutdown()
    window.hide()
