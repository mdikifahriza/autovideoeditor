from __future__ import annotations

import os

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from core.cache_manager import get_output_cache_paths
from core.planner import save_plan
from core.project_manager import set_project_stage
from gui.segment_card import SegmentCard
from gui.ui_theme import set_widget_props

INSPECTOR_WIDTH = 300
TIMELINE_HEIGHT = 140


def _format_time(seconds: float) -> str:
    total_seconds = max(0, int(round(float(seconds or 0))))
    minutes, secs = divmod(total_seconds, 60)
    return f"{minutes:02d}:{secs:02d}"


class GPUOverlayWidget(QWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WA_TranslucentBackground)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(0)

        self.floating_lbl = QLabel("")
        self.floating_lbl.setAlignment(Qt.AlignCenter)
        self.floating_lbl.setWordWrap(True)
        self.floating_lbl.setStyleSheet(
            "color: #f6e64c; font-size: 28px; font-weight: 900;"
            "background: transparent;"
        )
        self.floating_lbl.hide()

        layout.addStretch(1)
        layout.addWidget(self.floating_lbl, 0, Qt.AlignCenter)
        layout.addStretch(1)

        self.subtitle_lbl = QLabel("")
        self.subtitle_lbl.setAlignment(Qt.AlignCenter)
        self.subtitle_lbl.setWordWrap(True)
        self.subtitle_lbl.setStyleSheet(
            "color: #ffffff; font-size: 18px; font-weight: 800;"
            "background-color: rgba(0, 0, 0, 150); padding: 8px 14px; border-radius: 10px;"
        )
        self.subtitle_lbl.hide()
        layout.addWidget(self.subtitle_lbl, 0, Qt.AlignHCenter | Qt.AlignBottom)

    def update_text(self, subtitle: str, floating: str):
        subtitle = str(subtitle or "").strip()
        floating = str(floating or "").strip()

        if subtitle:
            self.subtitle_lbl.setText(subtitle)
            self.subtitle_lbl.show()
        else:
            self.subtitle_lbl.hide()

        if floating:
            self.floating_lbl.setText(floating)
            self.floating_lbl.show()
        else:
            self.floating_lbl.hide()


class ReviewPanel(QWidget):
    rerender_requested = Signal(int)
    final_render_requested = Signal()
    preview_refresh_requested = Signal(int)
    state_changed = Signal()
    global_settings_changed = Signal(bool, bool)
    back_to_home_requested = Signal()
    download_missing_requested = Signal(list)

    def __init__(self):
        super().__init__()
        self.plan = None
        self.audio_path = None
        self.output_dir = None
        self.selected_segment_index = -1
        self.segment_buttons: list[QPushButton] = []
        self.segment_card: SegmentCard | None = None

        self._subtitle_enabled = False
        self._floating_enabled = False

        self._play_all_mode = False
        self._current_play_index = -1
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        header = QFrame()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(8, 4, 8, 4)
        header_layout.setSpacing(12)

        title = QLabel("Preview Canvas")
        set_widget_props(title, role="heroTitle")
        header_layout.addWidget(title)
        
        header_layout.addStretch(1)

        chip_col = QHBoxLayout()
        chip_col.setSpacing(10)
        self.selected_chip = QLabel("Segmen belum dipilih")
        self.review_chip = QLabel("0 / 0 dikonfirmasi")
        set_widget_props(self.selected_chip, role="statusChip", tone="warning")
        set_widget_props(self.review_chip, role="statusChip", tone="warning")
        chip_col.addWidget(self.selected_chip, 0, Qt.AlignRight)
        chip_col.addWidget(self.review_chip, 0, Qt.AlignRight)
        header_layout.addLayout(chip_col)
        root.addWidget(header)

        self.main_splitter = QSplitter(Qt.Vertical)
        self.main_splitter.setChildrenCollapsible(False)
        self.main_splitter.setHandleWidth(2)
        root.addWidget(self.main_splitter, 1)

        self.top_splitter = QSplitter(Qt.Horizontal)
        self.top_splitter.setChildrenCollapsible(False)
        self.top_splitter.setHandleWidth(2)

        self.center_panel = self._build_center_panel()
        self.right_panel = self._build_right_panel()
        self.top_splitter.addWidget(self.center_panel)
        self.top_splitter.addWidget(self.right_panel)
        self.top_splitter.setSizes([700, INSPECTOR_WIDTH])
        self.top_splitter.setStretchFactor(0, 1)
        self.top_splitter.setStretchFactor(1, 0)

        self.bottom_panel = self._build_bottom_panel()
        self.main_splitter.addWidget(self.top_splitter)
        self.main_splitter.addWidget(self.bottom_panel)
        self.main_splitter.setSizes([640, TIMELINE_HEIGHT])
        self.main_splitter.setStretchFactor(0, 1)
        self.main_splitter.setStretchFactor(1, 0)

        root.addWidget(self._build_status_bar())

        self.media_player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.media_player.setAudioOutput(self.audio_output)
        self.media_player.setVideoOutput(self.preview_video_host)
        self.media_player.positionChanged.connect(self._on_player_position_changed)
        self.media_player.mediaStatusChanged.connect(self._on_media_status_changed)

        self.btn_play.clicked.connect(self._on_play_clicked)
        self.btn_stop.clicked.connect(self._on_stop_clicked)

    def _build_center_panel(self) -> QWidget:
        panel = QFrame()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        shell = set_widget_props(QFrame(), role="videoShell")
        shell_layout = QVBoxLayout(shell)
        shell_layout.setContentsMargins(4, 4, 4, 4)
        shell_layout.setSpacing(12)

        self.video_container = QWidget()
        self.video_container.setStyleSheet("background:#040b15; border-radius: 18px;")
        self.video_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        video_layout = QVBoxLayout(self.video_container)
        video_layout.setContentsMargins(0, 0, 0, 0)
        video_layout.setSpacing(0)

        self.preview_video_host = QVideoWidget()
        self.preview_video_host.setStyleSheet("background:#040b15; border:none;")
        self.preview_video_host.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        video_layout.addWidget(self.preview_video_host)

        self.overlay_widget = GPUOverlayWidget(self.video_container)
        shell_layout.addWidget(self.video_container, 1)

        controls = set_widget_props(QFrame(), role="toolbarGroup")
        controls_layout = QVBoxLayout(controls)
        controls_layout.setContentsMargins(16, 14, 16, 14)
        controls_layout.setSpacing(12)

        self.preview_timeline = QProgressBar()
        self.preview_timeline.setRange(0, 1000)
        self.preview_timeline.setValue(0)
        self.preview_timeline.setTextVisible(False)
        self.preview_timeline.setFixedHeight(12)
        controls_layout.addWidget(self.preview_timeline)

        row = QHBoxLayout()
        row.setSpacing(10)

        self.btn_play = QPushButton("Putar Segmen")
        set_widget_props(self.btn_play, variant="primary")
        self.btn_play.setMinimumWidth(110)
        self.btn_play.clicked.connect(self._on_play_clicked)
        row.addWidget(self.btn_play)
        
        self.btn_play_all = QPushButton("Putar Semua")
        set_widget_props(self.btn_play_all, variant="secondary")
        self.btn_play_all.clicked.connect(self._on_play_all_clicked)
        row.addWidget(self.btn_play_all)

        self.btn_stop = QPushButton("Berhenti")
        set_widget_props(self.btn_stop, variant="secondary")
        self.btn_stop.setMinimumWidth(110)
        row.addWidget(self.btn_stop)

        self.seg_info = QLabel("00:00 / 00:00")
        set_widget_props(self.seg_info, role="statusChip")
        row.addWidget(self.seg_info, 0, Qt.AlignVCenter)

        row.addStretch(1)
        controls_layout.addLayout(row)

        shell_layout.addWidget(controls)
        layout.addWidget(shell, 1)
        return panel

    def _build_right_panel(self) -> QWidget:
        panel = QFrame()
        panel.setMinimumWidth(240)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        layout.addWidget(set_widget_props(QLabel("Inspector Segmen"), role="sectionTitle"))

        self.right_scroll = QScrollArea()
        self.right_scroll.setWidgetResizable(True)
        self.right_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.right_container = QWidget()
        self.right_layout = QVBoxLayout(self.right_container)
        self.right_layout.setContentsMargins(0, 0, 0, 0)
        self.right_layout.setSpacing(14)
        self.right_layout.addStretch(1)
        self.right_scroll.setWidget(self.right_container)
        layout.addWidget(self.right_scroll, 1)
        return panel

    def _build_bottom_panel(self) -> QWidget:
        panel = QFrame()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        header_row = QHBoxLayout()
        header_row.setSpacing(12)

        title_col = QVBoxLayout()
        title_col.setSpacing(4)
        title_col.addWidget(set_widget_props(QLabel("Timeline Review"), role="sectionTitle"))
        
        header_row.addLayout(title_col, 1)

        self.segment_count_label = QLabel("0 segmen")
        set_widget_props(self.segment_count_label, role="statusChip")
        header_row.addWidget(self.segment_count_label, 0, Qt.AlignTop)
        layout.addLayout(header_row)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        container = QWidget()
        self.timeline_layout = QHBoxLayout(container)
        self.timeline_layout.setContentsMargins(0, 0, 0, 0)
        self.timeline_layout.setSpacing(12)
        self.timeline_layout.setAlignment(Qt.AlignLeft)
        scroll.setWidget(container)
        layout.addWidget(scroll, 1)
        return panel

    def _build_status_bar(self) -> QWidget:
        card = QFrame()
        layout = QHBoxLayout(card)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(10)

        self.btn_back_home = QPushButton("Kembali")
        set_widget_props(self.btn_back_home, variant="ghost")
        self.btn_back_home.clicked.connect(self.back_to_home_requested.emit)
        layout.addWidget(self.btn_back_home)

        self.status_msg = QLabel("")
        self.status_msg.setWordWrap(True)
        set_widget_props(self.status_msg, role="body")
        layout.addWidget(self.status_msg, 1)

        self.btn_toggle_subtitle = QPushButton("Subtitle: OFF")
        self.btn_toggle_subtitle.setCheckable(True)
        set_widget_props(self.btn_toggle_subtitle, variant="toolbarToggle")
        self.btn_toggle_subtitle.toggled.connect(self._on_toggle_subtitle)
        layout.addWidget(self.btn_toggle_subtitle)

        self.btn_toggle_floating = QPushButton("Teks: OFF")
        self.btn_toggle_floating.setCheckable(True)
        set_widget_props(self.btn_toggle_floating, variant="toolbarToggle")
        self.btn_toggle_floating.toggled.connect(self._on_toggle_floating)
        layout.addWidget(self.btn_toggle_floating)

        self.lbl_summary = QLabel("")
        set_widget_props(self.lbl_summary, role="toolbarMeta")
        layout.addWidget(self.lbl_summary)

        self.btn_download_all = QPushButton("📥 Download Kosong")
        set_widget_props(self.btn_download_all, variant="toolbar")
        self.btn_download_all.clicked.connect(self._on_download_missing)
        self.btn_download_all.hide()
        layout.addWidget(self.btn_download_all)

        self.btn_confirm_all = QPushButton("Konfirmasi Semua")
        set_widget_props(self.btn_confirm_all, variant="primary")
        self.btn_confirm_all.clicked.connect(self.confirm_all_segments)
        self.btn_confirm_all.setEnabled(False)
        layout.addWidget(self.btn_confirm_all)

        self.btn_render_final = QPushButton("Render Final")
        set_widget_props(self.btn_render_final, variant="toolbarPrimary")
        self.btn_render_final.clicked.connect(self.final_render_requested.emit)
        self.btn_render_final.hide()
        layout.addWidget(self.btn_render_final)

        return card

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "overlay_widget") and hasattr(self, "video_container"):
            self.overlay_widget.resize(self.video_container.size())

    def load_plan(self, plan: dict, audio_path: str, output_dir: str):
        self.plan = plan
        self.audio_path = audio_path
        self.output_dir = output_dir

        segments = self.plan.get("segments", [])
        self.segment_count_label.setText(f"{len(segments)} segmen")
        self._build_timeline(segments)
        self._update_review_summary()
        self.state_changed.emit()

        if segments:
            self._show_segment(0)
        else:
            self.selected_segment_index = -1
            self.status_msg.setText("Edit plan belum memiliki segmen.")
        self._check_all_confirmed()

    def _build_timeline(self, segments: list[dict]):
        while self.timeline_layout.count():
            item = self.timeline_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        self.segment_buttons.clear()

        for index, segment in enumerate(segments):
            button = QPushButton()
            button.setCheckable(True)
            button.clicked.connect(lambda checked, idx=index: self._show_segment(idx))
            set_widget_props(button, variant="timeline")
            self.timeline_layout.addWidget(button)
            self.segment_buttons.append(button)
            self._refresh_timeline_button(index, selected=False)

        self.timeline_layout.addStretch(1)

    def _segment_button_text(self, index: int, segment: dict) -> str:
        duration = float(segment.get("render_duration") or 0) or max(
            1.0,
            float(segment.get("end", 0) or 0) - float(segment.get("start", 0) or 0),
        )
        
        has_video = bool(self._resolve_segment_video_path(segment))
        if not has_video:
            status = "Kosong"
        else:
            status = "Dikonfirmasi" if segment.get("confirmed", False) else "Perlu cek"
            
        transcript = str(segment.get("transcript", "") or "").strip().replace("\n", " ")
        if len(transcript) > 42:
            transcript = transcript[:39].rstrip() + "..."
        transcript = transcript or "Belum ada transcript"
        return f"Segmen {index + 1}\n{duration:.1f} dtk | {status}\n{transcript}"

    def _refresh_timeline_button(self, index: int, selected: bool):
        if not self.plan or index < 0 or index >= len(self.segment_buttons):
            return
        segment = self.plan.get("segments", [])[index]
        button = self.segment_buttons[index]
        button.setChecked(selected)
        button.setText(self._segment_button_text(index, segment))
        
        state = "pending"
        if not bool(self._resolve_segment_video_path(segment)):
            state = "missing"
        elif segment.get("confirmed", False):
            state = "confirmed"
            
        set_widget_props(
            button,
            variant="timeline",
            state=state,
            selected="true" if selected else "false",
        )

    def _show_segment(self, index: int):
        if self._play_all_mode and self._current_play_index != index:
            self._play_all_mode = False
            self.btn_play_all.setText("Putar Semua")
            
        if not self.plan or index < 0 or index >= len(self.plan.get("segments", [])):
            return

        self.selected_segment_index = index
        segment = self.plan["segments"][index]

        for button_index in range(len(self.segment_buttons)):
            self._refresh_timeline_button(button_index, selected=(button_index == index))

        if self.segment_card:
            self.right_layout.removeWidget(self.segment_card)
            self.segment_card.deleteLater()

        self.segment_card = SegmentCard(segment, self.output_dir)
        self.segment_card.segment_changed.connect(self._on_segment_changed)
        self.right_layout.insertWidget(0, self.segment_card)

        self.selected_chip.setText(f"Segmen {index + 1} dari {len(self.plan.get('segments', []))}")
        set_widget_props(self.selected_chip, role="statusChip", tone="success")
        self.status_msg.setText(
            f"Sedang meninjau segmen {index + 1}. Atur visual di inspector lalu konfirmasi jika sudah cocok."
        )
        self._load_segment_media(segment)
        self._sync_overlay(self.media_player.position())
        self._update_review_summary()

    def _resolve_segment_video_path(self, segment: dict) -> str:
        chosen = segment.get("broll_chosen")
        if not isinstance(chosen, dict):
            return ""

        direct_path = str(chosen.get("local_path", "") or "").strip()
        if direct_path and os.path.exists(direct_path):
            return direct_path

        relative_path = str(chosen.get("project_local_path", "") or "").strip()
        if relative_path and self.output_dir:
            joined = os.path.join(self.output_dir, relative_path)
            if os.path.exists(joined):
                return joined
        return ""

    def _load_segment_media(self, segment: dict):
        video_path = self._resolve_segment_video_path(segment)
        if video_path:
            self.media_player.setSource(QUrl.fromLocalFile(video_path))
            self.media_player.play()
            self.btn_play.setText("Jeda Segmen")
        else:
            self.media_player.stop()
            self.media_player.setSource(QUrl())
            self.preview_timeline.setValue(0)
            self.seg_info.setText("00:00 / 00:00")
            self.btn_play.setText("Putar Segmen")
            self.overlay_widget.update_text("", "Pilih B-roll terlebih dahulu")

    def _on_player_position_changed(self, position_ms: int):
        duration_ms = self.media_player.duration()
        if duration_ms > 0:
            self.preview_timeline.setValue(int((position_ms / duration_ms) * 1000))
            self.seg_info.setText(
                f"{_format_time(position_ms / 1000.0)} / {_format_time(duration_ms / 1000.0)}"
            )
        self._sync_overlay(position_ms)

    def _sync_overlay(self, position_ms: int):
        if not self.plan or self.selected_segment_index < 0:
            return

        segment = self.plan["segments"][self.selected_segment_index]
        subtitle = segment.get("transcript", "") if self._subtitle_enabled else ""
        floating = segment.get("emphasis_text", "") if self._floating_enabled else ""
        self.overlay_widget.update_text(subtitle, floating)

    def _on_play_all_clicked(self):
        if not self.plan or not self.plan.get("segments"):
            return
            
        if self._play_all_mode and self.media_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.media_player.pause()
            self.btn_play_all.setText("Putar Semua")
            self.btn_play.setText("Putar Segmen")
            return
            
        if self._play_all_mode and self.media_player.playbackState() == QMediaPlayer.PlaybackState.PausedState:
            self.media_player.play()
            self.btn_play_all.setText("Jeda Semua")
            self.btn_play.setText("Jeda Segmen")
            return
            
        self._play_all_mode = True
        self._current_play_index = 0
        self.btn_play_all.setText("Jeda Semua")
        self._play_segment_at(0)

    def _play_segment_at(self, index: int):
        segments = self.plan.get("segments", [])
        if index < 0 or index >= len(segments):
            self._play_all_mode = False
            self.btn_play_all.setText("Putar Semua")
            return
            
        self._current_play_index = index
        self.btn_play.setText("Putar Segmen")
        
        self._show_segment(index)
        
        if self.media_player.source().isEmpty():
            self.status_msg.setText(f"Putar Semua dihentikan di Segmen {index + 1} karena source video kosong.")
            self._play_all_mode = False
            self.btn_play_all.setText("Putar Semua")
            return
            
        self.media_player.play()
        
    def _on_media_status_changed(self, status):
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            if self._play_all_mode:
                next_index = self._current_play_index + 1
                if next_index < len(self.plan.get("segments", [])):
                    self._play_segment_at(next_index)
                else:
                    self._play_all_mode = False
                    self.btn_play_all.setText("Putar Semua")
                    self.btn_play.setText("Putar Segmen")
                    self.preview_timeline.setValue(0)
            else:
                self.btn_play.setText("Putar Segmen")
                self.preview_timeline.setValue(0)

    def _on_play_clicked(self):
        self._play_all_mode = False
        self.btn_play_all.setText("Putar Semua")
        
        if self.media_player.source().isEmpty():
            self.status_msg.setText("Segmen ini belum punya source visual. Pilih B-roll dahulu.")
            return

        if self.media_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.media_player.pause()
            self.btn_play.setText("Putar Segmen")
        else:
            self.media_player.play()
            self.btn_play.setText("Jeda Segmen")

    def _on_stop_clicked(self):
        self._play_all_mode = False
        self.btn_play_all.setText("Putar Semua")
        self.media_player.stop()
        self.btn_play.setText("Putar Segmen")
        self.preview_timeline.setValue(0)

    def _on_toggle_subtitle(self, checked: bool):
        self.btn_toggle_subtitle.setText(f"Subtitle: {'ON' if checked else 'OFF'}")
        self.set_subtitle_enabled(checked, trigger_refresh=True)

    def _on_toggle_floating(self, checked: bool):
        self.btn_toggle_floating.setText(f"Teks: {'ON' if checked else 'OFF'}")
        self.set_floating_text_enabled(checked, trigger_refresh=True)

    def get_subtitle_enabled(self) -> bool:
        return self._subtitle_enabled

    def set_subtitle_enabled(self, enabled: bool, trigger_refresh: bool = False):
        self._subtitle_enabled = bool(enabled)
        self._sync_overlay(self.media_player.position())
        if trigger_refresh:
            self.global_settings_changed.emit(self._subtitle_enabled, self._floating_enabled)

    def get_floating_text_enabled(self) -> bool:
        return self._floating_enabled

    def set_floating_text_enabled(self, enabled: bool, trigger_refresh: bool = False):
        self._floating_enabled = bool(enabled)
        self._sync_overlay(self.media_player.position())
        if trigger_refresh:
            self.global_settings_changed.emit(self._subtitle_enabled, self._floating_enabled)

    def update_preview_status(self, ready_count: int, total: int, available_duration: float, message: str):
        self.status_msg.setText("Preview realtime aktif. Pilih segmen untuk mengecek hasil edit.")

    def update_draft_video(self, video_path: str, activate: bool = True):
        return

    def show_rerender_progress(self, total: int):
        return

    def update_rerender_progress(self, current: int, total: int):
        return

    def hide_rerender_progress(self):
        return

    def hide_inline_error(self):
        return

    def _on_segment_changed(self, segment_index: int, field: str, value):
        if not self.plan or segment_index < 0 or segment_index >= len(self.plan.get("segments", [])):
            return

        segment = self.plan["segments"][segment_index]
        if field == "confirmed":
            segment["confirmed"] = bool(value)
        elif field == "broll_chosen":
            segment["broll_chosen"] = value
            segment["broll_load_failed"] = False
            segment.pop("broll_load_error", None)
        elif field == "broll_retry":
            pass
        elif field == "render_duration":
            segment["render_duration"] = float(value or 0)
        elif field in {"effect", "effect_name"}:
            segment["effect"] = value
        elif field == "transition_in":
            segment["transition_in"] = value
        elif field == "transition_out":
            segment["transition_out"] = value
        elif field == "color_grade":
            segment["color_grade"] = value
        elif field == "emphasis_text":
            segment["emphasis_text"] = value
        elif field == "floating_text_mode":
            segment["floating_text_mode"] = value
        elif field == "subtitle_style":
            segment["subtitle_style"] = value
        elif field in {"floating_text_anim", "floating_text_animation"}:
            segment["floating_text_animation"] = value
        elif field in {"floating_text_pos", "floating_text_position"}:
            segment["floating_text_position"] = value
        elif field == "scale_factor":
            segment["scale_factor"] = value

        self._save_plan_async()
        self._refresh_timeline_button(segment_index, selected=(segment_index == self.selected_segment_index))

        if segment_index == self.selected_segment_index:
            if field in {"broll_chosen", "broll_retry"}:
                if self.segment_card:
                    self.segment_card.refresh_from_segment()
                self._load_segment_media(segment)
            elif field == "confirmed" and self.segment_card:
                self.segment_card.set_confirmed_state(bool(value))

        self._check_all_confirmed()
        self._update_review_summary()
        self._sync_overlay(self.media_player.position())
        self.state_changed.emit()

    def _save_plan_async(self):
        if not self.output_dir or not self.plan:
            return
        paths = get_output_cache_paths(self.output_dir)
        save_plan(self.plan, paths["plan"])

    def confirm_all_segments(self):
        if not self.plan:
            return

        for index, segment in enumerate(self.plan.get("segments", [])):
            segment["confirmed"] = True
            self._refresh_timeline_button(index, selected=(index == self.selected_segment_index))

        if self.segment_card:
            self.segment_card.set_confirmed_state(True)

        self._save_plan_async()
        self._check_all_confirmed()
        self._update_review_summary()
        self.status_msg.setText("Semua segmen sudah dikonfirmasi. Render final siap dijalankan.")
        self.state_changed.emit()

    def _on_download_missing(self):
        missing_indices = []
        for index, segment in enumerate(self.plan.get("segments", [])):
            if not self._resolve_segment_video_path(segment):
                missing_indices.append(index)
        
        if not missing_indices:
            self.status_msg.setText("Tidak ada klip kosong untuk diunduh.")
            return
            
        self.status_msg.setText(f"Memicu download untuk {len(missing_indices)} segmen...")
        self.btn_download_all.setEnabled(False)
        self.download_missing_requested.emit(missing_indices)

    def _check_all_confirmed(self):
        if not self.plan:
            self.btn_confirm_all.show()
            self.btn_confirm_all.setEnabled(False)
            self.btn_render_final.hide()
            self.btn_download_all.hide()
            return

        missing_count = sum(1 for segment in self.plan.get("segments", []) if not self._resolve_segment_video_path(segment))
        if missing_count > 0:
            self.btn_download_all.setText(f"📥 Download ({missing_count})")
            self.btn_download_all.show()
            self.btn_download_all.setEnabled(True)
        else:
            self.btn_download_all.hide()

        all_confirmed = all(
            segment.get("confirmed", False) for segment in self.plan.get("segments", [])
        )
        if all_confirmed:
            self.btn_confirm_all.hide()
            self.btn_render_final.show()
            if self.output_dir:
                set_project_stage(self.output_dir, "validation", "completed")
        else:
            self.btn_confirm_all.show()
            self.btn_confirm_all.setEnabled(True)
            self.btn_render_final.hide()

    def _update_review_summary(self):
        if not self.plan:
            self.review_chip.setText("0 / 0 dikonfirmasi")
            set_widget_props(self.review_chip, role="statusChip", tone="warning")
            self.lbl_summary.setText("")
            return

        segments = self.plan.get("segments", [])
        total = len(segments)
        confirmed = sum(1 for segment in segments if segment.get("confirmed", False))
        dur = sum(float(s.get("render_duration", 0) or 0) for s in segments)
        
        self.review_chip.setText(f"{confirmed} / {total} dikonfirmasi")
        tone = "success" if total and confirmed == total else "warning"
        set_widget_props(self.review_chip, role="statusChip", tone=tone)

        self.lbl_summary.setText(f"{total} seg | {confirmed} siap | {dur:.0f} dtk")
