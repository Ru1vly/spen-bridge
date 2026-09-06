"""Small modal dialogs for profile creation/duplication."""

from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QFormLayout,
    QLineEdit,
    QComboBox,
    QDialogButtonBox,
    QLabel,
)


class NewProfileDialog(QDialog):
    def __init__(self, existing_names, parent=None):
        super().__init__(parent)
        self.setWindowTitle("New Application Profile")
        self.profile_name = ""
        self.source_profile_name = "Default"

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self._edit_name = QLineEdit()
        self._edit_name.setPlaceholderText("e.g. Krita, Blender, Cyberpunk 2077")
        form.addRow("Profile name:", self._edit_name)

        self._combo_source = QComboBox()
        for name in existing_names:
            self._combo_source.addItem(name, name)
        idx = self._combo_source.findData("Default")
        if idx >= 0:
            self._combo_source.setCurrentIndex(idx)
        form.addRow("Duplicate settings from:", self._combo_source)

        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("Create")
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_accept(self):
        name = self._edit_name.text().strip()
        if not name:
            self._edit_name.setFocus()
            return
        self.profile_name = name
        self.source_profile_name = self._combo_source.currentData() or "Default"
        self.accept()


class DuplicateProfileDialog(QDialog):
    def __init__(self, current_name: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Duplicate Profile")
        self.new_name = ""

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"Duplicate '{current_name}' as:"))

        self._edit_name = QLineEdit(f"{current_name} copy")
        self._edit_name.selectAll()
        layout.addWidget(self._edit_name)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("Duplicate")
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_accept(self):
        name = self._edit_name.text().strip()
        if not name:
            self._edit_name.setFocus()
            return
        self.new_name = name
        self.accept()
