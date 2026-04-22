import json
import os

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)
from gui.ui_theme import set_widget_props


class _TestWorker(QThread):
    result = Signal(str, bool, str)

    def __init__(self, key_name: str, values: dict):
        super().__init__()
        self.key_name = key_name
        self.values = values

    def run(self):
        from core.settings_manager import settings

        if self.key_name == "vertex_ai":
            ok, msg = settings.validate_vertex_ai(
                project=self.values.get("project"),
                location="global",
                key_path=self.values.get("key_path"),
            )
        elif self.key_name == "pexels_api_key":
            ok, msg = settings.validate_pexels_key(self.values.get("key"))
        elif self.key_name == "pixabay_api_key":
            ok, msg = settings.validate_pixabay_key(self.values.get("key"))
        else:
            ok, msg = False, "Unknown key"
        self.result.emit(self.key_name, ok, msg)


class _FetchModelsWorker(QThread):
    result = Signal(list, str)

    def __init__(self, key_path: str, allow_preview: bool):
        super().__init__()
        self.key_path = key_path
        self.allow_preview = allow_preview

    def run(self):
        try:
            from google import genai
            from google.oauth2 import service_account

            if not self.key_path or not os.path.exists(self.key_path):
                raise ValueError("File Service Account JSON belum dipilih")

            with open(self.key_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            project_id = str(data.get("project_id", "")).strip()
            if not project_id:
                raise ValueError("project_id tidak ditemukan di file JSON")

            credentials = service_account.Credentials.from_service_account_file(
                self.key_path,
                scopes=["https://www.googleapis.com/auth/cloud-platform"],
            )
            client = genai.Client(
                vertexai=True,
                project=project_id,
                location="global",
                credentials=credentials,
            )

            models = []
            for model in client.models.list():
                full_name = getattr(model, "name", "") or ""
                name = full_name.split("/")[-1]
                if not name.startswith("gemini-") and "veo" not in name:
                    continue
                if not self.allow_preview and "preview" in name.lower():
                    continue
                models.append(name)

            # Injeksi model statis yang direkomendasikan agar selalu muncul di UI
            from core.settings_manager import settings
            static_models = settings.get_global_gemini_models()
            for sm in static_models:
                if not self.allow_preview and "preview" in sm.lower():
                    continue
                models.append(sm)

            models = sorted(set(models))
            self.result.emit(models, "")
        except Exception as e:
            self.result.emit([], str(e))


class _DetectEncoderWorker(QThread):
    result = Signal(dict)

    def __init__(self, force: bool = False):
        super().__init__()
        self.force = force

    def run(self):
        try:
            from core.video_encoder_manager import refresh_video_encoder_detection

            payload = refresh_video_encoder_detection(force=self.force)
            payload["error"] = ""
        except Exception as e:
            payload = {
                "detected": "",
                "status": f"Gagal mendeteksi encoder: {e}",
                "checked_at": 0,
                "error": str(e),
            }
        self.result.emit(payload)


class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Pengaturan Proyek dan Vertex AI")
        self.setObjectName("settings_dialog")
        self.resize(900, 760)
        self.setMinimumSize(760, 560)
        self.setModal(True)
        self._workers = []
        self._syncing_model_state = False
        self._available_models = []
        self._encoder_detection = {"detected": "", "status": "Belum dicek", "checked_at": 0}
        self._build_ui()
        self._load_existing_values()
        self._fit_to_available_screen()

    def _build_ui(self):
        self.setStyleSheet(
            """
            QDialog { background: #08101d; color: #edf3ff; }
            QLabel { color: #dbeafe; font-size: 13px; }
            QLineEdit, QComboBox {
                background: #0b1628;
                color: #ffffff;
                border: 1px solid #22314c;
                border-radius: 14px;
                padding: 10px 12px;
                font-size: 13px;
            }
            QLineEdit:focus, QComboBox:hover { border: 1px solid #5baeff; }
            QPushButton {
                background: #15213a;
                color: #f8fafc;
                border: 1px solid #2b4061;
                border-radius: 14px;
                padding: 10px 16px;
                font-size: 12px;
                font-weight: 700;
            }
            QPushButton:hover { background: #1b2d4b; border-color: #5177a8; }
            QPushButton#btn_save {
                background: #2de29a;
                color: #032019;
                font-weight: 800;
                padding: 10px 24px;
            }
            QCheckBox { color: #f8fafc; font-size: 13px; }
            QScrollArea { border: none; background: transparent; }
            """
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        layout.addWidget(self.scroll, 1)

        content = QWidget()
        content.setStyleSheet("background: #08101d;")
        self.scroll.setWidget(content)

        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(22, 22, 22, 22)
        content_layout.setSpacing(16)

        header = QLabel("Pengaturan")
        header.setStyleSheet("font-size: 20px; font-weight: 800; color: #f8fafc;")
        content_layout.addWidget(header)

        top_card = QFrame()
        top_card.setStyleSheet("QFrame { background: #10192d; border-radius: 18px; border: 1px solid #1f2e49; }")
        top_grid = QGridLayout(top_card)
        top_grid.setContentsMargins(16, 16, 16, 16)
        top_grid.setHorizontalSpacing(12)
        top_grid.setVerticalSpacing(12)

        self.inp_json = QLineEdit()
        self.inp_json.setPlaceholderText("Pilih file Service Account JSON")
        btn_browse = QPushButton("Pilih JSON")
        btn_browse.clicked.connect(self._browse_json)
        btn_test = QPushButton("Tes Vertex")
        btn_test.clicked.connect(lambda: self._test_key("vertex_ai"))

        self.lbl_project = QLabel("-")
        self.lbl_project.setWordWrap(True)
        self.lbl_project.setStyleSheet("color: #f8fafc; font-weight: bold;")
        self.lbl_region = QLabel("global")
        self.lbl_region.setStyleSheet("color: #f8fafc; font-weight: bold;")
        self.lbl_status_vertex = QLabel("")
        self.lbl_status_vertex.setWordWrap(True)

        top_grid.addWidget(QLabel("Service Account JSON"), 0, 0)
        top_grid.addWidget(self.inp_json, 0, 1)
        top_grid.addWidget(btn_browse, 0, 2)
        top_grid.addWidget(btn_test, 0, 3)
        top_grid.addWidget(QLabel("Project ID"), 1, 0)
        top_grid.addWidget(self.lbl_project, 1, 1, 1, 3)
        top_grid.addWidget(QLabel("Region"), 2, 0)
        top_grid.addWidget(self.lbl_region, 2, 1, 1, 3)
        top_grid.addWidget(self.lbl_status_vertex, 3, 0, 1, 4)
        content_layout.addWidget(self._section_title("Koneksi Vertex AI"))
        content_layout.addWidget(top_card)

        project_card = QFrame()
        project_card.setStyleSheet("QFrame { background: #10192d; border-radius: 18px; border: 1px solid #1f2e49; }")
        project_grid = QGridLayout(project_card)
        project_grid.setContentsMargins(16, 16, 16, 16)
        project_grid.setHorizontalSpacing(12)
        project_grid.setVerticalSpacing(12)

        self.inp_projects_root = QLineEdit()
        self.inp_projects_root.setPlaceholderText("Folder global penyimpanan proyek")
        btn_projects_root = QPushButton("Pilih Folder")
        btn_projects_root.clicked.connect(self._browse_projects_root)
        project_grid.addWidget(QLabel("Folder proyek global"), 0, 0)
        project_grid.addWidget(self.inp_projects_root, 0, 1)
        project_grid.addWidget(btn_projects_root, 0, 2)
        content_layout.addWidget(self._section_title("Penyimpanan Proyek"))
        content_layout.addWidget(project_card)

        stock_card = QFrame()
        stock_card.setStyleSheet("QFrame { background: #10192d; border-radius: 18px; border: 1px solid #1f2e49; }")
        stock_grid = QGridLayout(stock_card)
        stock_grid.setContentsMargins(16, 16, 16, 16)
        stock_grid.setHorizontalSpacing(12)
        stock_grid.setVerticalSpacing(12)

        self.cmb_default_source = QComboBox()
        self.cmb_default_source.addItem("Pexels", "pexels")
        self.cmb_default_source.addItem("Pixabay", "pixabay")

        self.inp_pexels = QLineEdit()
        self.inp_pexels.setEchoMode(QLineEdit.Password)
        self.inp_pixabay = QLineEdit()
        self.inp_pixabay.setEchoMode(QLineEdit.Password)
        btn_test_pexels = QPushButton("Test Pexels")
        btn_test_pexels.clicked.connect(lambda: self._test_key("pexels_api_key"))
        btn_test_pixabay = QPushButton("Test Pixabay")
        btn_test_pixabay.clicked.connect(lambda: self._test_key("pixabay_api_key"))
        self.lbl_status_px = QLabel("")
        self.lbl_status_pb = QLabel("")
        self.lbl_status_px.setWordWrap(True)
        self.lbl_status_pb.setWordWrap(True)

        stock_grid.addWidget(QLabel("Default Source"), 0, 0)
        stock_grid.addWidget(self.cmb_default_source, 0, 1, 1, 2)
        stock_grid.addWidget(QLabel("Pexels API Key"), 1, 0)
        stock_grid.addWidget(self.inp_pexels, 1, 1)
        stock_grid.addWidget(btn_test_pexels, 1, 2)
        stock_grid.addWidget(self.lbl_status_px, 2, 0, 1, 3)
        stock_grid.addWidget(QLabel("Pixabay API Key"), 3, 0)
        stock_grid.addWidget(self.inp_pixabay, 3, 1)
        stock_grid.addWidget(btn_test_pixabay, 3, 2)
        stock_grid.addWidget(self.lbl_status_pb, 4, 0, 1, 3)
        content_layout.addWidget(self._section_title("Sumber B-roll"))
        content_layout.addWidget(stock_card)

        model_card = QFrame()
        model_card.setStyleSheet("QFrame { background: #10192d; border-radius: 18px; border: 1px solid #1f2e49; }")
        model_grid = QGridLayout(model_card)
        model_grid.setContentsMargins(16, 16, 16, 16)
        model_grid.setHorizontalSpacing(12)
        model_grid.setVerticalSpacing(12)

        self.cmb_profile = QComboBox()
        self.cmb_profile.addItem("Cepat", "fast")
        self.cmb_profile.addItem("Sedang", "balanced")
        self.cmb_profile.addItem("Akurat", "accurate")
        self.cmb_profile.addItem("Manual", "manual")
        self.cmb_profile.currentIndexChanged.connect(self._toggle_manual_models)

        self.chk_preview = QCheckBox("Preview")
        self.chk_preview.toggled.connect(self._on_preview_toggled)
        btn_refresh = QPushButton("🔄")
        btn_refresh.setFixedWidth(40)
        btn_refresh.clicked.connect(self._fetch_remote_models)

        self.cmb_model_transcribe = QComboBox()
        self.cmb_model_planner = QComboBox()
        self.cmb_model_vision = QComboBox()
        self.cmb_model_video = QComboBox()
        self.cmb_model_tts = QComboBox()
        for combo in (
            self.cmb_model_transcribe,
            self.cmb_model_planner,
            self.cmb_model_vision,
            self.cmb_model_video,
            self.cmb_model_tts,
        ):
            combo.setEditable(True)
            combo.currentIndexChanged.connect(self._activate_manual_profile)
            combo.editTextChanged.connect(self._activate_manual_profile)

        self.lbl_model_mode = QLabel("")
        self.lbl_model_mode.setWordWrap(True)
        self.lbl_model_mode.setStyleSheet("color: #93c5fd; font-size: 12px;")

        preset_layout = QHBoxLayout()
        preset_layout.setContentsMargins(0, 0, 0, 0)
        preset_layout.addWidget(self.cmb_profile, 1)
        preset_layout.addWidget(self.chk_preview)
        preset_layout.addWidget(btn_refresh)

        model_grid.addWidget(QLabel("Preset model"), 0, 0)
        model_grid.addLayout(preset_layout, 0, 1, 1, 3)
        model_grid.addWidget(QLabel("Transkripsi"), 1, 0)
        model_grid.addWidget(self.cmb_model_transcribe, 1, 1, 1, 3)
        model_grid.addWidget(QLabel("Planner"), 2, 0)
        model_grid.addWidget(self.cmb_model_planner, 2, 1, 1, 3)
        model_grid.addWidget(QLabel("Vision selector"), 3, 0)
        model_grid.addWidget(self.cmb_model_vision, 3, 1, 1, 3)
        model_grid.addWidget(QLabel("Video Generator"), 4, 0)
        model_grid.addWidget(self.cmb_model_video, 4, 1, 1, 3)
        model_grid.addWidget(QLabel("TTS"), 5, 0)
        model_grid.addWidget(self.cmb_model_tts, 5, 1, 1, 3)
        model_grid.addWidget(self.lbl_model_mode, 6, 0, 1, 4)
        content_layout.addWidget(self._section_title("Model AI"))
        content_layout.addWidget(model_card)

        encoder_card = QFrame()
        encoder_card.setStyleSheet("QFrame { background: #10192d; border-radius: 18px; border: 1px solid #1f2e49; }")
        encoder_grid = QGridLayout(encoder_card)
        encoder_grid.setContentsMargins(16, 16, 16, 16)
        encoder_grid.setHorizontalSpacing(12)
        encoder_grid.setVerticalSpacing(12)

        self.cmb_video_encoder = QComboBox()
        self.cmb_video_encoder.addItem("Otomatis", "auto")
        self.cmb_video_encoder.addItem("Intel Quick Sync (h264_qsv)", "h264_qsv")
        self.cmb_video_encoder.addItem("CPU x264 (libx264)", "libx264")
        self.cmb_video_encoder.currentIndexChanged.connect(
            lambda: self._refresh_encoder_status_label(self._encoder_detection)
        )
        btn_detect_encoder = QPushButton("Cek Encoder")
        btn_detect_encoder.clicked.connect(lambda: self._detect_encoder(force=True))
        self.lbl_encoder_status = QLabel("")
        self.lbl_encoder_status.setWordWrap(True)

        encoder_grid.addWidget(QLabel("Encoder video"), 0, 0)
        encoder_grid.addWidget(self.cmb_video_encoder, 0, 1)
        encoder_grid.addWidget(btn_detect_encoder, 0, 2)
        encoder_grid.addWidget(self.lbl_encoder_status, 1, 0, 1, 3)
        content_layout.addWidget(self._section_title("Encoder Render"))
        content_layout.addWidget(encoder_card)

        footer = QFrame()
        footer.setStyleSheet("QFrame { background: #0a1324; border-top: 1px solid #16233a; }")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(18, 14, 18, 14)
        footer_layout.setSpacing(10)
        footer_layout.addStretch()
        btn_clear_cache = QPushButton("Hapus Cache Global")
        btn_clear_cache.clicked.connect(self._clear_global_cache)
        btn_cancel = QPushButton("Batal")
        btn_cancel.clicked.connect(self.reject)
        btn_save = QPushButton("Simpan")
        btn_save.setObjectName("btn_save")
        set_widget_props(btn_save, variant="primary")
        btn_save.clicked.connect(self._save)
        footer_layout.addWidget(btn_clear_cache)
        footer_layout.addWidget(btn_cancel)
        footer_layout.addWidget(btn_save)
        layout.addWidget(footer, 0)

    def _section_title(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setStyleSheet("font-size: 15px; font-weight: 800; color: #f8fafc; padding-left: 2px;")
        return label

    def showEvent(self, event):
        super().showEvent(event)
        self._fit_to_available_screen()

    def _fit_to_available_screen(self):
        screen = self.screen() or QApplication.primaryScreen()
        if not screen:
            return

        available = screen.availableGeometry()
        max_width = max(760, available.width() - 40)
        max_height = max(560, available.height() - 40)
        self.setMaximumSize(max_width, max_height)
        self.resize(min(self.width(), max_width), min(self.height(), max_height))

        x = available.x() + max(0, (available.width() - self.width()) // 2)
        y = available.y() + max(0, (available.height() - self.height()) // 2)
        self.move(x, y)

    def _apply_model_choices(self, models: list[str]):
        unique_models = self._unique_models(models)
        self._available_models = unique_models

        current_map = {
            "transcribe": self.cmb_model_transcribe.currentText(),
            "planner": self.cmb_model_planner.currentText(),
            "vision": self.cmb_model_vision.currentText(),
            "video": self.cmb_model_video.currentText(),
            "tts": self.cmb_model_tts.currentText(),
        }
        self._apply_combo_models(
            self.cmb_model_transcribe,
            self._filter_models_for_task(unique_models, "transcribe"),
            current_map["transcribe"],
        )
        self._apply_combo_models(
            self.cmb_model_planner,
            self._filter_models_for_task(unique_models, "planner"),
            current_map["planner"],
        )
        self._apply_combo_models(
            self.cmb_model_vision,
            self._filter_models_for_task(unique_models, "vision"),
            current_map["vision"],
        )
        self._apply_combo_models(
            self.cmb_model_video,
            self._filter_models_for_task(unique_models, "video"),
            current_map["video"],
        )
        self._apply_combo_models(
            self.cmb_model_tts,
            self._filter_models_for_task(unique_models, "tts"),
            current_map["tts"],
        )
        self._sync_preview_checkbox()

    def _load_existing_values(self):
        from core.settings_manager import settings

        self.inp_json.setText(settings.get("gcp_key_path", ""))
        self._refresh_project_label()
        self.inp_projects_root.setText(settings.get("projects_root", ""))
        self.inp_pexels.setText(settings.get("pexels_api_key", ""))
        self.inp_pixabay.setText(settings.get("pixabay_api_key", ""))
        default_broll = settings.get("default_broll_source", "pexels")
        idx = self.cmb_default_source.findData(default_broll)
        if idx >= 0:
            self.cmb_default_source.setCurrentIndex(idx)
        self.chk_preview.setChecked(bool(settings.get("allow_preview_models", False)))
        self._apply_model_choices(settings.get_global_gemini_models())
        encoder_index = self.cmb_video_encoder.findData(settings.get_video_encoder_mode())
        self.cmb_video_encoder.setCurrentIndex(encoder_index if encoder_index >= 0 else 0)
        self._refresh_encoder_status_label(settings.get_video_encoder_detection())

        profile = settings.get("model_profile", "balanced")
        index = self.cmb_profile.findData(profile)
        if index >= 0:
            self.cmb_profile.setCurrentIndex(index)

        self.cmb_model_transcribe.setCurrentText(settings.get_model_for_task("transcribe"))
        self.cmb_model_planner.setCurrentText(settings.get_model_for_task("planner"))
        self.cmb_model_vision.setCurrentText(settings.get_model_for_task("vision"))
        self.cmb_model_video.setCurrentText(settings.get_model_for_task("video"))
        self.cmb_model_tts.setCurrentText(settings.get_model_for_task("tts"))
        self._toggle_manual_models()
        self._sync_preview_checkbox()
        if not settings.get_video_encoder_detection().get("checked_at"):
            self._detect_encoder(force=False)

    def _browse_json(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Pilih Service Account JSON",
            "",
            "JSON Files (*.json)",
        )
        if path:
            self.inp_json.setText(path)
            self._refresh_project_label()

    def _refresh_project_label(self):
        from core.settings_manager import settings

        project_id = settings.infer_project_id_from_key_path(self.inp_json.text().strip())
        self.lbl_project.setText(project_id or "-")

    def _browse_projects_root(self):
        path = QFileDialog.getExistingDirectory(
            self,
            "Pilih folder global proyek",
            self.inp_projects_root.text().strip(),
        )
        if path:
            self.inp_projects_root.setText(path)

    def _clear_global_cache(self):
        from core.cache_manager import clear_cache, format_bytes

        removed, freed = clear_cache(None)
        QMessageBox.information(
            self,
            "Cache Global Dikosongkan",
            f"Berhasil menghapus {removed} file cache global. Total ruang dibebaskan: {format_bytes(freed)}.",
        )

    def _toggle_manual_models(self):
        is_manual = self.cmb_profile.currentData() == "manual"
        if not is_manual:
            self._syncing_model_state = True
            bundle = self._preset_bundle(self.cmb_profile.currentData())
            self.cmb_model_transcribe.setCurrentText(bundle.get("transcribe", ""))
            self.cmb_model_planner.setCurrentText(bundle.get("planner", ""))
            self.cmb_model_vision.setCurrentText(bundle.get("vision", ""))
            self.cmb_model_video.setCurrentText(bundle.get("video", "veo-2.0-generate-001"))
            self.cmb_model_tts.setCurrentText(bundle.get("tts", "gemini-3.1-flash-tts-preview"))
            self._syncing_model_state = False
            self.lbl_model_mode.setText(
                "Preset aktif. Klik dropdown model tertentu untuk otomatis pindah ke mode Manual."
            )
        else:
            self.lbl_model_mode.setText(
                "Mode Manual aktif. Kamu bisa memilih model transkripsi, planner, vision, video generator, dan TTS secara terpisah."
            )
        self._sync_preview_checkbox()

    def _activate_manual_profile(self, *_args):
        if self._syncing_model_state or self.cmb_profile.currentData() == "manual":
            return
        manual_index = self.cmb_profile.findData("manual")
        if manual_index >= 0:
            self.cmb_profile.setCurrentIndex(manual_index)

    def _preset_bundle(self, profile: str) -> dict:
        from core.settings_manager import settings

        bundle = settings.get_preset_bundle(profile or "balanced")
        if self._available_models:
            bundle = {
                "transcribe": self._resolve_bundle_model(bundle.get("transcribe", ""), "transcribe"),
                "planner": self._resolve_bundle_model(bundle.get("planner", ""), "planner"),
                "vision": self._resolve_bundle_model(bundle.get("vision", ""), "vision"),
                "video": self._resolve_bundle_model(bundle.get("video", "veo-2.0-generate-001"), "video"),
                "tts": self._resolve_bundle_model(bundle.get("tts", "gemini-3.1-flash-tts-preview"), "tts"),
            }
        return bundle

    def _unique_models(self, models: list[str]) -> list[str]:
        unique = []
        for model in models:
            model = str(model).strip()
            if model and model not in unique:
                unique.append(model)
        return unique

    def _filter_models_for_task(self, models: list[str], task: str) -> list[str]:
        filtered = [model for model in models if self._is_model_compatible(model, task)]
        return filtered or models

    def _is_model_compatible(self, model: str, task: str) -> bool:
        name = str(model or "").strip().lower()
        if task == "video":
            return "veo" in name
            
        if not name.startswith("gemini-"):
            return False
            
        if task == "transcribe":
            return "-image-" not in name and "-tts" not in name
        if task == "planner":
            return "native-audio" not in name and "-image-" not in name and "-tts" not in name
        if task == "vision":
            return "native-audio" not in name and "-tts" not in name
        if task == "tts":
            return "tts" in name or "audio" in name
        return True

    def _apply_combo_models(self, combo: QComboBox, models: list[str], current: str):
        combo.blockSignals(True)
        combo.clear()
        combo.addItems(models)
        if current:
            if combo.findText(current) == -1:
                combo.addItem(current)
            combo.setCurrentText(current)
        elif models:
            combo.setCurrentText(models[0])
        combo.blockSignals(False)

    def _resolve_bundle_model(self, preferred: str, task: str) -> str:
        candidates = self._filter_models_for_task(self._available_models, task)
        if preferred in candidates:
            return preferred

        preferred_lower = preferred.lower()
        for model in candidates:
            if model.lower() == preferred_lower:
                return model

        keywords = self._task_keywords_for_preferred(task, preferred_lower)
        for keyword in keywords:
            for model in candidates:
                if keyword in model.lower():
                    return model
        return candidates[0] if candidates else preferred

    def _task_keywords_for_preferred(self, task: str, preferred_lower: str) -> list[str]:
        if task == "transcribe":
            if "3.1-flash-lite-preview" in preferred_lower:
                return ["3.1-flash-lite-preview", "native-audio", "flash-lite-preview", "flash-lite", "flash-preview", "flash"]
            if "flash" in preferred_lower:
                return ["flash", "pro"]
        if task == "planner":
            if "3.1-pro-preview" in preferred_lower:
                return ["3.1-pro-preview", "pro-preview", "2.5-pro", "pro", "flash-preview", "flash"]
            if "pro" in preferred_lower:
                return ["pro", "flash"]
        if task == "vision":
            if "3-flash-preview" in preferred_lower:
                return ["3-flash-preview", "flash-preview", "2.5-flash", "flash", "pro-preview", "pro"]
            if "flash" in preferred_lower:
                return ["flash", "pro"]
        if task == "video":
            if "2.0" in preferred_lower:
                return ["2.0", "veo"]
            return ["veo"]
        if task == "tts":
            if "3.1" in preferred_lower:
                return ["3.1", "tts", "audio"]
            return ["tts", "audio"]
        return ["pro-preview", "flash-preview", "pro", "flash", "flash-lite"]

    def _selected_models(self) -> list[str]:
        return [
            self.cmb_model_transcribe.currentText().strip(),
            self.cmb_model_planner.currentText().strip(),
            self.cmb_model_vision.currentText().strip(),
            self.cmb_model_video.currentText().strip(),
            self.cmb_model_tts.currentText().strip(),
        ]

    def _has_preview_model_selected(self) -> bool:
        return any("preview" in model.lower() for model in self._selected_models() if model)

    def _sync_preview_checkbox(self):
        should_check = self._has_preview_model_selected()
        self.chk_preview.blockSignals(True)
        self.chk_preview.setChecked(should_check)
        self.chk_preview.blockSignals(False)

    def _on_model_selection_changed(self, *_args):
        self._sync_preview_checkbox()

    def _on_preview_toggled(self, checked: bool):
        if checked:
            return
        if self._has_preview_model_selected():
            self.chk_preview.blockSignals(True)
            self.chk_preview.setChecked(True)
            self.chk_preview.blockSignals(False)

    def _test_key(self, key_name: str):
        if key_name == "vertex_ai":
            values = {
                "project": self.lbl_project.text().strip() if self.lbl_project.text().strip() != "-" else "",
                "key_path": self.inp_json.text().strip(),
            }
            status_lbl = self.lbl_status_vertex
        elif key_name == "pexels_api_key":
            values = {"key": self.inp_pexels.text().strip()}
            status_lbl = self.lbl_status_px
        else:
            values = {"key": self.inp_pixabay.text().strip()}
            status_lbl = self.lbl_status_pb

        status_lbl.setText("Mengecek...")
        status_lbl.setStyleSheet("color: #94a3b8;")
        worker = _TestWorker(key_name, values)
        worker.result.connect(self._on_test_result)
        self._workers.append(worker)
        worker.start()

    def _on_test_result(self, key_name: str, ok: bool, msg: str):
        if key_name == "vertex_ai":
            status = self.lbl_status_vertex
        elif key_name == "pexels_api_key":
            status = self.lbl_status_px
        else:
            status = self.lbl_status_pb
        status.setText(msg)
        status.setStyleSheet(f"color: {'#10b981' if ok else '#ef4444'};")

    def _fetch_remote_models(self):
        worker = _FetchModelsWorker(
            self.inp_json.text().strip(),
            self.chk_preview.isChecked(),
        )
        worker.result.connect(self._on_models_fetched)
        self._workers.append(worker)
        worker.start()

    def _on_models_fetched(self, models, error):
        if error:
            QMessageBox.warning(self, "Gagal", error)
            return

        self._apply_model_choices(models)
        QMessageBox.information(self, "Berhasil", f"{len(models)} model dimuat.")

    def _detect_encoder(self, force: bool):
        self.lbl_encoder_status.setText("Mendeteksi encoder render...")
        self.lbl_encoder_status.setStyleSheet("color: #94a3b8;")
        worker = _DetectEncoderWorker(force=force)
        worker.result.connect(self._on_encoder_detected)
        self._workers.append(worker)
        worker.start()

    def _on_encoder_detected(self, payload: dict):
        self._encoder_detection = dict(payload or {})
        self._refresh_encoder_status_label(payload)
        if payload.get("error"):
            QMessageBox.warning(self, "Deteksi Encoder", payload.get("status", "Gagal mendeteksi encoder."))

    def _refresh_encoder_status_label(self, payload: dict):
        self._encoder_detection = dict(payload or self._encoder_detection or {})
        detected = str(payload.get("detected", "") or "").strip() or "-"
        status = str(payload.get("status", "Belum dicek") or "Belum dicek").strip()
        mode = self.cmb_video_encoder.currentData() if hasattr(self, "cmb_video_encoder") else "auto"
        prefix = f"Mode: {mode} | Deteksi: {detected}"
        self.lbl_encoder_status.setText(f"{prefix}\n{status}")
        is_ok = detected in {"h264_qsv", "libx264"}
        if mode == "h264_qsv" and detected != "h264_qsv":
            color = "#f59e0b"
        else:
            color = "#10b981" if is_ok else "#f59e0b"
        self.lbl_encoder_status.setStyleSheet(f"color: {color};")

    def _save(self):
        from core.settings_manager import settings

        key_path = self.inp_json.text().strip()
        project_id = settings.infer_project_id_from_key_path(key_path)
        if not key_path:
            QMessageBox.warning(self, "Error", "Pilih file Service Account JSON terlebih dahulu.")
            return
        if not project_id:
            QMessageBox.warning(self, "Error", "project_id tidak ditemukan di file Service Account JSON.")
            return

        settings.set_many(
            {
                "ai_provider": "vertex_ai",
                "gcp_key_path": key_path,
                "gcp_project_id": project_id,
                "gcp_location": settings.get_vertex_location(),
                "projects_root": self.inp_projects_root.text().strip(),
                "default_broll_source": self.cmb_default_source.currentData() or "pexels",
                "pexels_api_key": self.inp_pexels.text().strip(),
                "pixabay_api_key": self.inp_pixabay.text().strip(),
                "allow_preview_models": self.chk_preview.isChecked(),
                "model_profile": self.cmb_profile.currentData(),
                "gemini_model_text": self.cmb_model_planner.currentText(),
                "gemini_model_transcribe": self.cmb_model_transcribe.currentText(),
                "gemini_model_planner": self.cmb_model_planner.currentText(),
                "gemini_model_vision": self.cmb_model_vision.currentText(),
                "gemini_model_video": self.cmb_model_video.currentText(),
                "gemini_model_tts": self.cmb_model_tts.currentText(),
                "video_encoder_mode": self.cmb_video_encoder.currentData() or "auto",
            }
        )
        QMessageBox.information(
            self,
            "Tersimpan",
            f"Pengaturan tersimpan.\nProject: {project_id}\nRegion: global",
        )
        self.accept()
