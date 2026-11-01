"""Native desktop layout matrix; mocks device startup and user preference writes."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
import sys
from unittest.mock import Mock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication, QScrollArea
from server.config import TabletConfig
from server.gui.main_window import MainWindow
from server.gui import theme
from server.gui.dialogs import NewProfileDialog, DuplicateProfileDialog

app = QApplication.instance() or QApplication([])
out = Path(__file__).parent / 'evidence' / 'ui-ux-fixes'
out.mkdir(parents=True, exist_ok=True)
configure = theme.configure
for dark in (False, True):
    scheme = 'dark' if dark else 'light'
    for width, height, points in ((1200, 900, 11), (760, 700, 11), (960, 800, 16)):
        app.setFont(QFont(app.font().family(), points))
        config = TabletConfig(auto_start_server=False, auto_adb_forward=False, minimize_to_tray=False)
        with patch('server.gui.main_window.load_config', return_value=config), \
             patch('server.gui.main_window.WindowWatcher.start'), \
             patch('server.gui.main_window.GuiState', return_value=Mock(last_tab_index=0, last_editing_profile='Default')), \
             patch('server.gui.main_window.theme.configure', side_effect=lambda _: configure(dark)):
            window = MainWindow()
            window.resize(width, height)
            window.show()
            app.processEvents()
            assert window.system_tab.connection_panel.lbl_hint.font().pointSizeF() == points
            for index, name in ((0, 'connection'), (1, 'pen'), (2, 'profiles'), (3, 'preferences')):
                window.tabs.setCurrentIndex(index)
                app.processEvents()
                if name == 'connection':
                    assert window.system_tab.scroll.horizontalScrollBar().maximum() == 0, (width, points, 'connection overflow')
                window.grab().save(str(out / f'desktop-{scheme}-{width}-{points}-{name}.png'))
                assert window.width() == width, (name, window.size().toTuple())
            window.tabs.setCurrentIndex(1)
            for index, name in enumerate(('pressure', 'mapping', 'buttons', 'device')):
                editor = window.profiles_tab.editor_panel
                editor.categories.setCurrentIndex(index)
                if name == 'mapping':
                    editor.mapping_section.advanced_box.set_expanded(True)
                app.processEvents()
                scroll = editor.category_scrolls[name.title()]
                assert scroll.horizontalScrollBar().maximum() == 0, (width, points, name)
                window.grab().save(str(out / f'desktop-{scheme}-{width}-{points}-{name}.png'))
                if name == 'mapping':
                    scroll.verticalScrollBar().setValue(scroll.verticalScrollBar().maximum())
                    app.processEvents()
                    window.grab().save(str(out / f'desktop-{scheme}-{width}-{points}-bounds.png'))
            if width == 1200:
                window.profiles_tab.select_profile('Default')
                window.tabs.setCurrentIndex(2)
                app.processEvents()
                window.grab().save(str(out / f'desktop-{scheme}-app-matching.png'))
                for dialog, name in ((NewProfileDialog(config.profiles, window), 'new-profile'),
                                     (DuplicateProfileDialog('Default', window), 'duplicate-profile')):
                    dialog.show()
                    app.processEvents()
                    dialog.grab().save(str(out / f'desktop-{scheme}-{name}.png'))
                    dialog.reject()
            print(scheme, width, points, 'all workspaces and pen categories fit')
            window.diag_timer.stop()
            window.system_tab.connection_panel.stop_usb_monitor()
            window.worker.shutdown()
            window.tray.tray_icon.hide()
            window.hide()
            window.deleteLater()
            app.processEvents()
