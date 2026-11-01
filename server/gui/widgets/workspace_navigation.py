"""Native workspace navigation: a labelled rail, or tabs on compact windows."""
from PySide6.QtCore import Qt, Signal, QSignalBlocker, QSize
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem, QStackedWidget, QTabBar, QLabel


class WorkspaceNavigation(QWidget):
    currentChanged = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.compact_tabs = QTabBar()
        self.compact_tabs.setExpanding(False)
        self.compact_tabs.setUsesScrollButtons(True)
        self.compact_tabs.setAccessibleName("Workspaces")
        outer.addWidget(self.compact_tabs)
        body = QHBoxLayout()
        body.setSpacing(24)
        outer.addLayout(body, 1)
        self.rail = QWidget()
        self.rail.setObjectName("navigationRail")
        rail_layout = QVBoxLayout(self.rail)
        rail_layout.setContentsMargins(0, 0, 0, 0)
        rail_layout.setSpacing(16)
        self.list = QListWidget()
        self.list.setObjectName("workspaceList")
        self.list.setAccessibleName("Workspaces")
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        rail_layout.addWidget(self.list, 1)
        self.footer_layout = QVBoxLayout()
        rail_layout.addLayout(self.footer_layout)
        body.addWidget(self.rail)
        self.stack = QStackedWidget()
        body.addWidget(self.stack, 1)
        self.list.currentRowChanged.connect(self.setCurrentIndex)
        self.compact_tabs.currentChanged.connect(self.setCurrentIndex)
        self.stack.currentChanged.connect(self._changed)
        self._compact = None

    def addTab(self, page, label):
        index = self.stack.addWidget(page)
        item = QListWidgetItem(label)
        item.setSizeHint(QSize(160, self.list.fontMetrics().height() + 30))
        self.list.addItem(item)
        self.compact_tabs.addTab(label)
        if index == 0:
            self.setCurrentIndex(0)
        return index

    def setFooter(self, widget):
        self.footer_layout.addWidget(widget)

    def currentWidget(self):
        return self.stack.currentWidget()

    def currentIndex(self):
        return self.stack.currentIndex()

    def count(self):
        return self.stack.count()

    def tabText(self, index):
        return self.compact_tabs.tabText(index)

    def setCurrentIndex(self, index):
        if 0 <= index < self.stack.count():
            self.stack.setCurrentIndex(index)
            self._sync(index)

    def _sync(self, index):
        with QSignalBlocker(self.list), QSignalBlocker(self.compact_tabs):
            self.list.setCurrentRow(index)
            self.compact_tabs.setCurrentIndex(index)

    def _changed(self, index):
        self._sync(index)
        self.currentChanged.emit(index)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        compact = self.width() < self.fontMetrics().horizontalAdvance("M") * 70
        self.rail.setVisible(not compact)
        self.compact_tabs.setVisible(compact)
        self.rail.setFixedWidth(self.fontMetrics().horizontalAdvance("M") * 17)
