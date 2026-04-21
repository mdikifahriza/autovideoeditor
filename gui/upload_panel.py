import os

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from core.project_manager import get_default_projects_root
from gui.ui_theme import repolish, set_widget_props


class UploadPanel(QWidget):
    start_clicked = Signal(object)
    project_opened = Signal(str)

    def __init__(self):
        super().__init__()
        self._actions_compact = None
        self._build_ui()

    def _build_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        root_layout.addWidget(scroll)

        content = QWidget()
        scroll.setWidget(content)

        layout = QVBoxLayout(content)
        layout.setAlignment(Qt.AlignTop | Qt.AlignHCenter)
        layout.setSpacing(18)
        layout.setContentsMargins(24, 24, 24, 32)

        hero_card = set_widget_props(QFrame(), role="heroCard")
        hero_card.setMaximumWidth(1080)
        hero_layout = QVBoxLayout(hero_card)
        hero_layout.setSpacing(12)
        hero_layout.setContentsMargins(16, 16, 16, 16)

        eyebrow = self._make_label("Project Intake", "eyebrow")
        eyebrow.setAlignment(Qt.AlignCenter)
        hero_layout.addWidget(eyebrow)

        title = self._make_label("Auto Video Editor by M. Diki Fahriza", "heroTitle")
        title.setAlignment(Qt.AlignCenter)
        title.setWordWrap(True)
        hero_layout.addWidget(title)

        chip_row = QHBoxLayout()
        chip_row.setSpacing(10)
        chip_row.addStretch(1)
        chip_row.addWidget(self._make_chip("Voice Over"))
        chip_row.addWidget(self._make_chip("Semi Auto"))
        chip_row.addWidget(self._make_chip("Full Auto"))
        chip_row.addStretch(1)
        hero_layout.addLayout(chip_row)
        layout.addWidget(hero_card)

        workspace = set_widget_props(QFrame(), role="panelCard")
        workspace.setMaximumWidth(1080)
        workspace_layout = QVBoxLayout(workspace)
        workspace_layout.setSpacing(18)
        workspace_layout.setContentsMargins(26, 26, 26, 26)
        layout.addWidget(workspace)

        intro_card = set_widget_props(QFrame(), role="subCard")
        intro_layout = QVBoxLayout(intro_card)
        intro_layout.setSpacing(8)
        intro_layout.setContentsMargins(20, 20, 20, 20)
        intro_layout.addWidget(self._make_label("Mulai Proyek Baru", "sectionTitle"))

        intro = self._make_label(
            "Semua proyek akan berujung ke voice over aktif. Untuk mode script, kamu akan refine naskah dulu lalu AI membuat suara sebelum pipeline utama dimulai.",
            "body",
        )
        intro.setWordWrap(True)
        intro_layout.addWidget(intro)
        workspace_layout.addWidget(intro_card)

        basics_card = set_widget_props(QFrame(), role="subCard")
        basics_layout = QVBoxLayout(basics_card)
        basics_layout.setSpacing(12)
        basics_layout.setContentsMargins(12, 12, 12, 12)
        basics_layout.addWidget(self._make_label("Identitas Proyek", "sectionTitle"))
        basics_layout.addWidget(self._field_label("Nama proyek"))

        self.project_name_input = QLineEdit()
        self.project_name_input.setPlaceholderText("Contoh: Konten Motivasi Episode 1")
        self.project_name_input.textChanged.connect(self._update_start_button)
        self.project_name_input.setMinimumHeight(36)
        basics_layout.addWidget(self.project_name_input)

        self.projects_root_label = self._make_banner("")
        self.projects_root_label.setWordWrap(True)
        basics_layout.addWidget(self.projects_root_label)
        workspace_layout.addWidget(basics_card)

        mode_card = QFrame()
        mode_layout = QVBoxLayout(mode_card)
        mode_layout.setSpacing(12)
        mode_layout.setContentsMargins(12, 12, 12, 12)
        mode_layout.addWidget(self._make_label("Mode Proyek", "sectionTitle"))

        self.project_mode_group = QButtonGroup(self)
        self.btn_mode_voiceover = QRadioButton("Voice Over")
        self.btn_mode_semi = QRadioButton("Semi Auto")
        self.btn_mode_full = QRadioButton("Full Auto")
        self.btn_mode_voiceover.setChecked(True)

        from core.settings_manager import settings

        saved_project_mode = settings.get("project_mode", "voiceover")
        if saved_project_mode == "semi_auto":
            self.btn_mode_semi.setChecked(True)
        elif saved_project_mode == "full_auto":
            self.btn_mode_full.setChecked(True)

        self.project_mode_group.addButton(self.btn_mode_voiceover, 1)
        self.project_mode_group.addButton(self.btn_mode_semi, 2)
        self.project_mode_group.addButton(self.btn_mode_full, 3)

        project_mode_box = self._build_radio_group(
            self.btn_mode_voiceover,
            self.btn_mode_semi,
            self.btn_mode_full,
        )
        for radio in (self.btn_mode_voiceover, self.btn_mode_semi, self.btn_mode_full):
            radio.toggled.connect(self._on_mode_changed)
        mode_layout.addWidget(project_mode_box)
        workspace_layout.addWidget(mode_card)

        review_card = QFrame()
        review_layout = QVBoxLayout(review_card)
        review_layout.setSpacing(12)
        review_layout.setContentsMargins(12, 12, 12, 12)
        review_layout.addWidget(self._make_label("Profil Review", "sectionTitle"))

        self.review_group = QButtonGroup(self)
        self.btn_review_fast = QRadioButton("Draft Cepat")
        self.btn_review_standard = QRadioButton("Review Standar")
        self.btn_review_full = QRadioButton("Review Penuh")
        self.btn_review_standard.setChecked(True)

        saved_review_profile = settings.get("review_profile", "standard")
        if saved_review_profile == "draft_fast":
            self.btn_review_fast.setChecked(True)
        elif saved_review_profile == "full_review":
            self.btn_review_full.setChecked(True)

        self.review_group.addButton(self.btn_review_fast, 1)
        self.review_group.addButton(self.btn_review_standard, 2)
        self.review_group.addButton(self.btn_review_full, 3)
        review_layout.addWidget(
            self._build_radio_group(
                self.btn_review_fast,
                self.btn_review_standard,
                self.btn_review_full,
            )
        )
        workspace_layout.addWidget(review_card)

        self.mode_stack_host = QWidget()
        self.mode_stack_layout = QVBoxLayout(self.mode_stack_host)
        self.mode_stack_layout.setContentsMargins(0, 0, 0, 0)
        self.mode_stack_layout.setSpacing(14)

        self.voiceover_box = self._build_voiceover_box()
        self.semi_auto_box = self._build_semi_auto_box()
        self.full_auto_box = self._build_full_auto_box()
        self.mode_stack_layout.addWidget(self.voiceover_box)
        self.mode_stack_layout.addWidget(self.semi_auto_box)
        self.mode_stack_layout.addWidget(self.full_auto_box)
        workspace_layout.addWidget(self.mode_stack_host)

        launch_card = set_widget_props(QFrame(), role="subCard")
        launch_layout = QVBoxLayout(launch_card)
        launch_layout.setSpacing(14)
        launch_layout.setContentsMargins(20, 20, 20, 20)
        launch_layout.addWidget(self._make_label("Status & Mulai", "sectionTitle"))

        self.status_label = self._make_banner("Isi data sesuai mode proyek yang dipilih terlebih dahulu.")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setWordWrap(True)
        launch_layout.addWidget(self.status_label)

        self.btn_start = QPushButton("Buat Proyek dan Mulai")
        self.btn_start.setMinimumHeight(56)
        self.btn_start.setEnabled(False)
        set_widget_props(self.btn_start, variant="primary")
        self.btn_start.clicked.connect(self._on_start)
        launch_layout.addWidget(self.btn_start)
        workspace_layout.addWidget(launch_card)

        self.action_box = QFrame()
        action_layout = QVBoxLayout(self.action_box)
        action_layout.setContentsMargins(12, 12, 12, 12)
        action_layout.setSpacing(12)
        action_layout.addWidget(self._make_label("Akses Proyek", "sectionTitle"))

        self.action_grid = QGridLayout()
        self.action_grid.setContentsMargins(0, 0, 0, 0)
        self.action_grid.setHorizontalSpacing(12)
        self.action_grid.setVerticalSpacing(12)
        action_layout.addLayout(self.action_grid)

        self.btn_back_home = QPushButton("Kembali ke Beranda")
        self.btn_back_home.setMinimumHeight(48)
        self.btn_back_home.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        set_widget_props(self.btn_back_home, variant="secondary")
        # will be connected in app.py

        self.btn_clear_cache = QPushButton("Bersihkan Cache MP4")
        self.btn_clear_cache.setMinimumHeight(48)
        self.btn_clear_cache.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        set_widget_props(self.btn_clear_cache, variant="ghost")
        self.btn_clear_cache.clicked.connect(self._on_clear_cache)

        self.lbl_cache_info = self._make_label("", "helper")
        self.lbl_cache_info.setAlignment(Qt.AlignCenter)
        self.lbl_cache_info.setWordWrap(True)
        action_layout.addWidget(self.lbl_cache_info)
        workspace_layout.addWidget(self.action_box)
        self._update_action_buttons_layout(force=True)

        layout.addStretch(1)
        self.refresh_projects_root_label()
        self._on_mode_changed()

    def _build_voiceover_box(self) -> QWidget:
        box = QFrame()
        layout = QVBoxLayout(box)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        layout.addWidget(self._make_label("Voice Over Aktif", "sectionTitle"))

        row = QHBoxLayout()
        row.setSpacing(12)

        self.mp3_input = QLineEdit()
        self.mp3_input.setPlaceholderText("Pilih file audio MP3, WAV, atau M4A")
        self.mp3_input.setReadOnly(True)
        self.mp3_input.setMinimumHeight(48)
        row.addWidget(self.mp3_input, 1)

        btn_mp3 = QPushButton("Browse")
        btn_mp3.setMinimumHeight(48)
        btn_mp3.setMinimumWidth(120)
        set_widget_props(btn_mp3, variant="secondary")
        btn_mp3.clicked.connect(self._browse_mp3)
        row.addWidget(btn_mp3, 0)
        layout.addLayout(row)

        return box

    def _build_semi_auto_box(self) -> QWidget:
        box = QFrame()
        layout = QVBoxLayout(box)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        layout.addWidget(self._make_label("Semi Auto", "sectionTitle"))

        layout.addWidget(self._field_label("Judul / topik"))
        self.semi_title_input = QLineEdit()
        self.semi_title_input.setPlaceholderText("Contoh: Kenapa Jalan Kaki 30 Menit Itu Penting")
        self.semi_title_input.setMinimumHeight(36)
        self.semi_title_input.textChanged.connect(self._update_start_button)
        layout.addWidget(self.semi_title_input)

        layout.addWidget(self._field_label("Script / teks manual"))
        self.manual_script_input = QTextEdit()
        self.manual_script_input.setMinimumHeight(150)
        self.manual_script_input.setPlaceholderText("Paste script atau narasi di sini...")
        set_widget_props(self.manual_script_input, role="editorSurface")
        self.manual_script_input.textChanged.connect(self._update_start_button)
        layout.addWidget(self.manual_script_input)
        return box

    def _build_full_auto_box(self) -> QWidget:
        box = QFrame()
        layout = QVBoxLayout(box)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        layout.addWidget(self._make_label("Full Auto", "sectionTitle"))

        layout.addWidget(self._field_label("Judul / topik"))
        self.full_title_input = QLineEdit()
        self.full_title_input.setPlaceholderText("Contoh: Kenapa Jalan Kaki 30 Menit Itu Penting")
        self.full_title_input.setMinimumHeight(36)
        self.full_title_input.textChanged.connect(self._update_start_button)
        layout.addWidget(self.full_title_input)

        layout.addWidget(self._field_label("Angle / tujuan konten"))
        self.full_angle_input = QLineEdit()
        self.full_angle_input.setPlaceholderText("Opsional: edukatif, persuasif, fakta singkat, dan sebagainya")
        self.full_angle_input.setMinimumHeight(36)
        self.full_angle_input.textChanged.connect(self._update_start_button)
        layout.addWidget(self.full_angle_input)
        return box

    def _make_label(self, text: str, role: str) -> QLabel:
        label = QLabel(text)
        return set_widget_props(label, role=role)

    def _make_wrapped_label(self, text: str, role: str) -> QLabel:
        label = self._make_label(text, role)
        label.setWordWrap(True)
        return label

    def _make_chip(self, text: str) -> QLabel:
        chip = self._make_label(text, "statusChip")
        chip.setAlignment(Qt.AlignCenter)
        return chip

    def _make_banner(self, text: str) -> QLabel:
        banner = self._make_label(text, "infoBanner")
        banner.setWordWrap(True)
        return banner

    def _field_label(self, text: str) -> QLabel:
        return self._make_label(text, "subTitle")

    def _build_radio_group(self, *buttons: QRadioButton) -> QWidget:
        box = set_widget_props(QWidget(), role="toolbarGroup")
        layout = QVBoxLayout(box)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)
        for button in buttons:
            set_widget_props(button, pill="true")
            button.setCursor(Qt.PointingHandCursor)
            button.setMinimumHeight(48)
            layout.addWidget(button)
        return box

    def _set_banner_tone(self, widget: QLabel, tone: str = ""):
        widget.setProperty("tone", tone)
        repolish(widget)

    def refresh_projects_root_label(self):
        root = get_default_projects_root()
        self.projects_root_label.setText(
            "Folder proyek global aktif:\n"
            f"{root}"
        )
        self._update_cache_info()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_action_buttons_layout()

    def _clear_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            child_layout = item.layout()
            if widget is not None:
                widget.setParent(None)
            elif child_layout is not None:
                self._clear_layout(child_layout)

    def _update_action_buttons_layout(self, force: bool = False):
        if not hasattr(self, "action_grid"):
            return

        available_width = self.action_box.width() or self.width()
        needed_width = (
            self.btn_back_home.sizeHint().width()
            + self.btn_clear_cache.sizeHint().width()
            + self.action_grid.horizontalSpacing()
            + 36
        )
        min_two_column_width = max(needed_width + 32, 520)
        use_compact = available_width < min_two_column_width
        if not force and self._actions_compact == use_compact:
            return

        self._actions_compact = use_compact
        self._clear_layout(self.action_grid)

        if use_compact:
            self.action_grid.addWidget(self.btn_back_home, 0, 0)
            self.action_grid.addWidget(self.btn_clear_cache, 1, 0)
            self.action_grid.setColumnStretch(0, 1)
            self.action_grid.setColumnStretch(1, 0)
        else:
            self.action_grid.addWidget(self.btn_back_home, 0, 0)
            self.action_grid.addWidget(self.btn_clear_cache, 0, 1)
            self.action_grid.setColumnStretch(0, 1)
            self.action_grid.setColumnStretch(1, 1)

    def _browse_mp3(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Pilih file voice over",
            "",
            "Audio Files (*.mp3 *.wav *.m4a)",
        )
        if path:
            self.mp3_input.setText(path)
            if not self.project_name_input.text().strip():
                base = os.path.splitext(os.path.basename(path))[0]
                self.project_name_input.setText(base)
            self._update_start_button()

    def _on_open_project_folder(self):
        path = QFileDialog.getExistingDirectory(
            self,
            "Buka folder proyek",
            get_default_projects_root(),
        )
        if path:
            self.project_opened.emit(path)

    def _on_open_project_archive(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Buka proyek .avep",
            get_default_projects_root(),
            "Auto Video Editor Project (*.avep)",
        )
        if path:
            self.project_opened.emit(path)

    def _on_clear_cache(self):
        from core.cache_manager import clear_cache, format_bytes
        from core.project_manager import get_default_projects_root

        removed, freed = clear_cache(None)
        projects_root = get_default_projects_root()
        if os.path.isdir(projects_root):
            target_names = {"preview", "render", "exports"}
            for root, _, files in os.walk(projects_root):
                folder_name = os.path.basename(root).lower()
                if folder_name not in target_names:
                    continue
                for file_name in files:
                    if not file_name.lower().endswith(".mp4"):
                        continue
                    path = os.path.join(root, file_name)
                    try:
                        freed += os.path.getsize(path)
                        os.remove(path)
                        removed += 1
                    except Exception:
                        pass
        self.lbl_cache_info.setText(
            f"Cache dibersihkan: {removed} file dihapus, {format_bytes(freed)} dibebaskan."
        )

    def _update_cache_info(self):
        from core.cache_manager import get_directory_size, format_bytes

        root = get_default_projects_root()
        size = get_directory_size(root) if os.path.isdir(root) else 0
        if size:
            self.lbl_cache_info.setText(
                f"Total ukuran folder proyek saat ini: {format_bytes(size)}."
            )
        else:
            self.lbl_cache_info.setText("Folder proyek masih kosong.")

    def _current_project_mode(self) -> str:
        mode_id = self.project_mode_group.checkedId()
        return {1: "voiceover", 2: "semi_auto", 3: "full_auto"}.get(mode_id, "voiceover")

    def _current_review_profile(self) -> str:
        review_id = self.review_group.checkedId()
        return {1: "draft_fast", 2: "standard", 3: "full_review"}.get(review_id, "standard")

    def _on_mode_changed(self):
        mode = self._current_project_mode()
        self.voiceover_box.setVisible(mode == "voiceover")
        self.semi_auto_box.setVisible(mode == "semi_auto")
        self.full_auto_box.setVisible(mode == "full_auto")
        self._update_start_button()

    def _on_start(self):
        payload = {
            "project_name": self.project_name_input.text().strip(),
            "project_mode": self._current_project_mode(),
            "review_profile": self._current_review_profile(),
            "audio_path": self.mp3_input.text().strip(),
            "title": "",
            "manual_script": "",
            "angle": "",
        }

        from core.settings_manager import settings

        settings.set("project_mode", payload["project_mode"])
        settings.set("review_profile", payload["review_profile"])
        review_to_legacy = {
            "draft_fast": "auto",
            "standard": "semi_manual",
            "full_review": "manual",
        }
        settings.set("processing_mode", review_to_legacy.get(payload["review_profile"], "semi_manual"))

        if not payload["project_name"]:
            QMessageBox.warning(self, "Error", "Isi nama proyek terlebih dahulu.")
            return

        if payload["project_mode"] == "voiceover":
            if not payload["audio_path"] or not os.path.exists(payload["audio_path"]):
                QMessageBox.warning(self, "Error", "Pilih file audio yang valid.")
                return
            payload["title"] = self.project_name_input.text().strip()
        elif payload["project_mode"] == "semi_auto":
            payload["title"] = self.semi_title_input.text().strip()
            payload["manual_script"] = self.manual_script_input.toPlainText().strip()
            if not payload["title"] or not payload["manual_script"]:
                QMessageBox.warning(self, "Error", "Isi judul konten dan script manual terlebih dahulu.")
                return
        else:
            payload["title"] = self.full_title_input.text().strip()
            payload["angle"] = self.full_angle_input.text().strip()
            if not payload["title"]:
                QMessageBox.warning(self, "Error", "Isi judul atau topik konten terlebih dahulu.")
                return

        self.start_clicked.emit(payload)

    def _update_start_button(self):
        project_name = self.project_name_input.text().strip()
        project_mode = self._current_project_mode()
        valid = False
        message = "Isi data sesuai mode proyek yang dipilih terlebih dahulu."

        if project_mode == "voiceover":
            mp3 = self.mp3_input.text().strip()
            valid = bool(project_name and mp3 and os.path.exists(mp3))
            if valid:
                message = "Siap membuat proyek baru dari voice over ini."
            else:
                message = "Isi nama proyek dan pilih file voice over terlebih dahulu."
        elif project_mode == "semi_auto":
            title = self.semi_title_input.text().strip()
            script_text = self.manual_script_input.toPlainText().strip()
            valid = bool(project_name and title and script_text)
            if valid:
                message = "Siap masuk ke tahap refine script dan pembuatan voice over AI."
            else:
                message = "Isi nama proyek, judul konten, dan script manual terlebih dahulu."
        else:
            title = self.full_title_input.text().strip()
            valid = bool(project_name and title)
            if valid:
                message = "Siap membuat draft script dari judul/topik lalu lanjut ke refine."
            else:
                message = "Isi nama proyek dan judul/topik konten terlebih dahulu."

        self.btn_start.setEnabled(valid)
        self.status_label.setText(message)
        self._set_banner_tone(self.status_label, "success" if valid else "")
        self._update_cache_info()
