import os
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QScrollArea, QFrame, QGridLayout, QMessageBox, QFileDialog
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap

from gui.ui_theme import set_widget_props
from core.broll_fetcher import search_new_broll
from gui.segment_card import VeoGenerateWorker
from core.asset_manager import import_media_to_project, create_video_thumbnail


class BrollCandidateCard(QFrame):
    chosen = Signal(dict)
    
    def __init__(self, candidate: dict):
        super().__init__()
        self.candidate = candidate
        self.setFrameShape(QFrame.StyledPanel)
        self.setStyleSheet("QFrame { background: #1a2332; border-radius: 12px; }")
        self.setFixedSize(200, 180)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        
        self.thumb_label = QLabel()
        self.thumb_label.setFixedSize(184, 104)
        self.thumb_label.setAlignment(Qt.AlignCenter)
        self.thumb_label.setStyleSheet("background: #0f172a; border-radius: 8px;")
        
        thumb_path = candidate.get("thumbnail_path")
        if thumb_path and os.path.exists(thumb_path):
            pixmap = QPixmap(thumb_path)
            self.thumb_label.setPixmap(pixmap.scaled(184, 104, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation))
        else:
            self.thumb_label.setText("No Preview")
            
        layout.addWidget(self.thumb_label)
        
        source = str(candidate.get("source", "unknown"))
        dur = candidate.get("duration", 0)
        info_lbl = QLabel(f"{source.capitalize()} | {dur}s")
        info_lbl.setStyleSheet("color: #94a3b8; font-size: 11px;")
        layout.addWidget(info_lbl)
        
        self.btn_choose = QPushButton("Pilih")
        set_widget_props(self.btn_choose, variant="primary")
        self.btn_choose.clicked.connect(self._on_choose)
        layout.addWidget(self.btn_choose)
        
    def _on_choose(self):
        self.chosen.emit(self.candidate)


class SelectionSegmentRow(QFrame):
    segment_chosen = Signal()
    
    def __init__(self, segment: dict, output_dir: str):
        super().__init__()
        self.segment = segment
        self.output_dir = output_dir
        self.setFrameShape(QFrame.StyledPanel)
        self.setStyleSheet("QFrame { background: #10192d; border-radius: 12px; border: 1px solid #1f2e49; margin-bottom: 10px; }")
        
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(16, 16, 16, 16)
        
        header_layout = QHBoxLayout()
        title = QLabel(f"Segmen {segment['id'] + 1} ({segment.get('render_duration', 0)}s)")
        title.setStyleSheet("font-weight: bold; font-size: 14px; color: #f8fafc;")
        
        status = QLabel("✅ Terpilih" if segment.get("broll_chosen") else "❌ Belum Memilih")
        status.setStyleSheet("color: #10b981;" if segment.get("broll_chosen") else "color: #ef4444;")
        self.status_lbl = status
        
        header_layout.addWidget(title)
        header_layout.addStretch()
        header_layout.addWidget(self.status_lbl)
        self.layout.addLayout(header_layout)
        
        transcript = QLabel(segment.get("transcript", ""))
        transcript.setWordWrap(True)
        transcript.setStyleSheet("color: #cbd5e1; font-style: italic; margin-bottom: 10px;")
        self.layout.addWidget(transcript)
        
        self.cards_layout = QHBoxLayout()
        self.layout.addLayout(self.cards_layout)
        
        self.actions_layout = QHBoxLayout()
        self.btn_load_more = QPushButton("Load More")
        self.btn_load_more.clicked.connect(self._on_load_more)
        self.btn_veo = QPushButton("Generate Veo")
        self.btn_veo.clicked.connect(self._on_veo)
        self.btn_local = QPushButton("Import Lokal")
        self.btn_local.clicked.connect(self._on_local)
        
        set_widget_props(self.btn_load_more, variant="secondary")
        set_widget_props(self.btn_veo, variant="secondary")
        set_widget_props(self.btn_local, variant="secondary")
        
        self.actions_layout.addWidget(self.btn_load_more)
        self.actions_layout.addWidget(self.btn_veo)
        self.actions_layout.addWidget(self.btn_local)
        self.actions_layout.addStretch()
        self.layout.addLayout(self.actions_layout)
        
        self._populate_cards()
        
    def _populate_cards(self):
        # clear cards
        while self.cards_layout.count():
            item = self.cards_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
                
        candidates = self.segment.get("broll_candidates", [])
        if not candidates:
            lbl = QLabel("Tidak ada kandidat B-Roll.")
            lbl.setStyleSheet("color: #94a3b8;")
            self.cards_layout.addWidget(lbl)
            return
            
        chosen_id = self.segment.get("broll_chosen", {}).get("id")
            
        for cand in candidates[:5]:
            card = BrollCandidateCard(cand)
            if cand.get("id") == chosen_id:
                card.setStyleSheet("QFrame { background: #1e3a8a; border-radius: 12px; border: 2px solid #3b82f6; }")
                card.btn_choose.setText("Terpilih")
                card.btn_choose.setEnabled(False)
            card.chosen.connect(self._on_candidate_chosen)
            self.cards_layout.addWidget(card)
            
    def _on_candidate_chosen(self, candidate):
        self.segment["broll_chosen"] = candidate
        self.status_lbl.setText("✅ Terpilih")
        self.status_lbl.setStyleSheet("color: #10b981;")
        self._populate_cards()
        self.segment_chosen.emit()
        
    def _on_load_more(self):
        query = " ".join(self.segment.get("broll_keywords", []))
        if not query:
            query = self.segment.get("transcript", "")
            
        exclude = [c.get("id") for c in self.segment.get("broll_candidates", [])]
        dur = float(self.segment.get("render_duration", 5))
        
        self.btn_load_more.setEnabled(False)
        self.btn_load_more.setText("Mencari...")
        
        import threading
        def _search():
            fresh = search_new_broll(query, dur, exclude, self.output_dir)
            return fresh
            
        # Quick inline thread for non-blocking UI (simplified for script)
        from PySide6.QtCore import QTimer
        
        def _done(fresh):
            self.btn_load_more.setEnabled(True)
            self.btn_load_more.setText("Load More")
            if fresh:
                self.segment.setdefault("broll_candidates", []).extend(fresh)
                # Keep showing latest 5 by moving them to front or just repopulate top 5
                # For simplicity, move new ones to front
                for f in reversed(fresh):
                    self.segment["broll_candidates"].insert(0, f)
                self._populate_cards()
            else:
                QMessageBox.information(self, "Info", "Tidak ada klip tambahan ditemukan.")
                
        class Worker(threading.Thread):
            def run(self):
                f = _search()
                QTimer.singleShot(0, lambda: _done(f))
                
        Worker().start()

    def _on_veo(self):
        query = self.segment.get("query", "") or self.segment.get("transcript", "")
        self.btn_veo.setEnabled(False)
        self.btn_veo.setText("Membangkitkan...")
        
        self.veo_worker = VeoGenerateWorker(query, self.segment.get("render_duration", 5.0), self.output_dir)
        self.veo_worker.finished.connect(self._on_veo_done)
        self.veo_worker.error.connect(self._on_veo_error)
        self.veo_worker.start()
        
    def _on_veo_done(self, videos):
        self.btn_veo.setEnabled(True)
        self.btn_veo.setText("Generate Veo")
        if videos:
            veo_vid = videos[0]
            local_path = veo_vid.get("local_path")
            if local_path and os.path.exists(local_path):
                import time
                thumb_asset = create_video_thumbnail(local_path, self.output_dir, "custom_broll", f"thumb_veo_{int(time.time())}")
                if thumb_asset:
                    veo_vid["thumbnail_path"] = thumb_asset.get("absolute_path")
                    veo_vid["project_thumbnail_path"] = thumb_asset.get("relative_path")
            self.segment["broll_chosen"] = veo_vid
            self.segment.setdefault("broll_candidates", []).insert(0, veo_vid)
            self.status_lbl.setText("✅ Terpilih")
            self.status_lbl.setStyleSheet("color: #10b981;")
            self._populate_cards()
            self.segment_chosen.emit()
            
    def _on_veo_error(self, err):
        self.btn_veo.setEnabled(True)
        self.btn_veo.setText("Generate Veo")
        QMessageBox.warning(self, "Error", f"Gagal generate Veo: {err}")
        
    def _on_local(self):
        path, _ = QFileDialog.getOpenFileName(self, "Pilih video", "", "Video (*.mp4 *.mov)")
        if not path: return
        media_asset = import_media_to_project(path, self.output_dir, "custom_broll")
        import time
        thumb_asset = create_video_thumbnail(media_asset["absolute_path"], self.output_dir, "custom_broll", f"thumb_local_{int(time.time())}")
        
        candidate = {
            "id": f"local_{self.segment['id']}_{media_asset['filename']}",
            "source": "local",
            "thumbnail_path": thumb_asset["absolute_path"] if thumb_asset else None,
            "project_thumbnail_path": thumb_asset["relative_path"] if thumb_asset else None,
            "local_path": media_asset["absolute_path"],
            "project_local_path": media_asset["relative_path"],
        }
        self.segment["broll_chosen"] = candidate
        self.segment.setdefault("broll_candidates", []).insert(0, candidate)
        self.status_lbl.setText("✅ Terpilih")
        self.status_lbl.setStyleSheet("color: #10b981;")
        self._populate_cards()
        self.segment_chosen.emit()


class BrollSelectionPanel(QWidget):
    finished = Signal()
    
    def __init__(self):
        super().__init__()
        self.plan = None
        self.output_dir = None
        self._build_ui()
        
    def _build_ui(self):
        layout = QVBoxLayout(self)
        
        header = QLabel("Pemilihan B-Roll Manual (Review Penuh)")
        set_widget_props(header, role="heroTitle")
        layout.addWidget(header)
        
        desc = QLabel("Pilih klip visual untuk masing-masing segmen sebelum mengunduh video sumber.")
        desc.setStyleSheet("color: #94a3b8; font-size: 14px; margin-bottom: 10px;")
        layout.addWidget(desc)
        
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        self.container = QWidget()
        self.container.setStyleSheet("background: transparent;")
        self.container_layout = QVBoxLayout(self.container)
        self.scroll.setWidget(self.container)
        layout.addWidget(self.scroll, 1)
        
        footer = QHBoxLayout()
        self.lbl_status = QLabel("0 / 0 Terpilih")
        self.lbl_status.setStyleSheet("color: #f8fafc; font-weight: bold;")
        self.btn_confirm = QPushButton("Selesai & Unduh MP4")
        set_widget_props(self.btn_confirm, variant="primary")
        self.btn_confirm.setMinimumHeight(50)
        self.btn_confirm.clicked.connect(self._on_confirm)
        
        footer.addWidget(self.lbl_status)
        footer.addStretch()
        footer.addWidget(self.btn_confirm)
        layout.addLayout(footer)
        
    def load_plan(self, plan: dict, output_dir: str):
        self.plan = plan
        self.output_dir = output_dir
        
        while self.container_layout.count():
            item = self.container_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
                
        segments = self.plan.get("segments", [])
        for seg in segments:
            # force a default if empty to make UI cleaner, or leave it empty
            row = SelectionSegmentRow(seg, output_dir)
            row.segment_chosen.connect(self._update_status)
            self.container_layout.addWidget(row)
            
        self.container_layout.addStretch()
        self._update_status()
        
    def _update_status(self):
        if not self.plan: return
        segs = self.plan.get("segments", [])
        chosen = sum(1 for s in segs if s.get("broll_chosen"))
        self.lbl_status.setText(f"{chosen} / {len(segs)} Terpilih")
        self.btn_confirm.setEnabled(chosen == len(segs))
        
    def _on_confirm(self):
        from core.planner import save_plan
        from core.cache_manager import get_output_cache_paths
        
        for seg in self.plan.get("segments", []):
            seg["confirmed"] = True
            
        paths = get_output_cache_paths(self.output_dir)
        save_plan(self.plan, paths["plan"])
        self.finished.emit()
