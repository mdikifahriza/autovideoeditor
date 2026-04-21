"""
gui/segment_card.py

Inspector card for a single review segment.
"""

from __future__ import annotations

import os

from PySide6.QtCore import Qt, Signal, QThread
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from config import AVAILABLE_EFFECTS, AVAILABLE_GRADES, AVAILABLE_TRANSITIONS
from core.asset_manager import create_video_thumbnail, import_media_to_project
from gui.ui_theme import set_widget_props

FLOATING_TEXT_MODES = [
    ("Ikuti global", "inherit"),
    ("Paksa aktif", "enabled"),
    ("Matikan segmen ini", "disabled"),
]


def _format_seconds(seconds: float) -> str:
    total_seconds = max(0, int(round(float(seconds or 0))))
    minutes, secs = divmod(total_seconds, 60)
    return f"{minutes:02d}:{secs:02d}"


class VeoGenerateWorker(QThread):
    finished = Signal(list)
    error = Signal(str)

    def __init__(self, query: str, duration: float, output_dir: str):
        super().__init__()
        self.query = query
        self.duration = duration
        self.output_dir = output_dir

    def run(self):
        try:
            from core.broll_fetcher import _generate_veo
            videos = _generate_veo(self.query, self.duration, self.output_dir)
            if not videos:
                self.error.emit("Tidak ada video yang dihasilkan oleh Veo.")
            else:
                self.finished.emit(videos)
        except Exception as e:
            self.error.emit(str(e))

class SegmentCard(QFrame):
    rerender_clicked = Signal(int)
    segment_changed = Signal(int, str, object)

    def __init__(self, segment: dict, output_dir: str | None = None):
        super().__init__()
        self.segment = segment
        self.output_dir = output_dir
        self._thumb_source_pixmap = QPixmap()
        self._confirmation_override = True

        self.setFrameShape(QFrame.NoFrame)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        set_widget_props(self, role="nestedCard")

        self._build_ui()
        self.refresh_from_segment()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(16)

        root.addWidget(self._build_header_card())
        root.addWidget(self._make_divider())
        root.addWidget(self._build_broll_card())
        root.addWidget(self._make_divider())
        root.addWidget(self._build_settings_card())
        root.addWidget(self._make_divider())
        root.addWidget(self._build_text_card())
        root.addWidget(self._make_divider())
        root.addWidget(self._build_actions_card())

    def _make_divider(self) -> QFrame:
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        line.setStyleSheet("background-color: #1f2e49;")
        return line

    def _build_header_card(self) -> QWidget:
        seg = self.segment
        natural_duration = self._natural_duration()

        card = QWidget()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(12)

        top_row = QHBoxLayout()
        top_row.setSpacing(12)

        title_col = QVBoxLayout()
        title_col.setSpacing(2)

        eyebrow = QLabel("Review Segment")
        set_widget_props(eyebrow, role="eyebrow")
        title_col.addWidget(eyebrow)

        self.lbl_title = QLabel(f"Segmen {int(seg.get('id', 0)) + 1}")
        set_widget_props(self.lbl_title, role="sectionTitle")
        title_col.addWidget(self.lbl_title)

        self.lbl_timing = QLabel(
            f"{_format_seconds(seg.get('start', 0))} - {_format_seconds(seg.get('end', 0))}"
            f" | {natural_duration:.1f}s"
        )
        set_widget_props(self.lbl_timing, role="helper")
        title_col.addWidget(self.lbl_timing)

        top_row.addLayout(title_col, 1)

        chip_col = QVBoxLayout()
        chip_col.setSpacing(8)
        self.lbl_confirm_chip = QLabel()
        self.lbl_asset_chip = QLabel()
        chip_col.addWidget(self.lbl_confirm_chip, 0, Qt.AlignRight)
        chip_col.addWidget(self.lbl_asset_chip, 0, Qt.AlignRight)
        top_row.addLayout(chip_col)
        layout.addLayout(top_row)

        self.lbl_warning = QLabel("")
        self.lbl_warning.setWordWrap(True)
        self.lbl_warning.setTextInteractionFlags(Qt.TextSelectableByMouse)
        set_widget_props(self.lbl_warning, role="infoBanner", tone="danger")
        self.lbl_warning.hide()
        layout.addWidget(self.lbl_warning)

        transcript_title = QLabel("Transcript")
        set_widget_props(transcript_title, role="subTitle")
        layout.addWidget(transcript_title)

        self.lbl_transcript = QLabel("")
        self.lbl_transcript.setWordWrap(True)
        self.lbl_transcript.setTextInteractionFlags(Qt.TextSelectableByMouse)
        set_widget_props(self.lbl_transcript, role="transcriptBox")
        layout.addWidget(self.lbl_transcript)

        return card

    def _build_broll_card(self) -> QWidget:
        card = QWidget()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(12)

        title = QLabel("Visual B-roll")
        set_widget_props(title, role="subTitle")
        layout.addWidget(title)

        self.thumb_shell = QFrame()
        set_widget_props(self.thumb_shell, role="videoShell")
        thumb_layout = QVBoxLayout(self.thumb_shell)
        thumb_layout.setContentsMargins(10, 10, 10, 10)
        thumb_layout.setSpacing(0)

        self.thumb_label = QLabel("Preview belum tersedia")
        self.thumb_label.setAlignment(Qt.AlignCenter)
        self.thumb_label.setMinimumHeight(176)
        self.thumb_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        set_widget_props(self.thumb_label, role="previewMeta")
        thumb_layout.addWidget(self.thumb_label)
        layout.addWidget(self.thumb_shell)

        self.lbl_source = QLabel("")
        self.lbl_source.setWordWrap(True)
        self.lbl_source.setTextInteractionFlags(Qt.TextSelectableByMouse)
        set_widget_props(self.lbl_source, role="helper")
        layout.addWidget(self.lbl_source)

        button_col = QVBoxLayout()
        button_col.setSpacing(6)

        self.btn_choose_broll = QPushButton("Pilih Pexels/Pixabay")
        set_widget_props(self.btn_choose_broll, variant="primary")
        self.btn_choose_broll.clicked.connect(self._on_choose_existing_broll)
        button_col.addWidget(self.btn_choose_broll)

        self.btn_veo = QPushButton("Generate dengan Veo")
        set_widget_props(self.btn_veo, variant="secondary")
        self.btn_veo.clicked.connect(self._on_generate_veo)
        button_col.addWidget(self.btn_veo)

        self.btn_import_local = QPushButton("Import File")
        set_widget_props(self.btn_import_local, variant="secondary")
        self.btn_import_local.clicked.connect(self._on_use_local_video)
        button_col.addWidget(self.btn_import_local)

        layout.addLayout(button_col)

        self.btn_retry_download = QPushButton("Download Video Ini")
        set_widget_props(self.btn_retry_download, variant="danger")
        self.btn_retry_download.clicked.connect(self._on_retry_download)
        self.btn_retry_download.hide()
        layout.addWidget(self.btn_retry_download)

        return card

    def _build_settings_card(self) -> QWidget:
        card = QWidget()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(14)

        title = QLabel("Visual Settings")
        set_widget_props(title, role="subTitle")
        layout.addWidget(title)

        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)
        grid.setColumnStretch(1, 1)

        self.spin_duration = QDoubleSpinBox()
        self.spin_duration.setRange(1.0, 90.0)
        self.spin_duration.setSingleStep(0.5)
        self.spin_duration.setSuffix(" s")
        self.spin_duration.valueChanged.connect(
            lambda value: self._emit_named_change("render_duration", float(value))
        )
        self._add_form_row(grid, 0, "Durasi", self.spin_duration)

        self.cmb_effect = self._make_combo(AVAILABLE_EFFECTS)
        self.cmb_effect.currentTextChanged.connect(
            lambda value: self._emit_named_change("effect", value)
        )
        self._add_form_row(grid, 1, "Efek", self.cmb_effect)

        self.cmb_trans_in = self._make_combo(AVAILABLE_TRANSITIONS)
        self.cmb_trans_in.currentTextChanged.connect(
            lambda value: self._emit_named_change("transition_in", value)
        )
        self._add_form_row(grid, 2, "Transisi masuk", self.cmb_trans_in)

        self.cmb_trans_out = self._make_combo(AVAILABLE_TRANSITIONS)
        self.cmb_trans_out.currentTextChanged.connect(
            lambda value: self._emit_named_change("transition_out", value)
        )
        self._add_form_row(grid, 3, "Transisi keluar", self.cmb_trans_out)

        self.cmb_grade = self._make_combo(AVAILABLE_GRADES)
        self.cmb_grade.currentTextChanged.connect(
            lambda value: self._emit_named_change("color_grade", value)
        )
        self._add_form_row(grid, 4, "Color grade", self.cmb_grade)

        layout.addLayout(grid)
        return card

    def _build_text_card(self) -> QWidget:
        card = QWidget()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(14)

        title = QLabel("Floating Text")
        set_widget_props(title, role="subTitle")
        layout.addWidget(title)

        self.emphasis_input = QLineEdit()
        self.emphasis_input.setPlaceholderText("Teks penekanan segmen ini")
        self.emphasis_input.textChanged.connect(
            lambda value: self._emit_named_change("emphasis_text", value.strip() or None)
        )
        layout.addWidget(self.emphasis_input)

        self.cmb_floating_mode = QComboBox()
        for label, value in FLOATING_TEXT_MODES:
            self.cmb_floating_mode.addItem(label, value)
        self.cmb_floating_mode.currentIndexChanged.connect(
            lambda _index: self._emit_named_change(
                "floating_text_mode",
                self.cmb_floating_mode.currentData() or "inherit",
            )
        )
        layout.addWidget(self.cmb_floating_mode)

        return card

    def _build_actions_card(self) -> QWidget:
        card = QWidget()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(12)

        row = QHBoxLayout()
        row.setSpacing(10)

        self.btn_confirm = QPushButton()
        self.btn_confirm.setCheckable(True)
        self.btn_confirm.toggled.connect(self._on_confirm_toggled)
        row.addWidget(self.btn_confirm, 1)

        self.btn_rerender = QPushButton("Render Preview")
        set_widget_props(self.btn_rerender, variant="secondary")
        self.btn_rerender.clicked.connect(
            lambda: self.rerender_clicked.emit(int(self.segment.get("id", 0)))
        )
        row.addWidget(self.btn_rerender)

        layout.addLayout(row)

        self.lbl_confirm_lock = QLabel("")
        self.lbl_confirm_lock.setWordWrap(True)
        set_widget_props(self.lbl_confirm_lock, role="helper")
        layout.addWidget(self.lbl_confirm_lock)

        self.chk_confirm = QCheckBox("Konfirmasi segmen ini")
        self.chk_confirm.hide()
        layout.addWidget(self.chk_confirm)

        return card

    def _add_form_row(self, grid: QGridLayout, row: int, label_text: str, widget: QWidget):
        label = QLabel(label_text)
        set_widget_props(label, role="body")
        grid.addWidget(label, row, 0)
        grid.addWidget(widget, row, 1)

    def _make_combo(self, options: list[str]) -> QComboBox:
        combo = QComboBox()
        combo.addItems(options)
        return combo

    def _natural_duration(self) -> float:
        return max(
            1.0,
            float(self.segment.get("end", 0) or 0) - float(self.segment.get("start", 0) or 0),
        )

    def _resolve_candidate_path(self, candidate: dict | None, abs_key: str, rel_key: str) -> str:
        if not isinstance(candidate, dict):
            return ""
        abs_path = str(candidate.get(abs_key, "") or "").strip()
        if abs_path and os.path.exists(abs_path):
            return abs_path
        rel_path = str(candidate.get(rel_key, "") or "").strip()
        if rel_path and self.output_dir:
            joined = os.path.join(self.output_dir, rel_path)
            if os.path.exists(joined):
                return joined
        return abs_path or ""

    def _has_video(self) -> bool:
        chosen = self.segment.get("broll_chosen")
        local_path = self._resolve_candidate_path(chosen, "local_path", "project_local_path")
        return bool(local_path and os.path.exists(local_path))

    def _set_combo_text(self, combo: QComboBox, value: str):
        index = combo.findText(value)
        if index >= 0:
            combo.setCurrentIndex(index)

    def _set_combo_data(self, combo: QComboBox, value: str):
        index = combo.findData(value)
        combo.setCurrentIndex(index if index >= 0 else 0)

    def _sync_status_chips(self):
        confirmed = bool(self.segment.get("confirmed", False))
        confirm_text = "Confirmed" if confirmed else "Needs confirm"
        confirm_tone = "success" if confirmed else "warning"
        self.lbl_confirm_chip.setText(confirm_text)
        set_widget_props(self.lbl_confirm_chip, role="statusChip", tone=confirm_tone)

        if self._has_video():
            asset_text = "Video siap"
            asset_tone = "success"
        else:
            asset_text = "Belum ada video"
            asset_tone = "danger"
        self.lbl_asset_chip.setText(asset_text)
        set_widget_props(self.lbl_asset_chip, role="statusChip", tone=asset_tone)

    def _sync_confirm_button(self):
        confirmed = bool(self.segment.get("confirmed", False))
        has_video = self._has_video()
        can_confirm = bool(self._confirmation_override and has_video)

        self.btn_confirm.blockSignals(True)
        self.btn_confirm.setChecked(confirmed)
        self.btn_confirm.blockSignals(False)

        self.chk_confirm.blockSignals(True)
        self.chk_confirm.setChecked(confirmed)
        self.chk_confirm.blockSignals(False)

        self.btn_confirm.setEnabled(can_confirm)
        self.chk_confirm.setEnabled(can_confirm)
        self.btn_confirm.setText("Sudah dikonfirmasi" if confirmed else "Konfirmasi segmen")
        state = "confirmed" if confirmed else "pending"
        set_widget_props(self.btn_confirm, variant="confirm", state=state)

        if not has_video:
            self.lbl_confirm_lock.setText("Konfirmasi tersedia setelah video segmen siap.")
            self.lbl_confirm_lock.show()
        elif not self._confirmation_override:
            self.lbl_confirm_lock.setText("Konfirmasi segmen sedang dinonaktifkan.")
            self.lbl_confirm_lock.show()
        else:
            self.lbl_confirm_lock.hide()

    def _sync_warning_state(self):
        has_video = self._has_video()
        error_text = str(self.segment.get("broll_load_error", "") or "").strip()
        failed = bool(self.segment.get("broll_load_failed", False))

        warning = ""
        if not has_video:
            warning = "File video untuk segmen ini belum ada."
        if failed:
            warning = f"Gagal mengunduh B-roll. {error_text}"
        
        if warning:
            self.lbl_warning.setText(warning)
            self.lbl_warning.show()
            self.btn_retry_download.show()
        else:
            self.lbl_warning.hide()
            self.btn_retry_download.hide()

    def _emit_named_change(self, field: str, value):
        self.segment[field] = value
        if field == "confirmed":
            self._sync_confirm_button()
            self._sync_status_chips()
        self.segment_changed.emit(int(self.segment.get("id", 0)), field, value)

    def _on_confirm_toggled(self, checked: bool):
        self._emit_named_change("confirmed", bool(checked))

    def refresh_from_segment(self):
        seg = self.segment
        natural_duration = self._natural_duration()
        render_duration = float(seg.get("render_duration", natural_duration) or natural_duration)

        self.lbl_title.setText(f"Segmen {int(seg.get('id', 0)) + 1}")
        self.lbl_timing.setText(
            f"{_format_seconds(seg.get('start', 0))} - {_format_seconds(seg.get('end', 0))}"
            f" | {render_duration:.1f}s"
        )
        transcript = str(seg.get("transcript", "") or "").strip() or "-"
        self.lbl_transcript.setText(transcript)

        self.spin_duration.blockSignals(True)
        self.spin_duration.setValue(render_duration)
        self.spin_duration.blockSignals(False)

        self.cmb_effect.blockSignals(True)
        self._set_combo_text(self.cmb_effect, str(seg.get("effect", "static") or "static"))
        self.cmb_effect.blockSignals(False)

        self.cmb_trans_in.blockSignals(True)
        self._set_combo_text(
            self.cmb_trans_in, str(seg.get("transition_in", "cut") or "cut")
        )
        self.cmb_trans_in.blockSignals(False)

        self.cmb_trans_out.blockSignals(True)
        self._set_combo_text(
            self.cmb_trans_out, str(seg.get("transition_out", "cut") or "cut")
        )
        self.cmb_trans_out.blockSignals(False)

        self.cmb_grade.blockSignals(True)
        self._set_combo_text(
            self.cmb_grade, str(seg.get("color_grade", "neutral") or "neutral")
        )
        self.cmb_grade.blockSignals(False)

        self.emphasis_input.blockSignals(True)
        self.emphasis_input.setText(str(seg.get("emphasis_text", "") or ""))
        self.emphasis_input.blockSignals(False)

        self.cmb_floating_mode.blockSignals(True)
        self._set_combo_data(
            self.cmb_floating_mode,
            str(seg.get("floating_text_mode", "inherit") or "inherit"),
        )
        self.cmb_floating_mode.blockSignals(False)

        self._refresh_broll_preview()
        self._sync_warning_state()
        self._sync_status_chips()
        self._sync_confirm_button()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._apply_thumb_pixmap()

    def _refresh_broll_preview(self):
        chosen = self.segment.get("broll_chosen")
        thumb_path = self._resolve_candidate_path(chosen, "thumbnail_path", "project_thumbnail_path")
        if thumb_path and os.path.exists(thumb_path):
            pixmap = QPixmap(thumb_path)
            if not pixmap.isNull():
                self._thumb_source_pixmap = pixmap
                self.thumb_label.setText("")
                self._apply_thumb_pixmap()
            else:
                self._set_thumb_placeholder()
        else:
            self._set_thumb_placeholder()

        if isinstance(chosen, dict):
            source = str(chosen.get("source", "unknown") or "unknown").strip()
            duration = chosen.get("duration")
            width = chosen.get("width")
            height = chosen.get("height")
            local_path = self._resolve_candidate_path(chosen, "local_path", "project_local_path")
            parts = [f"Source: {source}"]
            if duration not in (None, ""):
                parts.append(f"Durasi: {duration}s")
            if width and height:
                parts.append(f"Resolusi: {width}x{height}")
            if local_path:
                parts.append(os.path.basename(local_path))
            self.lbl_source.setText(" | ".join(parts))
        else:
            self.lbl_source.setText("Belum ada B-roll terpilih untuk segmen ini.")

    def _set_thumb_placeholder(self):
        self._thumb_source_pixmap = QPixmap()
        self.thumb_label.setPixmap(QPixmap())
        self.thumb_label.setText("Preview belum tersedia")

    def _apply_thumb_pixmap(self):
        if self._thumb_source_pixmap.isNull():
            return
        target_width = max(1, self.thumb_label.width() - 2)
        target_height = max(1, self.thumb_label.height() - 2)
        scaled = self._thumb_source_pixmap.scaled(
            target_width,
            target_height,
            Qt.KeepAspectRatioByExpanding,
            Qt.SmoothTransformation,
        )
        self.thumb_label.setPixmap(scaled)

    def _on_retry_download(self):
        chosen = self.segment.get("broll_chosen")
        if not isinstance(chosen, dict):
            QMessageBox.warning(self, "Error", "Tidak ada video yang dipilih untuk di-retry.")
            return
        try:
            from core.broll_fetcher import ensure_segment_video_available

            QMessageBox.information(self, "Retry", "Mencoba download ulang video segmen.")
            local_path = ensure_segment_video_available(
                self.segment,
                project_dir=self.output_dir or "",
                progress_cb=None,
                log_cb=None,
            )
            if local_path and os.path.exists(local_path):
                self.segment["broll_load_failed"] = False
                self.segment.pop("broll_load_error", None)
                updated_choice = self.segment.get("broll_chosen")
                self.segment_changed.emit(
                    int(self.segment.get("id", 0)),
                    "broll_chosen",
                    updated_choice,
                )
                self.refresh_from_segment()
                QMessageBox.information(self, "Sukses", "Video berhasil di-download ulang.")
                return
            QMessageBox.warning(self, "Gagal", "Retry download gagal. Coba pilih video lain.")
        except Exception as exc:
            QMessageBox.warning(self, "Error", f"Retry gagal: {exc}")

    def _on_generate_veo(self):
        query = self.segment.get("query", "") or self.segment.get("transcript", "")
        if not query:
            QMessageBox.warning(self, "Error", "Tidak ada query untuk Veo.")
            return
            
        self.btn_veo.setEnabled(False)
        self.btn_veo.setText("Membangkitkan...")
        
        self.veo_worker = VeoGenerateWorker(
            query=query, 
            duration=self.segment.get("render_duration", 5.0),
            output_dir=self.output_dir or ""
        )
        self.veo_worker.finished.connect(self._on_veo_done)
        self.veo_worker.error.connect(self._on_veo_error)
        self.veo_worker.start()

    def _on_veo_done(self, videos: list):
        self.btn_veo.setEnabled(True)
        self.btn_veo.setText("Generate dengan Veo")
        
        if not videos:
            return
            
        veo_vid = videos[0]
        local_path = veo_vid.get("local_path")
        
        if local_path and os.path.exists(local_path) and self.output_dir:
            try:
                from core.asset_manager import create_video_thumbnail
                thumb_asset = create_video_thumbnail(local_path, self.output_dir)
                if thumb_asset:
                    veo_vid["thumbnail_path"] = thumb_asset.get("absolute_path")
                    veo_vid["project_thumbnail_path"] = thumb_asset.get("relative_path")
            except Exception as e:
                print(f"Gagal membuat thumbnail veo: {e}")
                
        self.segment["broll_chosen"] = veo_vid
        
        candidates = self.segment.get("broll_candidates", [])
        if candidates is None:
            candidates = []
            
        candidates.insert(0, veo_vid)
        self.segment["broll_candidates"] = candidates
        
        self.segment["broll_load_failed"] = False
        self.segment["broll_load_error"] = None
        self.refresh_from_segment()
        self.changed.emit(int(self.segment.get("id", 0)), "broll_chosen", veo_vid)

    def _on_veo_error(self, err: str):
        self.btn_veo.setEnabled(True)
        self.btn_veo.setText("Generate dengan Veo")
        QMessageBox.warning(self, "Veo Error", f"Gagal generate Veo:\n\n{err}")

    def _on_choose_existing_broll(self):
        from gui.broll_browser import BrollBrowser

        candidates = self.segment.get("broll_candidates", [])
        if not candidates:
            QMessageBox.information(
                self,
                "Info",
                "Tidak ada kandidat B-roll lain untuk segmen ini.",
            )
            return

        dialog = BrollBrowser(candidates, self.segment.get("broll_chosen"), self)
        if dialog.exec() == BrollBrowser.Accepted and dialog.selected_broll:
            self.segment["broll_chosen"] = dialog.selected_broll
            self.segment["broll_load_failed"] = False
            self.segment.pop("broll_load_error", None)
            self.segment_changed.emit(
                int(self.segment.get("id", 0)),
                "broll_chosen",
                dialog.selected_broll,
            )
            self.refresh_from_segment()

    def _on_use_local_video(self):
        if not self.output_dir:
            QMessageBox.warning(self, "Error", "Folder proyek belum siap untuk impor media lokal.")
            return

        path, _ = QFileDialog.getOpenFileName(
            self,
            "Pilih video lokal",
            "",
            "Video Files (*.mp4 *.mov *.mkv *.avi)",
        )
        if not path:
            return

        try:
            media_asset = import_media_to_project(path, self.output_dir, "custom_broll")
            thumb_asset = create_video_thumbnail(
                media_asset["absolute_path"],
                self.output_dir,
                "custom_broll",
                f"thumb_seg_{self.segment['id']}",
            )

            duration = None
            width = None
            height = None
            try:
                from moviepy import VideoFileClip

                clip = VideoFileClip(media_asset["absolute_path"], audio=False)
                duration = round(float(clip.duration or 0), 2)
                width, height = clip.size
                clip.close()
            except Exception:
                pass

            candidate = {
                "id": f"local_seg_{self.segment['id']}_{media_asset['filename']}",
                "source": "local",
                "video_url": "",
                "thumbnail_url": "",
                "thumbnail_path": thumb_asset["absolute_path"] if thumb_asset else None,
                "project_thumbnail_path": thumb_asset["relative_path"] if thumb_asset else None,
                "local_path": media_asset["absolute_path"],
                "project_local_path": media_asset["relative_path"],
                "duration": duration,
                "width": width,
                "height": height,
            }
            self.segment.setdefault("broll_candidates", []).insert(0, candidate)
            self.segment["broll_chosen"] = candidate
            self.segment["broll_load_failed"] = False
            self.segment.pop("broll_load_error", None)
            self.segment_changed.emit(
                int(self.segment.get("id", 0)),
                "broll_chosen",
                candidate,
            )
            self.refresh_from_segment()
        except Exception as exc:
            QMessageBox.warning(self, "Error", f"Gagal mengimpor video lokal:\n{exc}")

    def get_current_values(self) -> dict:
        return {
            "render_duration": float(self.spin_duration.value()),
            "effect": self.cmb_effect.currentText(),
            "transition_in": self.cmb_trans_in.currentText(),
            "transition_out": self.cmb_trans_out.currentText(),
            "color_grade": self.cmb_grade.currentText(),
            "emphasis_text": self.emphasis_input.text().strip() or None,
            "floating_text_mode": self.cmb_floating_mode.currentData() or "inherit",
            "confirmed": self.btn_confirm.isChecked(),
        }

    def set_confirmation_enabled(self, enabled: bool):
        self._confirmation_override = bool(enabled)
        self._sync_confirm_button()

    def set_confirmed_state(self, confirmed: bool):
        self.segment["confirmed"] = bool(confirmed)
        self.refresh_from_segment()
