import os
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame, QScrollArea, QFileDialog
)
from gui.ui_theme import set_widget_props
from core.settings_manager import settings

class HomePanel(QWidget):
    new_project_requested = Signal()
    open_project_requested = Signal(str)

    def __init__(self):
        super().__init__()
        self._build_ui()
        self.refresh_history()

    def _build_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        root_layout.addWidget(scroll)

        content = QWidget()
        scroll.setWidget(content)
        layout = QVBoxLayout(content)
        layout.setAlignment(Qt.AlignTop | Qt.AlignHCenter)
        layout.setSpacing(24)
        layout.setContentsMargins(24, 48, 24, 48)

        hero_card = set_widget_props(QFrame(), role="heroCard")
        hero_card.setMaximumWidth(800)
        hero_layout = QVBoxLayout(hero_card)
        hero_layout.setSpacing(16)
        
        title = set_widget_props(QLabel("Auto Video Editor"), role="heroTitle")
        title.setAlignment(Qt.AlignCenter)
        hero_layout.addWidget(title)

        subtitle = set_widget_props(QLabel("Pilih untuk membuat proyek baru atau melanjutkan proyek yang sudah ada."), role="body")
        subtitle.setAlignment(Qt.AlignCenter)
        hero_layout.addWidget(subtitle)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(16)
        
        self.btn_new = QPushButton("Proyek Baru")
        self.btn_new.setMinimumHeight(64)
        set_widget_props(self.btn_new, variant="primary")
        self.btn_new.clicked.connect(self.new_project_requested.emit)
        
        self.btn_open = QPushButton("Buka Folder Proyek")
        self.btn_open.setMinimumHeight(64)
        set_widget_props(self.btn_open, variant="secondary")
        self.btn_open.clicked.connect(self._on_open_clicked)
        
        self.btn_open_archive = QPushButton("Buka Proyek (.avep)")
        self.btn_open_archive.setMinimumHeight(64)
        set_widget_props(self.btn_open_archive, variant="ghost")
        self.btn_open_archive.clicked.connect(self._on_open_archive_clicked)
        
        btn_layout.addWidget(self.btn_new, 1)
        btn_layout.addWidget(self.btn_open, 1)
        btn_layout.addWidget(self.btn_open_archive, 1)
        hero_layout.addLayout(btn_layout)
        
        layout.addWidget(hero_card)

        hist_card = set_widget_props(QFrame(), role="panelCard")
        hist_card.setMaximumWidth(800)
        self.hist_layout = QVBoxLayout(hist_card)
        self.hist_layout.setSpacing(12)
        
        hist_title = set_widget_props(QLabel("Riwayat Proyek Terakhir"), role="sectionTitle")
        self.hist_layout.addWidget(hist_title)

        self.hist_container = QVBoxLayout()
        self.hist_layout.addLayout(self.hist_container)
        
        layout.addWidget(hist_card)
        layout.addStretch(1)

    def _on_open_clicked(self):
        root = settings.get("projects_root", "")
        folder = QFileDialog.getExistingDirectory(self, "Pilih Folder Proyek", root)
        if folder:
            self.open_project_requested.emit(folder)
            
    def _on_open_archive_clicked(self):
        root = settings.get("projects_root", "")
        path, _ = QFileDialog.getOpenFileName(self, "Buka Arsip Proyek", root, "AutoVideoEditor Project (*.avep)")
        if path:
            self.open_project_requested.emit(path)

    def refresh_history(self):
        while self.hist_container.count():
            item = self.hist_container.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
                
        history = settings.get("project_history", [])
        
        valid_history = []
        for path in history:
            if os.path.exists(path):
                valid_history.append(path)
                
        if not valid_history:
            lbl = set_widget_props(QLabel("Belum ada riwayat proyek."), role="helper")
            self.hist_container.addWidget(lbl)
            return

        for path in reversed(valid_history[-5:]):
            row = QFrame()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(8, 8, 8, 8)
            name = os.path.basename(path)
            
            lbl_name = set_widget_props(QLabel(name), role="subTitle")
            lbl_path = set_widget_props(QLabel(path), role="helper")
            
            text_layout = QVBoxLayout()
            text_layout.addWidget(lbl_name)
            text_layout.addWidget(lbl_path)
            
            btn_open = QPushButton("Buka")
            set_widget_props(btn_open, variant="ghost")
            
            def create_callback(p=path):
                return lambda checked=False: self.open_project_requested.emit(p)
                
            btn_open.clicked.connect(create_callback())
            
            row_layout.addLayout(text_layout, 1)
            row_layout.addWidget(btn_open)
            self.hist_container.addWidget(row)
