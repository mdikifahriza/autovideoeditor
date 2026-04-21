from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtCore import Qt, Signal, QUrl, QThread
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from core.tts_provider import AVAILABLE_TTS_VOICES, GeminiTTSProvider
from gui.ui_theme import set_widget_props
import os
import time

class TTSPreviewWorker(QThread):
    finished = Signal(str)
    error = Signal(str)

    def __init__(self, voice_name: str):
        super().__init__()
        self.voice_name = voice_name

    def run(self):
        try:
            cache_dir = os.path.join("cache", "tts_preview")
            os.makedirs(cache_dir, exist_ok=True)
            output_path = os.path.join(cache_dir, f"{self.voice_name.lower()}.wav")
            
            if os.path.exists(output_path) and os.path.getsize(output_path) > 1024:
                self.finished.emit(output_path)
                return
                
            provider = GeminiTTSProvider()
            sample_text = f"Halo, saya adalah suara {self.voice_name}. Saya siap membacakan naskah video Anda dengan gaya dan intonasi yang natural."
            result = provider.synthesize(sample_text, output_path, voice_name=self.voice_name)
            
            if result and result.get("audio_path") and os.path.exists(result["audio_path"]):
                self.finished.emit(result["audio_path"])
            else:
                self.error.emit("Gagal membuat sampel suara.")
        except Exception as e:
            self.error.emit(str(e))


class ScriptRefinePanel(QWidget):
    back_requested = Signal()
    continue_requested = Signal(object)
    refine_requested = Signal(str, str) # prompt, current_script

    def __init__(self):
        super().__init__()
        self._payload = {}
        self._build_ui()

    def _build_ui(self):
        self.player = None
        self.audio_output = None
        
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(12)

        hero = QFrame()
        hero_layout = QHBoxLayout(hero)
        hero_layout.setContentsMargins(8, 4, 8, 4)
        hero_layout.setSpacing(16)

        title = self._make_label("Refine Script", "heroTitle")
        hero_layout.addWidget(title)
        
        self.lbl_project = self._make_label("Proyek: -", "toolbarMeta")
        hero_layout.addWidget(self.lbl_project)

        self.lbl_mode = self._make_label("Mode: -", "statusChip")
        hero_layout.addWidget(self.lbl_mode)
        
        hero_layout.addStretch(1)

        self._make_label("Suara TTS", "subTitle")
        self.voice_combo = QComboBox()
        self.voice_combo.setMinimumHeight(32)
        self.voice_combo.addItems(AVAILABLE_TTS_VOICES)
        hero_layout.addWidget(self._make_label("Suara TTS:", "subTitle"))
        hero_layout.addWidget(self.voice_combo)
        
        self.btn_play_voice = QPushButton("▶ Play")
        self.btn_play_voice.setMinimumHeight(32)
        set_widget_props(self.btn_play_voice, variant="ghost")
        self.btn_play_voice.clicked.connect(self._on_play_voice_clicked)
        hero_layout.addWidget(self.btn_play_voice)

        root.addWidget(hero)

        body_card = QFrame()
        body_layout = QHBoxLayout(body_card)
        body_layout.setContentsMargins(8, 4, 8, 4)
        body_layout.setSpacing(12)
        root.addWidget(body_card, 1)

        left_column = QVBoxLayout()
        left_column.setSpacing(12)
        body_layout.addLayout(left_column, 1)

        title_card = QFrame()
        title_layout = QVBoxLayout(title_card)
        title_layout.setContentsMargins(0, 0, 0, 0)
        title_layout.setSpacing(8)
        title_layout.addWidget(self._make_label("Judul / topik", "sectionTitle"))

        self.title_input = QLineEdit()
        self.title_input.setMinimumHeight(36)
        self.title_input.setPlaceholderText("Judul script")
        title_layout.addWidget(self.title_input)
        left_column.addWidget(title_card)

        self.research_card = QFrame()
        research_layout = QVBoxLayout(self.research_card)
        research_layout.setContentsMargins(0, 0, 0, 0)
        research_layout.setSpacing(8)
        self.research_label = self._make_label("Hasil Riset Google", "sectionTitle")
        research_layout.addWidget(self.research_label)

        self.research_input = QTextEdit()
        self.research_input.setReadOnly(True)
        self.research_input.setMinimumHeight(120)
        set_widget_props(self.research_input, role="mutedSurface")
        research_layout.addWidget(self.research_input)
        left_column.addWidget(self.research_card)

        editor_card = QFrame()
        editor_layout = QVBoxLayout(editor_card)
        editor_layout.setContentsMargins(0, 0, 0, 0)
        editor_layout.setSpacing(8)
        editor_layout.addWidget(self._make_label("Script final", "sectionTitle"))

        self.script_input = QTextEdit()
        self.script_input.setMinimumHeight(240)
        set_widget_props(self.script_input, role="editorSurface")
        editor_layout.addWidget(self.script_input)

        self.refine_widget = QWidget()
        refine_layout = QHBoxLayout(self.refine_widget)
        refine_layout.setContentsMargins(0, 0, 0, 0)
        refine_layout.setSpacing(8)
        
        self.refine_input = QLineEdit()
        self.refine_input.setPlaceholderText("Ketik instruksi AI untuk mengubah teks ini (contoh: 'tambah 2 kalimat')")
        self.refine_input.setMinimumHeight(36)
        refine_layout.addWidget(self.refine_input, 1)
        
        self.btn_refine = QPushButton("Refine dengan AI")
        self.btn_refine.setMinimumHeight(36)
        set_widget_props(self.btn_refine, variant="secondary")
        self.btn_refine.clicked.connect(self._on_refine_clicked)
        refine_layout.addWidget(self.btn_refine, 0)

        editor_layout.addWidget(self.refine_widget)

        left_column.addWidget(editor_card, 1)

        actions = QWidget()
        actions_layout = QHBoxLayout(actions)
        actions_layout.setContentsMargins(8, 8, 8, 8)
        actions_layout.setSpacing(12)

        btn_back = QPushButton("Kembali")
        btn_back.setMinimumHeight(46)
        set_widget_props(btn_back, variant="ghost")
        btn_back.clicked.connect(self.back_requested.emit)
        actions_layout.addWidget(btn_back)

        actions_layout.addStretch(1)

        self.btn_continue = QPushButton("Lanjutkan & Buat Voice Over")
        self.btn_continue.setMinimumHeight(50)
        set_widget_props(self.btn_continue, variant="primary")
        self.btn_continue.clicked.connect(self._on_continue)
        actions_layout.addWidget(self.btn_continue)
        root.addWidget(actions)

        self.research_card.hide()

    def _make_label(self, text: str, role: str) -> QLabel:
        label = QLabel(text)
        return set_widget_props(label, role=role)

    def _make_wrapped_label(self, text: str, role: str) -> QLabel:
        label = self._make_label(text, role)
        label.setWordWrap(True)
        return label

    def load_script(self, payload: dict):
        self._payload = dict(payload or {})
        project_name = self._payload.get("project_name", "-")
        project_mode = self._payload.get("project_mode", "voiceover")
        
        self.refine_widget.setVisible(project_mode == "full_auto")
        title = self._payload.get("title", "") or self._payload.get("project_name", "")
        script_text = self._payload.get("script_text", "")
        selected_voice = self._payload.get("tts_voice", AVAILABLE_TTS_VOICES[0])
        research_pack = self._payload.get("research_pack", {})

        self.lbl_mode.setText(f"Mode: {project_mode}")
        self.lbl_project.setText(f"Proyek: {project_name}")
        self.title_input.setText(title)
        self.script_input.setPlainText(script_text)
        index = self.voice_combo.findText(selected_voice)
        self.voice_combo.setCurrentIndex(index if index >= 0 else 0)

        if research_pack and research_pack.get("research_text"):
            self.research_card.show()
            self.research_label.show()
            self.research_input.show()
            self.research_input.setPlainText(research_pack.get("research_text"))
            self.script_input.setMinimumHeight(170)
        else:
            self.research_card.hide()
            self.research_label.hide()
            self.research_input.hide()
            self.research_input.clear()
            self.script_input.setMinimumHeight(240)

    def _on_refine_clicked(self):
        prompt = self.refine_input.text().strip()
        current_script = self.script_input.toPlainText().strip()
        if not prompt or not current_script:
            return
        
        self.btn_refine.setEnabled(False)
        self.refine_input.setEnabled(False)
        self.refine_requested.emit(prompt, current_script)
        
    def refine_finished(self, result_text: str):
        self.btn_refine.setEnabled(True)
        self.refine_input.setEnabled(True)
        if result_text:
            self.script_input.setPlainText(result_text)
            self.refine_input.clear()

    def _on_play_voice_clicked(self):
        voice_name = self.voice_combo.currentText().strip()
        if not voice_name:
            return
            
        if self.player:
            if self.player.playbackState() == QMediaPlayer.PlayingState:
                self.player.stop()
                self.btn_play_voice.setText("▶ Play")
                return

        self.btn_play_voice.setText("⌛ Memuat...")
        self.btn_play_voice.setEnabled(False)
        
        self.preview_worker = TTSPreviewWorker(voice_name)
        self.preview_worker.finished.connect(self._on_preview_ready)
        self.preview_worker.error.connect(self._on_preview_error)
        self.preview_worker.start()

    def _on_preview_ready(self, audio_path: str):
        self.btn_play_voice.setEnabled(True)
        self.btn_play_voice.setText("⏸ Stop")
        
        if not self.player:
            self.player = QMediaPlayer()
            self.audio_output = QAudioOutput()
            self.player.setAudioOutput(self.audio_output)
            self.audio_output.setVolume(1.0)
            self.player.playbackStateChanged.connect(self._on_player_state_changed)
            
        self.player.setSource(QUrl.fromLocalFile(audio_path))
        self.player.play()

    def _on_player_state_changed(self, state):
        if state in (QMediaPlayer.StoppedState, QMediaPlayer.PausedState):
            self.btn_play_voice.setText("▶ Play")

    def _on_preview_error(self, err: str):
        self.btn_play_voice.setEnabled(True)
        self.btn_play_voice.setText("▶ Play")
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.warning(self, "Preview Gagal", f"Gagal memutar sampel suara:\n\n{err}")

    def _on_continue(self):
        title = self.title_input.text().strip()
        script_text = self.script_input.toPlainText().strip()
        if not title:
            title = self._payload.get("project_name", "").strip()
        if not script_text:
            return
        payload = dict(self._payload)
        payload["title"] = title
        payload["script_text"] = script_text
        payload["tts_voice"] = self.voice_combo.currentText().strip() or AVAILABLE_TTS_VOICES[0]
        self.continue_requested.emit(payload)
