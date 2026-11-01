"""Behavioral coverage for neutral installs, migration and quiet UI state."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from unittest.mock import Mock, patch
from PySide6.QtWidgets import QApplication
from server.config import AppProfile, TabletConfig
from server.gui.header_bar import HeaderBar
from server.gui.support_panel import SupportPanel

app = QApplication.instance() or QApplication([])


def test_fresh_and_legacy_configurations_never_seed_app_profiles():
    for cfg in (TabletConfig(), TabletConfig.from_dict({}), TabletConfig.from_dict({'profiles': {}})):
        assert list(cfg.profiles) == ['Default']
        assert cfg.profiles['Default'].app_matches == []
        assert not cfg.auto_switch_profiles
        assert cfg.find_profile_for_app('krita', 'Krita').name == 'Default'
        assert list(TabletConfig.from_dict(cfg.to_dict()).profiles) == ['Default']
    legacy = TabletConfig.from_dict({'click_on_touch': False, 'stroke_smoothing': .3})
    assert not legacy.profiles['Default'].click_on_touch
    assert legacy.profiles['Default'].stroke_smoothing == .3


def test_existing_app_profiles_and_rules_survive_round_trip():
    cfg = TabletConfig(auto_switch_profiles=True)
    cfg.profiles['Krita'] = AppProfile(name='Krita', app_matches=['my-custom-rule'], pressure_gamma=.7)
    cfg.active_profile_name = 'Krita'
    saved = cfg.to_dict()
    for _ in range(2):
        cfg = TabletConfig.from_dict(saved)
        assert cfg.profiles['Krita'].app_matches == ['my-custom-rule']
        assert cfg.profiles['Krita'].pressure_gamma == .7
        assert cfg.active_profile_name == 'Krita'
        assert cfg.auto_switch_profiles
        saved = cfg.to_dict()
    del cfg.profiles['Krita']
    cfg.active_profile_name = 'Default'
    assert list(TabletConfig.from_dict(cfg.to_dict()).profiles) == ['Default']


def test_save_feedback_and_button_follow_dirty_state():
    header = HeaderBar()
    assert not header.btn_save_config.isEnabled()
    header.set_dirty(True)
    assert header.btn_save_config.isEnabled()
    assert header.save_feedback.text() == 'Unsaved changes'
    header.set_dirty(False)
    assert not header.btn_save_config.isEnabled()
    assert header.save_feedback.text() == 'Settings saved'
    header.deleteLater()


def test_support_export_is_explicit_previewed_and_allowlisted():
    cfg = TabletConfig()
    cfg.host = 'sensitive-host.example'
    cfg.profiles['Private app name'] = AppProfile(name='Private app name')
    panel = SupportPanel(cfg)
    assert not panel.is_expanded
    with patch.object(QApplication.clipboard(), 'setText') as copy:
        panel.refresh_report(cfg)
        copy.assert_not_called()
        panel.copy_report(cfg)
        text = copy.call_args.args[0]
        assert text == panel.report.text()
        assert cfg.host not in text
        assert 'Private app name' not in text
    panel.deleteLater()


def test_support_can_be_opened_and_exported_with_keyboard():
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    panel = SupportPanel(TabletConfig())
    panel.show()
    app.processEvents()
    try:
        panel._header.setFocus()
        QTest.keyClick(panel._header, Qt.Key_Space)
        assert panel.is_expanded
        QTest.keyClick(panel._header, Qt.Key_Tab)
        assert panel.copy_button.hasFocus()
        with patch.object(QApplication.clipboard(), 'setText') as copy:
            QTest.keyClick(panel.copy_button, Qt.Key_Space)
            copy.assert_called_once_with(panel.report.text())
    finally:
        panel.close()
        panel.deleteLater()
        app.processEvents()
