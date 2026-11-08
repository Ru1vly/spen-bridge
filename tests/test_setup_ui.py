"""Native setup controls expose LAN information and approval, not secret copying."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import unittest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication,QLineEdit
from server.config import TabletConfig
from server.gui.connection_panel import ConnectionPanel
from server.pairing import PairingRequest

app=QApplication.instance() or QApplication([])


class SetupUiTests(unittest.TestCase):
    def setUp(self):
        self.panel=ConnectionPanel('192.168.1.15',TabletConfig())
        self.panel.show();app.processEvents()
        self.addCleanup(self.cleanup)

    def cleanup(self):
        if self.panel._pair_dialog is not None:self.panel._pair_dialog.reject()
        self.panel.stop_usb_monitor();self.panel.hide();self.panel.deleteLater();app.processEvents()

    def test_wireless_address_is_independent_of_usb_listener(self):
        for host in ['127.0.0.1','0.0.0.0']:
            self.panel.set_listener((host,40118))
            self.assertEqual(self.panel.address(),'192.168.1.15:40118')
            self.assertEqual(self.panel.lbl_ip_info.text(),'Wireless address: 192.168.1.15:40118')
            self.panel._copy_connection_info();self.assertEqual(app.clipboard().text(),'192.168.1.15:40118')

    def test_unavailable_wifi_never_falls_back_to_usb_loopback(self):
        self.panel.set_listener(('127.0.0.1',40118))
        self.panel._set_network_address('')
        self.assertEqual(self.panel.address(),'')
        self.assertFalse(self.panel.btn_copy.isEnabled())
        self.assertIn('unavailable',self.panel.lbl_ip_info.text())
        self.assertNotIn('127.0.0.1',self.panel.lbl_ip_info.text())

    def test_pairing_requests_approval_and_never_displays_credentials(self):
        requests=[];decisions=[]
        self.panel.pairing_requested.connect(lambda:requests.append(True))
        self.panel.pairing_decision.connect(lambda token,approved:decisions.append((token,approved)))
        self.panel.show_pairing();self.panel.pairing_ready();app.processEvents()
        dialog=self.panel._pair_dialog
        self.assertEqual(requests,[True]);self.assertEqual(dialog.findChildren(QLineEdit),[])
        self.panel.show_pairing_request(PairingRequest('session','<b>My tablet</b>','192.168.1.2:5000','123456',60))
        self.assertEqual(dialog.heading.textFormat(),Qt.PlainText)
        self.assertEqual(dialog.number.text(),'123456')
        dialog.allow_button.click();self.assertEqual(decisions,[('session',True)])
        self.panel.pairing_finished(True,'Tablet paired.')
        self.assertFalse(dialog.number.isVisible());self.assertEqual(dialog.heading.text(),'Tablet paired')

    def test_closed_pairing_dialog_declines_late_request(self):
        decisions=[]
        self.panel.pairing_decision.connect(lambda token,approved:decisions.append((token,approved)))
        self.panel.show_pairing();self.panel._pair_dialog.reject()
        self.panel.show_pairing_request(PairingRequest('stale','My tablet','192.168.1.2:5000','123456',60))
        self.assertEqual(decisions,[('stale',False)])
