import sys
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QComboBox,
    QMessageBox,
    QFileDialog,
    QWidget
)
from core.settings_manager import settings

class _TestWorker(QThread):
    result = Signal(str, bool, str)

    def __init__(self, provider: str, values: dict):
        super().__init__()
        self.provider = provider
        self.values = values

    def run(self):
        # Validate Pexels and Pixabay first
        ok_pex, msg_pex = settings.validate_pexels_key(self.values.get("pexels"))
        if not ok_pex:
            self.result.emit("error", False, f"Pexels: {msg_pex}")
            return
            
        ok_pix, msg_pix = settings.validate_pixabay_key(self.values.get("pixabay"))
        if not ok_pix:
            self.result.emit("error", False, f"Pixabay: {msg_pix}")
            return
            
        if self.provider == "gemini":
            ok_ai, msg_ai = settings.validate_gemini_key(self.values.get("gemini"))
            if not ok_ai:
                self.result.emit("error", False, f"Gemini: {msg_ai}")
                return
        else:
            ok_ai, msg_ai = settings.validate_vertex_ai(
                project="",
                location="global",
                key_path=self.values.get("vertex")
            )
            if not ok_ai:
                self.result.emit("error", False, f"Vertex AI: {msg_ai}")
                return
                
        self.result.emit("success", True, "Validasi Berhasil")


class FirstSetupDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Selamat Datang di Program B-Roll")
        # Remove close button
        self.setWindowFlags(Qt.Window | Qt.CustomizeWindowHint | Qt.WindowTitleHint)
        self.setFixedSize(500, 480)
        self._build_ui()
        self._workers = []

    def closeEvent(self, event):
        # If user forces close (Alt+F4), exit the whole application
        sys.exit(0)

    def _build_ui(self):
        self.setStyleSheet(
            """
            QDialog { background: #08101d; color: #edf3ff; }
            QLabel { color: #dbeafe; font-size: 13px; }
            QLabel#title { font-size: 18px; font-weight: bold; color: #ffffff; }
            QLabel#subtitle { color: #94a3b8; font-size: 12px; margin-bottom: 10px; }
            QLineEdit, QComboBox {
                background: #0b1628;
                color: #ffffff;
                border: 1px solid #22314c;
                border-radius: 10px;
                padding: 8px 12px;
                font-size: 13px;
            }
            QLineEdit:focus, QComboBox:hover { border: 1px solid #5baeff; }
            QPushButton {
                background: #15213a;
                color: #f8fafc;
                border: 1px solid #2b4061;
                border-radius: 10px;
                padding: 8px 16px;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton:hover { background: #1b2d4b; border-color: #5177a8; }
            QPushButton#btn_save {
                background: #2de29a;
                color: #032019;
                font-size: 14px;
                font-weight: bold;
                padding: 12px 24px;
            }
            """
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        lbl_title = QLabel("Konfigurasi Awal (Wajib)")
        lbl_title.setObjectName("title")
        lbl_title.setAlignment(Qt.AlignCenter)
        layout.addWidget(lbl_title)
        
        lbl_subtitle = QLabel("Silakan isi API Key Anda sebelum mulai membuat video.")
        lbl_subtitle.setObjectName("subtitle")
        lbl_subtitle.setAlignment(Qt.AlignCenter)
        layout.addWidget(lbl_subtitle)

        # Pexels
        layout.addWidget(QLabel("Pexels API Key:"))
        self.inp_pexels = QLineEdit()
        self.inp_pexels.setPlaceholderText("Masukkan API Key Pexels (Gratis)")
        layout.addWidget(self.inp_pexels)

        # Pixabay
        layout.addWidget(QLabel("Pixabay API Key:"))
        self.inp_pixabay = QLineEdit()
        self.inp_pixabay.setPlaceholderText("Masukkan API Key Pixabay (Gratis)")
        layout.addWidget(self.inp_pixabay)

        layout.addSpacing(10)
        layout.addWidget(QLabel("Pilih Penyedia AI (Gemini direkomendasikan):"))
        self.cmb_ai_provider = QComboBox()
        self.cmb_ai_provider.addItems(["Google Gemini API", "GCP Vertex AI"])
        self.cmb_ai_provider.currentIndexChanged.connect(self._on_ai_provider_changed)
        layout.addWidget(self.cmb_ai_provider)

        # Gemini Container
        self.container_gemini = QWidget()
        lay_gemini = QVBoxLayout(self.container_gemini)
        lay_gemini.setContentsMargins(0, 0, 0, 0)
        lay_gemini.addWidget(QLabel("Gemini API Key:"))
        self.inp_gemini = QLineEdit()
        self.inp_gemini.setPlaceholderText("Masukkan API Key Google AI Studio")
        lay_gemini.addWidget(self.inp_gemini)
        layout.addWidget(self.container_gemini)

        # Vertex Container
        self.container_vertex = QWidget()
        lay_vertex = QVBoxLayout(self.container_vertex)
        lay_vertex.setContentsMargins(0, 0, 0, 0)
        lay_vertex.addWidget(QLabel("Vertex AI JSON Path:"))
        lay_vertex_h = QHBoxLayout()
        self.inp_vertex = QLineEdit()
        self.inp_vertex.setReadOnly(True)
        self.inp_vertex.setPlaceholderText("Pilih file service_account.json")
        lay_vertex_h.addWidget(self.inp_vertex)
        btn_browse = QPushButton("Pilih File")
        btn_browse.clicked.connect(self._browse_vertex_json)
        lay_vertex_h.addWidget(btn_browse)
        lay_vertex.addLayout(lay_vertex_h)
        layout.addWidget(self.container_vertex)
        
        self.inp_pexels.setText(settings.get("pexels_api_key", ""))
        self.inp_pixabay.setText(settings.get("pixabay_api_key", ""))
        
        provider = settings.get("ai_provider", "gemini")
        if provider == "gemini":
            self.cmb_ai_provider.setCurrentIndex(0)
            self.container_gemini.show()
            self.container_vertex.hide()
        else:
            self.cmb_ai_provider.setCurrentIndex(1)
            self.container_gemini.hide()
            self.container_vertex.show()

        self.inp_gemini.setText(settings.get("gemini_api_key", ""))
        self.inp_vertex.setText(settings.get("gcp_key_path", ""))

        layout.addStretch()

        self.btn_save = QPushButton("Simpan & Mulai")
        self.btn_save.setObjectName("btn_save")
        self.btn_save.clicked.connect(self._on_save)
        layout.addWidget(self.btn_save)

    def _on_ai_provider_changed(self, index):
        if index == 0:
            self.container_gemini.show()
            self.container_vertex.hide()
        else:
            self.container_gemini.hide()
            self.container_vertex.show()

    def _browse_vertex_json(self):
        path, _ = QFileDialog.getOpenFileName(self, "Pilih GCP Service Account JSON", "", "JSON Files (*.json)")
        if path:
            self.inp_vertex.setText(path)

    def _on_save(self):
        pex = self.inp_pexels.text().strip()
        pix = self.inp_pixabay.text().strip()
        provider = "gemini" if self.cmb_ai_provider.currentIndex() == 0 else "vertex_ai"
        gemini = self.inp_gemini.text().strip()
        vertex = self.inp_vertex.text().strip()

        if not pex or not pix:
            QMessageBox.warning(self, "Error", "Pexels dan Pixabay API Key wajib diisi.")
            return
            
        if provider == "gemini" and not gemini:
            QMessageBox.warning(self, "Error", "Gemini API Key wajib diisi.")
            return
            
        if provider == "vertex_ai" and not vertex:
            QMessageBox.warning(self, "Error", "Pilih file Vertex AI JSON.")
            return

        self.btn_save.setText("Memvalidasi...")
        self.btn_save.setEnabled(False)

        worker = _TestWorker(provider, {
            "pexels": pex,
            "pixabay": pix,
            "gemini": gemini,
            "vertex": vertex
        })
        worker.result.connect(self._on_test_result)
        self._workers.append(worker)
        worker.start()

    def _on_test_result(self, status, success, msg):
        self.btn_save.setText("Simpan & Mulai")
        self.btn_save.setEnabled(True)
        if not success:
            QMessageBox.critical(self, "Validasi Gagal", msg)
            return
            
        # Save to settings
        provider = "gemini" if self.cmb_ai_provider.currentIndex() == 0 else "vertex_ai"
        
        settings.set("pexels_api_key", self.inp_pexels.text().strip())
        settings.set("pixabay_api_key", self.inp_pixabay.text().strip())
        settings.set("ai_provider", provider)
        if provider == "gemini":
            settings.set("gemini_api_key", self.inp_gemini.text().strip())
        else:
            settings.set("gcp_key_path", self.inp_vertex.text().strip())
            
        # Accept the dialog and continue
        # Since we modified the close event, we must disconnect it or use done() directly
        self.done(1)
