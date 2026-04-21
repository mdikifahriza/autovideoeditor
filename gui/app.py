import os

from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QStatusBar,
    QTextEdit,
    QToolBar,
    QVBoxLayout,
    QHBoxLayout,
    QWidget,
)

from core.cache_manager import clear_cache, format_bytes, get_output_cache_paths, load_transcript_cache, save_transcript_cache
from core.preview_cache_manager import (
    create_preview_draft_path,
    get_latest_preview_draft_path,
    get_ready_chunk_paths,
    load_preview_manifest,
    prepare_preview_manifest,
    update_chunk_ready,
    update_draft_state,
)
from core.project_manager import (
    append_project_log,
    create_project,
    get_project_paths,
    load_script_text,
    load_project,
    register_artifact,
    set_project_stage,
    update_project_metadata,
)
from gui.progress_panel import ProgressPanel
from gui.review_panel import ReviewPanel
from gui.script_refine_panel import ScriptRefinePanel
from gui.ui_theme import set_widget_props
from gui.upload_panel import UploadPanel


class ScriptRefineWorker(QThread):
    finished = Signal(str)
    error = Signal(str)
    
    def __init__(self, prompt: str, current_script: str):
        super().__init__()
        self.prompt = prompt
        self.current_script = current_script
        
    def run(self):
        try:
            from core.ai_handler import AIHandler
            from core.settings_manager import settings
            import os
            
            from google.genai import types
            
            client = AIHandler.get_client()
            model_name = settings.get("gemini_model_planner", "gemini-2.5-pro")
            
            system_instruction = (
                "You are an expert video script writer. "
                "The user will provide a current script and an instruction on how to refine it. "
                "Output ONLY the finalized script text, without markdown blocks, without preambles, "
                "without scene descriptions, ONLY the spoken text."
            )
            
            prompt_full = (
                f"CURRENT SCRIPT:\n{self.current_script}\n\n"
                f"INSTRUCTION TO REFINE:\n{self.prompt}\n\n"
                "Please rewrite the script according to the instruction."
            )
            
            response = client.models.generate_content(
                model=model_name,
                contents=prompt_full,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=0.7
                )
            )
            
            if response and response.text:
                self.finished.emit(response.text)
            else:
                self.error.emit("AI tidak mengembalikan teks.")
                
        except Exception as e:
            self.error.emit(str(e))


class ScriptPreparationWorker(QThread):
    progress = Signal(int, int, str)
    log = Signal(str)
    finished = Signal(object)
    error = Signal(str)

    def __init__(self, project_dir: str, payload: dict):
        super().__init__()
        self.project_dir = project_dir
        self.payload = dict(payload or {})

    def run(self):
        try:
            from core.script_builder import build_script_from_manual_text, build_script_from_title
            from core.project_manager import attach_manual_script, save_script_text

            project_mode = str(self.payload.get("project_mode", "voiceover") or "voiceover").strip()
            title = str(self.payload.get("title", "") or "").strip()
            set_project_stage(self.project_dir, "scripting", "in_progress")
            self.progress.emit(0, 2, "Menyiapkan draft script...")

            if project_mode == "semi_auto":
                self.log.emit("Merapikan script manual sebelum masuk panel refine.")
                draft = build_script_from_manual_text(title, self.payload.get("manual_script", ""))
                draft_path = attach_manual_script(self.project_dir, draft["script_text"], kind="draft")
            elif project_mode == "full_auto":
                from core.project_manager import save_research_pack
                
                self.progress.emit(1, 2, "Menyusun draft script dari judul/topik...")
                self.log.emit("Menyusun draft script awal dari judul/topik.")
                draft = build_script_from_title(title, self.payload.get("angle", ""), log_cb=self.log.emit)
                draft_path = save_script_text(self.project_dir, draft["script_text"], kind="draft")
                
                if "research_pack" in draft:
                    save_research_pack(self.project_dir, draft["research_pack"], draft["research_pack"].get("query", ""))
            else:
                raise RuntimeError(f"Mode script tidak dikenali: {project_mode}")

            update_project_metadata(
                self.project_dir,
                project_mode=project_mode,
                review_profile=self.payload.get("review_profile", "standard"),
                inputs={
                    "title": title,
                    "research_query": str(self.payload.get("angle", "") or "").strip(),
                },
                content={
                    "script_source": draft.get("source_type", project_mode),
                },
            )
            register_artifact(self.project_dir, "script_file", draft_path, stage="scripting")
            payload = {
                **self.payload,
                **draft,
                "script_path": draft_path,
            }
            self.progress.emit(2, 2, "Draft script siap untuk direfine.")
            self.finished.emit(payload)
        except Exception as e:
            import traceback

            set_project_stage(self.project_dir, "scripting", "failed", error=str(e))
            self.error.emit(f"{e}\n\n{traceback.format_exc()}")


class TTSWorker(QThread):
    progress = Signal(int, int, str)
    log = Signal(str)
    finished = Signal(object)
    error = Signal(str)

    def __init__(self, project_dir: str, payload: dict):
        super().__init__()
        self.project_dir = project_dir
        self.payload = dict(payload or {})

    def run(self):
        try:
            from core.project_manager import get_project_paths, save_script_text
            from core.tts_manager import synthesize_project_voiceover

            final_script = str(self.payload.get("script_text", "") or "").strip()
            title = str(self.payload.get("title", "") or "").strip()
            if not final_script:
                raise RuntimeError("Script final kosong, voice over AI tidak bisa dibuat.")

            self.progress.emit(0, 3, "Menyimpan script final...")
            script_path = save_script_text(self.project_dir, final_script, kind="final")
            update_project_metadata(
                self.project_dir,
                inputs={
                    "title": title,
                    "tts_voice": str(self.payload.get("tts_voice", "") or "").strip(),
                },
                content={
                    "script_source": self.payload.get("source_type", ""),
                },
            )
            register_artifact(self.project_dir, "script_file", script_path, stage="scripting")

            self.progress.emit(1, 3, "Membuat voice over AI...")
            result = synthesize_project_voiceover(
                self.project_dir,
                final_script,
                voice_name=str(self.payload.get("tts_voice", "") or "").strip(),
                log_cb=self.log.emit,
            )

            self.progress.emit(2, 3, "Menyiapkan proyek ke pipeline audio...")
            register_artifact(
                self.project_dir,
                "tts_audio_file",
                get_project_paths(self.project_dir)["tts_audio"],
                stage="tts_generation",
            )
            self.progress.emit(3, 3, "Voice over AI siap diproses.")
            self.finished.emit(
                {
                    **self.payload,
                    "audio_path": result.get("project_audio_path", ""),
                    "tts_result": result,
                }
            )
        except Exception as e:
            import traceback

            set_project_stage(self.project_dir, "tts_generation", "failed", error=str(e))
            self.error.emit(f"{e}\n\n{traceback.format_exc()}")


class ProcessingWorker(QThread):
    progress = Signal(int, int, str)
    log = Signal(str)
    step_done = Signal(str, object)
    download_progress = Signal(int, int, str)
    finished = Signal(str)
    error = Signal(str)

    def __init__(self, project_dir: str, audio_path: str, mode: str = "semi_manual"):
        super().__init__()
        self.output_dir = project_dir
        self.paths = get_output_cache_paths(project_dir)
        self.audio_path = audio_path
        self.mode = mode
        self.plan_path = self.paths["plan"]

    def run(self):
        try:
            from core.broll_fetcher import fetch_candidates_for_plan, ensure_segment_video_available
            from core.planner import generate_edit_plan, save_plan, load_plan
            from core.transcriber import transcribe
            from core.vision_validator import validate_all_segments

            if self.mode == "download_missing":
                plan = load_plan(self.plan_path)
                segments = plan.get("segments", [])
                
                def _log_cb(msg):
                    self.log.emit(msg)
                def _progress_cb(c, t, m):
                    self.download_progress.emit(c, t, m)

                missing_count = sum(1 for s in segments if not (
                    (isinstance(s.get("broll_chosen"), dict) and 
                     s["broll_chosen"].get("local_path") and 
                     os.path.exists(s["broll_chosen"]["local_path"])) or
                    (isinstance(s.get("broll_chosen"), dict) and 
                     s["broll_chosen"].get("project_local_path") and 
                     os.path.exists(os.path.join(self.output_dir, s["broll_chosen"]["project_local_path"])))
                ))
                
                done_count = 0
                for i, segment in enumerate(segments):
                    chosen = segment.get("broll_chosen")
                    if not isinstance(chosen, dict):
                        continue
                    local = str(chosen.get("local_path", ""))
                    proj_local = str(chosen.get("project_local_path", ""))
                    if (local and os.path.exists(local)) or (proj_local and os.path.exists(os.path.join(self.output_dir, proj_local))):
                        continue
                        
                    self.progress.emit(done_count, missing_count, f"Mengunduh klip untuk segmen {i+1}...")
                    
                    local_path = ensure_segment_video_available(
                        segment,
                        project_dir=self.output_dir,
                        progress_cb=_progress_cb,
                        log_cb=_log_cb,
                    )
                    
                    if local_path and os.path.exists(local_path):
                        segment["broll_load_failed"] = False
                        segment.pop("broll_load_error", None)
                    else:
                        segment["broll_load_failed"] = True
                        segment["broll_load_error"] = "Gagal mengunduh (Batch Download)."
                        
                    done_count += 1
                
                save_plan(plan, self.plan_path)
                self.progress.emit(missing_count, missing_count, "Selesai mengunduh klip.")
                self.finished.emit("")
                return

            state_paths = self.paths
            transcript_cache = load_transcript_cache(self.output_dir, self.audio_path)
            plan = None

            set_project_stage(self.output_dir, "review", "in_progress")
            if os.path.exists(state_paths["plan"]):
                self.log.emit("Menemukan edit plan sebelumnya, melanjutkan dari progres proyek yang tersimpan.")
                plan = load_plan(state_paths["plan"])
                self.step_done.emit("plan", plan)
            else:
                if transcript_cache:
                    self.log.emit("Menemukan transkripsi cache, melewati langkah transkripsi.")
                    segments = transcript_cache.get("segments", [])
                    total_dur = float(transcript_cache.get("total_duration", 0))
                    self.step_done.emit("transcribe", segments)
                else:
                    set_project_stage(self.output_dir, "transcription", "in_progress")
                    self.progress.emit(0, 4, "Transkripsi audio (Gemini)...")
                    segments, total_dur = transcribe(self.audio_path, log_cb=self.log.emit)
                    save_transcript_cache(self.output_dir, self.audio_path, segments, total_dur)
                    register_artifact(self.output_dir, "transcript_file", state_paths["transcript"], stage="transcription")
                    self.step_done.emit("transcribe", segments)

                set_project_stage(self.output_dir, "planning", "in_progress")
                self.progress.emit(1, 4, "Membuat edit plan (Gemini)...")
                plan = generate_edit_plan(segments, total_dur, log_cb=self.log.emit)
                save_plan(plan, self.plan_path)
                register_artifact(self.output_dir, "plan_file", self.plan_path, stage="planning")
                self.step_done.emit("plan", plan)

            if not plan or not plan.get("segments"):
                raise RuntimeError("Edit plan tidak valid atau kosong.")

            needs_broll = any(
                not seg.get("broll_candidates") or not seg.get("broll_chosen")
                for seg in plan.get("segments", [])
            )
            needs_validation = not plan.get("validated", False)

            if needs_broll:
                set_project_stage(self.output_dir, "broll_search", "in_progress")
                self.progress.emit(2, 4, "Mencari B-roll...")
                plan = fetch_candidates_for_plan(
                    plan,
                    project_dir=self.output_dir,
                    progress_cb=lambda c, t, m: self.progress.emit(c, t, m),
                    log_cb=self.log.emit,
                )
                save_plan(plan, self.plan_path)
                with open(state_paths["search"], "w", encoding="utf-8") as fh:
                    import json

                    json.dump(plan.get("segments", []), fh, ensure_ascii=False, indent=2)
                register_artifact(self.output_dir, "search_file", state_paths["search"], stage="broll_search")

            if needs_validation:
                set_project_stage(self.output_dir, "validation", "in_progress")
                self.progress.emit(3, 4, "Validasi B-roll (Gemini Vision)...")
                plan = validate_all_segments(
                    plan,
                    progress_cb=lambda c, t, m: self.progress.emit(c, t, m),
                    log_cb=self.log.emit,
                )
                plan["validated"] = True
                save_plan(plan, self.plan_path)
                register_artifact(self.output_dir, "plan_file", self.plan_path, stage="validation")
                self.step_done.emit("validated_plan", plan)

            set_project_stage(self.output_dir, "preview_render", "not_started")
            set_project_stage(self.output_dir, "review", "in_progress")
            self.progress.emit(4, 4, "Edit plan siap. Source preview aktif di panel review.")
            self.finished.emit("")
        except Exception as e:
            import traceback

            set_project_stage(self.output_dir, "review", "failed", error=str(e))
            self.error.emit(f"{e}\n\n{traceback.format_exc()}")


class PreviewRenderWorker(QThread):
    progress = Signal(int, int, str)
    log = Signal(str)
    draft_updated = Signal(str, int, int, float, str)
    finished = Signal(str)
    error = Signal(str)

    def __init__(self, plan: dict, audio_path: str, output_dir: str, start_index: int = 0):
        super().__init__()
        self.plan = plan
        self.audio_path = audio_path
        self.output_dir = output_dir
        self.start_index = max(0, int(start_index or 0))

    def run(self):
        try:
            from core.renderer import build_preview_draft, render_segment_preview

            total = len(self.plan.get("segments", []))
            if total <= 0:
                self.finished.emit("")
                return

            set_project_stage(self.output_dir, "preview_render", "in_progress")
            manifest = prepare_preview_manifest(
                self.output_dir,
                self.plan,
                self.audio_path,
                start_index=self.start_index,
            )
            ready_count = int(manifest.get("ready_count", 0) or 0)
            available_duration = float(manifest.get("available_duration", 0) or 0)
            draft_path = manifest.get("draft_path", "")

            if ready_count and draft_path and os.path.exists(draft_path):
                self.draft_updated.emit(
                    draft_path,
                    ready_count,
                    total,
                    available_duration,
                    f"Preview siap {ready_count}/{total} segmen.",
                )

            for index in range(ready_count, total):
                if self.isInterruptionRequested():
                    self.log.emit("Preview background dihentikan sementara.")
                    return

                segment = self.plan["segments"][index]
                self.progress.emit(index, total, f"Render preview segmen {index + 1}/{total} (360p)...")
                self.log.emit(f"Render preview segmen {index + 1}/{total} ke cache temp.")
                chunk_path = manifest["chunks"][index]["path"]
                render_segment_preview(
                    segment,
                    chunk_path,
                    plan=self.plan,
                    output_dir=self.output_dir,
                )
                segment_duration = float(
                    segment.get("render_duration")
                    or max(1.0, float(segment.get("end", 0) or 0) - float(segment.get("start", 0) or 0))
                )
                manifest = update_chunk_ready(
                    self.output_dir,
                    manifest,
                    index,
                    chunk_path,
                    segment_duration,
                )
                ready_count = int(manifest.get("ready_count", 0) or 0)
                ready_chunks = get_ready_chunk_paths(manifest)
                draft_path = create_preview_draft_path(self.output_dir, ready_count)
                preview_path = build_preview_draft(
                    self.plan,
                    self.audio_path,
                    ready_chunks,
                    draft_path,
                    output_dir=self.output_dir,
                    ready_segments=ready_count,
                )
                available_duration = sum(
                    float(chunk.get("duration", 0) or 0)
                    for chunk in manifest.get("chunks", [])[:ready_count]
                )
                if preview_path:
                    manifest = update_draft_state(
                        self.output_dir,
                        manifest,
                        preview_path,
                        available_duration,
                    )
                    self.draft_updated.emit(
                        preview_path,
                        ready_count,
                        total,
                        available_duration,
                        f"Preview siap sampai segmen {ready_count}/{total}.",
                    )

            set_project_stage(self.output_dir, "preview_render", "done")
            self.progress.emit(total, total, "Preview selesai dirender.")
            self.finished.emit(manifest.get("draft_path", ""))
        except Exception as e:
            import traceback

            set_project_stage(self.output_dir, "preview_render", "failed", error=str(e))
            self.error.emit(f"{e}\n\n{traceback.format_exc()}")


class ReRenderWorker(QThread):
    progress = Signal(int, int, str)
    log = Signal(str)
    download_progress = Signal(int, int, str)
    finished = Signal(str)
    error = Signal(str)

    def __init__(self, plan: dict, audio_path: str, output_dir: str):
        super().__init__()
        self.plan = plan
        self.audio_path = audio_path
        self.output_dir = output_dir
        state_paths = get_output_cache_paths(output_dir)
        self.output_path = state_paths["final"]

    def run(self):
        try:
            from core.renderer import render_full

            set_project_stage(self.output_dir, "final_render", "in_progress")
            render_full(
                self.plan,
                self.audio_path,
                self.output_path,
                progress_cb=lambda c, t, m: self.progress.emit(c, t, m),
                download_cb=lambda c, t, m: self.download_progress.emit(c, t, m),
            )
            register_artifact(self.output_dir, "final_file", self.output_path, stage="final_render")
            self.finished.emit(self.output_path)
        except Exception as e:
            import traceback

            set_project_stage(self.output_dir, "final_render", "failed", error=str(e))
            self.error.emit(f"{e}\n\n{traceback.format_exc()}")


class ErrorDialog(QDialog):
    GO_HOME_RESULT = 2

    def __init__(self, parent, title: str, message: str, retry_callback=None):
        super().__init__(parent)
        self.retry_callback = retry_callback
        self.setWindowTitle(title)
        self.setModal(True)
        self.resize(760, 420)
        self.setObjectName("error_dialog")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        shell = QFrame()
        set_widget_props(shell, role="heroCard")
        shell_layout = QVBoxLayout(shell)
        shell_layout.setContentsMargins(16, 16, 16, 16)
        shell_layout.setSpacing(10)

        shell_layout.addWidget(set_widget_props(QLabel("Recovery"), role="eyebrow"))

        header = QLabel("Terjadi kesalahan selama pemrosesan")
        set_widget_props(header, role="sectionTitle")
        shell_layout.addWidget(header)

        info = QLabel(
            "Kamu bisa menyalin detail error, mengulang proses, atau kembali ke beranda."
        )
        info.setWordWrap(True)
        set_widget_props(info, role="heroSubtitle")
        shell_layout.addWidget(info)
        layout.addWidget(shell)

        self.error_text = QTextEdit()
        self.error_text.setReadOnly(True)
        self.error_text.setPlainText(message)
        set_widget_props(self.error_text, role="codeConsole")
        layout.addWidget(self.error_text, 1)

        button_row = QHBoxLayout()
        button_row.addStretch()

        if self.retry_callback:
            btn_retry = QPushButton("Retry")
            set_widget_props(btn_retry, variant="secondary")
            btn_retry.clicked.connect(self._retry)
            button_row.addWidget(btn_retry)

        btn_home = QPushButton("Kembali ke Beranda")
        set_widget_props(btn_home, variant="ghost")
        btn_home.clicked.connect(self._go_home)
        button_row.addWidget(btn_home)

        btn_copy = QPushButton("Salin Error")
        set_widget_props(btn_copy, variant="secondary")
        btn_copy.clicked.connect(self._copy_error)
        button_row.addWidget(btn_copy)

        btn_close = QPushButton("Tutup")
        set_widget_props(btn_close, variant="primary")
        btn_close.clicked.connect(self.accept)
        button_row.addWidget(btn_close)
        layout.addLayout(button_row)

    def _copy_error(self):
        QApplication.clipboard().setText(self.error_text.toPlainText())

    def _retry(self):
        if self.retry_callback:
            self.retry_callback()
        self.accept()

    def _go_home(self):
        self.done(self.GO_HOME_RESULT)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Auto Video Editor")
        self.setObjectName("main_window")

        font = QFont("Segoe UI", 10)
        font.setStyleStrategy(QFont.PreferAntialias)
        self.setFont(font)

        self.setMinimumSize(800, 500)
        self.showMaximized()

        self._load_styles()

        self.audio_path = None
        self.output_dir = None
        self.plan = None
        self.draft_path = None
        self.worker = None
        self.preview_worker = None
        self.current_mode = "voiceover"
        self.current_project_mode = "voiceover"
        self.current_review_profile = "standard"
        self.script_draft = {}
        self.pending_start_payload = {}
        self.pending_tts_payload = {}
        self._retry_action = None
        self._preview_operation = ""
        self._current_preview_segment_index = -1
        self._toolbar_syncing = False

        self.stack = QStackedWidget()
        self.stack.setObjectName("app_stack")
        self.setCentralWidget(self.stack)

        from gui.home_panel import HomePanel
        self.home_panel = HomePanel()
        self.upload_panel = UploadPanel()
        self.script_refine_panel = ScriptRefinePanel()
        self.progress_panel = ProgressPanel()
        self.review_panel = ReviewPanel()

        self.stack.addWidget(self.home_panel)
        self.stack.addWidget(self.upload_panel)
        self.stack.addWidget(self.script_refine_panel)
        self.stack.addWidget(self.progress_panel)
        self.stack.addWidget(self.review_panel)

        self.toolbar = QToolBar("Main Toolbar")
        self.toolbar.setObjectName("top_toolbar")
        self.toolbar.setMovable(False)
        self.addToolBar(self.toolbar)

        brand_group = QWidget()
        brand_layout = QVBoxLayout(brand_group)
        brand_layout.setContentsMargins(8, 4, 8, 4)
        brand_layout.setSpacing(2)
        brand_label = QLabel("Auto Video Editor by M. Diki Fahriza")
        set_widget_props(brand_label, role="toolbarBrand")
        self.lbl_toolbar_context = QLabel("")
        set_widget_props(self.lbl_toolbar_context, role="toolbarContext")
        brand_layout.addWidget(brand_label)
        brand_layout.addWidget(self.lbl_toolbar_context)
        self.toolbar.addWidget(brand_group)

        self.btn_rerender_all = QPushButton("Render Semua Preview")
        self.btn_rerender_all.hide()  # Hidden because of realtime preview

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.toolbar.addWidget(spacer)

        self.btn_settings = QPushButton("⚙")
        set_widget_props(self.btn_settings, variant="toolbar")
        self.btn_settings.clicked.connect(self._open_settings)

        self.btn_clear_cache = QPushButton("🗑️")
        set_widget_props(self.btn_clear_cache, variant="toolbar")
        self.btn_clear_cache.clicked.connect(self._clear_cache)

        utility_controls = QWidget()
        utility_layout = QHBoxLayout(utility_controls)
        utility_layout.setContentsMargins(8, 4, 8, 4)
        utility_layout.setSpacing(10)
        utility_layout.addWidget(self.btn_settings)
        utility_layout.addWidget(self.btn_clear_cache)
        self.toolbar.addWidget(utility_controls)

        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self.status.showMessage("Siap. Pilih mode proyek untuk memulai.")

        self.home_panel.new_project_requested.connect(lambda: self.stack.setCurrentWidget(self.upload_panel))
        self.home_panel.open_project_requested.connect(self._on_project_opened)
        self.upload_panel.start_clicked.connect(self._on_start)
        self.upload_panel.btn_back_home.clicked.connect(lambda: self.stack.setCurrentWidget(self.home_panel))
        self.upload_panel.project_opened.connect(self._on_project_opened)
        self.script_refine_panel.back_requested.connect(self._on_script_back_requested)
        self.script_refine_panel.continue_requested.connect(self._on_script_continue)
        self.script_refine_panel.refine_requested.connect(self._start_script_refine)
        self.review_panel.rerender_requested.connect(self._on_rerender_segment)
        self.review_panel.preview_refresh_requested.connect(self._on_preview_refresh_requested)
        self.review_panel.final_render_requested.connect(self._on_final_render)
        self.review_panel.state_changed.connect(self._refresh_toolbar_state)
        self.review_panel.state_changed.connect(self._on_review_state_changed)
        self.review_panel.global_settings_changed.connect(self._on_review_global_settings_changed)
        self.review_panel.back_to_home_requested.connect(self._return_to_home)
        self.review_panel.download_missing_requested.connect(self._on_download_missing_requested)
        self.stack.currentChanged.connect(
            lambda _index: (self._refresh_toolbar_state(), self._update_toolbar_context())
        )
        self._review_toolbar_widgets = []
        self._update_toolbar_context()
        self._refresh_toolbar_state()

    def _stop_preview_worker(self):
        # Disabled for realtime preview overlay
        pass

    def _refresh_toolbar_state(self):
        in_review = self.stack.currentWidget() is self.review_panel
        has_plan = bool(self.plan and self.plan.get("segments"))
        preview_busy = bool(self.preview_worker and self.preview_worker.isRunning())
        final_busy = bool(isinstance(self.worker, ReRenderWorker) and self.worker.isRunning())
        can_review = in_review and has_plan and not final_busy
        all_confirmed = bool(has_plan and all(seg.get("confirmed", False) for seg in self.plan.get("segments", [])))

        # Hide/show review toolbar widgets based on current panel
        for widget in self._review_toolbar_widgets:
            widget.setVisible(in_review)

        self.btn_rerender_all.setEnabled(can_review and not preview_busy)
        if in_review and has_plan:
            self._sync_review_toolbar_toggles()
        self._update_toolbar_context()

    def _update_toolbar_context(self):
        current = self.stack.currentWidget()
        if current is self.home_panel:
            context = "Beranda"
        elif current is self.upload_panel:
            context = "Proyek Baru"
        elif current is self.script_refine_panel:
            context = "Refine script"
        elif current is self.progress_panel:
            context = "Pipeline proses"
        elif current is self.review_panel:
            context = "Studio review"
        else:
            context = "Workspace"

        project_name = ""
        if self.output_dir:
            project_name = os.path.basename(self.output_dir.rstrip("\\/"))

        self.lbl_toolbar_context.setText(
            f"{context} | {project_name}" if project_name else context
        )

    def _on_rerender_all_previews(self):
        # Deprecated
        pass

    def _show_review_panel(self, status_message: str = ""):
        if not self.plan or not self.output_dir:
            return

        latest_draft = get_latest_preview_draft_path(self.output_dir, self.plan, self.audio_path)
        manifest = load_preview_manifest(self.output_dir) or {}
        self.draft_path = latest_draft or ""
        self.review_panel.load_plan(self.plan, self.audio_path, self.output_dir)
        if self.draft_path:
            try:
                self.review_panel.update_draft_video(self.draft_path, activate=False)
            except Exception:
                pass

        total = len(self.plan.get("segments", []))
        ready_count = int(manifest.get("ready_count", 0) or 0) if latest_draft else 0
        available_duration = float(manifest.get("available_duration", 0) or 0) if latest_draft else 0.0
        if total:
            message = "Source preview aktif. Render preview hanya dibuat saat diminta."
            if ready_count:
                message = (
                    f"Source preview aktif. Cache rendered preview tersedia untuk "
                    f"{ready_count}/{total} segmen."
                )
            self.review_panel.update_preview_status(ready_count, total, available_duration, message)

        self.stack.setCurrentWidget(self.review_panel)
        self.review_panel.hide_inline_error()
        self._sync_review_toolbar_toggles()
        self._refresh_toolbar_state()
        self._on_review_state_changed()
        if status_message:
            self.status.showMessage(status_message)

    def _sync_review_toolbar_toggles(self):
        pass

    def _on_toolbar_subtitle_toggled(self, checked: bool):
        pass

    def _on_toolbar_floating_toggled(self, checked: bool):
        pass

    def _on_review_global_settings_changed(self, subtitle_enabled: bool, floating_enabled: bool):
        pass

    def _on_review_state_changed(self):
        if not self.plan:
            self.lbl_toolbar_summary.setText("")
            return

        segments = self.plan.get("segments", [])
        confirmed = sum(1 for s in segments if s.get("confirmed", False))
        dur = sum(float(s.get("render_duration", 0) or 0) for s in segments)
        self.lbl_toolbar_summary.setText(
            f"{len(segments)} seg | {confirmed} siap | {dur:.0f} dtk"
        )

    def _start_preview_worker(self, start_index: int = 0, reason: str = "", operation: str = "background"):
        # We no longer render MP4 previews in the background because
        # we have a realtime GPU text overlay in the ReviewPanel.
        self._refresh_toolbar_state()

    def _open_settings(self):
        from gui.settings_dialog import SettingsDialog

        dialog = SettingsDialog(self)
        dialog.exec()
        self.upload_panel.refresh_projects_root_label()

    def _add_to_history(self, path: str):
        if not path:
            return
        history = settings.get("project_history", [])
        if path in history:
            history.remove(path)
        history.append(path)
        settings.set("project_history", history[-10:])

    def _on_project_opened(self, project_path: str):
        try:
            self._stop_preview_worker()
            self.status.showMessage("Membuka proyek...")
            extract_to = os.path.splitext(project_path)[0] + "_extracted" if project_path.lower().endswith(".avep") else None
            project_data = load_project(project_path, extract_to)

            if not project_data:
                QMessageBox.warning(self, "Error", "Gagal membaca proyek ini.")
                self.status.showMessage("Siap.")
                return

            self.output_dir = project_data["project_dir"]
            self._add_to_history(self.output_dir)
            self.audio_path = project_data.get("audio_path") or ""
            self.plan = project_data.get("plan")
            metadata = project_data.get("metadata") or {}
            self.current_project_mode = metadata.get("project_mode", "voiceover")
            self.current_mode = self.current_project_mode
            self.current_review_profile = metadata.get("review_profile", "standard")
            self.draft_path = get_latest_preview_draft_path(self.output_dir, self.plan, self.audio_path) if self.plan else ""

            if self.plan:
                self._show_review_panel(
                    f"Proyek {os.path.basename(self.output_dir)} berhasil dibuka. Source preview aktif."
                )
            elif self.audio_path and os.path.exists(self.audio_path):
                self.status.showMessage("Melanjutkan proyek dari progres yang tersimpan...")
                self._restart_current_project()
            elif self.current_project_mode in {"semi_auto", "full_auto"}:
                script_text = load_script_text(self.output_dir)
                if script_text:
                    self.script_draft = {
                        "project_name": metadata.get("name", os.path.basename(self.output_dir)),
                        "project_mode": self.current_project_mode,
                        "review_profile": self.current_review_profile,
                        "title": metadata.get("inputs", {}).get("title", metadata.get("name", "")),
                        "script_text": script_text,
                        "source_type": metadata.get("content", {}).get("script_source", ""),
                        "tts_voice": metadata.get("inputs", {}).get("tts_voice", "Kore"),
                    }
                    self._show_script_panel("Lanjutkan refine script sebelum membuat voice over AI.")
                else:
                    self.stack.setCurrentWidget(self.home_panel)
                    self.status.showMessage(f"Proyek {os.path.basename(self.output_dir)} berhasil dibuka.")
                    self._refresh_toolbar_state()
            else:
                self.stack.setCurrentWidget(self.home_panel)
                self.status.showMessage(f"Proyek {os.path.basename(self.output_dir)} berhasil dibuka.")
                self._refresh_toolbar_state()
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Gagal membuka proyek:\n{e}")
            self.status.showMessage("Siap.")
            self._refresh_toolbar_state()

    def _load_styles(self):
        qss_path = os.path.join(os.path.dirname(__file__), "style.qss")
        if os.path.exists(qss_path):
            with open(qss_path, encoding="utf-8") as f:
                self.setStyleSheet(f.read())

    def _show_script_panel(self, status_message: str = ""):
        if not self.script_draft:
            return
        self.script_refine_panel.load_script(self.script_draft)
        self.stack.setCurrentWidget(self.script_refine_panel)
        if status_message:
            self.status.showMessage(status_message)
        self._refresh_toolbar_state()

    def _launch_processing_worker(self, initial_log: str = ""):
        if not self.output_dir or not self.audio_path:
            return
        self.stack.setCurrentWidget(self.progress_panel)
        self.progress_panel.reset()
        if initial_log:
            self.progress_panel.append_log(initial_log)

        self._retry_action = lambda: self._restart_current_project()
        self.worker = ProcessingWorker(self.output_dir, self.audio_path, self.current_project_mode)
        self.worker.progress.connect(self.progress_panel.update_progress)
        self.worker.download_progress.connect(self.progress_panel.update_download_status)
        self.worker.log.connect(self.progress_panel.append_log)
        self.worker.log.connect(self._append_project_log)
        self.worker.step_done.connect(self._on_step_done)
        self.worker.finished.connect(self._on_processing_done)
        self.worker.error.connect(self._on_error)
        self.worker.start()
        self._refresh_toolbar_state()

    def _start_script_preparation(self, payload: dict):
        if not self.output_dir:
            return
        self.pending_start_payload = dict(payload or {})
        self.stack.setCurrentWidget(self.progress_panel)
        self.progress_panel.reset()
        self.progress_panel.append_log(f"Folder proyek: {self.output_dir}")
        self._retry_action = lambda: self._start_script_preparation(self.pending_start_payload)
        self.worker = ScriptPreparationWorker(self.output_dir, payload)
        self.worker.progress.connect(self.progress_panel.update_progress)
        self.worker.log.connect(self.progress_panel.append_log)
        self.worker.log.connect(self._append_project_log)
        self.worker.finished.connect(self._on_script_prepared)
        self.worker.error.connect(self._on_error)
        self.worker.start()
        self._refresh_toolbar_state()

    def _start_script_refine(self, prompt: str, current_script: str):
        self.status.showMessage("Sedang merefine script dengan AI...")
        self.script_refine_worker = ScriptRefineWorker(prompt, current_script)
        self.script_refine_worker.finished.connect(self._on_script_refine_done)
        self.script_refine_worker.error.connect(self._on_script_refine_error)
        self.script_refine_worker.start()
        
    def _on_script_refine_done(self, new_text: str):
        self.status.showMessage("Script berhasil direfine.")
        self.script_refine_panel.refine_finished(new_text)
        
    def _on_script_refine_error(self, err: str):
        self.status.showMessage("Gagal merefine script.")
        self.script_refine_panel.refine_finished("")
        QMessageBox.warning(self, "Refine Gagal", f"Gagal merefine script:\n\n{err}")

    def _start_tts_generation(self, payload: dict):
        if not self.output_dir:
            return
        self.pending_tts_payload = dict(payload or {})
        self.stack.setCurrentWidget(self.progress_panel)
        self.progress_panel.reset()
        self.progress_panel.append_log("Menyiapkan voice over AI untuk proyek ini...")
        self._retry_action = lambda: self._start_tts_generation(self.pending_tts_payload)
        self.worker = TTSWorker(self.output_dir, payload)
        self.worker.progress.connect(self.progress_panel.update_progress)
        self.worker.log.connect(self.progress_panel.append_log)
        self.worker.log.connect(self._append_project_log)
        self.worker.finished.connect(self._on_tts_ready)
        self.worker.error.connect(self._on_error)
        self.worker.start()
        self._refresh_toolbar_state()

    def _on_start(self, payload: dict):
        project_name = str(payload.get("project_name", "") or "").strip()
        project_mode = str(payload.get("project_mode", "voiceover") or "voiceover").strip()
        review_profile = str(payload.get("review_profile", "standard") or "standard").strip()
        audio_path = str(payload.get("audio_path", "") or "").strip()
        title = str(payload.get("title", "") or project_name).strip()

        self.current_mode = project_mode
        self.current_project_mode = project_mode
        self.current_review_profile = review_profile
        self._stop_preview_worker()
        try:
            project_dir, _ = create_project(
                project_name,
                voiceover_path=audio_path if project_mode == "voiceover" else "",
                project_mode=project_mode,
                review_profile=review_profile,
                title=title or project_name,
            )
            self._add_to_history(project_dir)
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Gagal membuat folder proyek:\n{e}")
            self.status.showMessage("Siap.")
            return

        self.audio_path = get_project_paths(project_dir)["audio"]
        self.output_dir = project_dir
        self.plan = None
        self.draft_path = None
        update_project_metadata(
            self.output_dir,
            project_mode=project_mode,
            review_profile=review_profile,
            inputs={
                "title": title or project_name,
                "research_query": str(payload.get("angle", "") or "").strip(),
            },
        )

        if project_mode == "voiceover":
            self._launch_processing_worker(f"Folder proyek: {self.output_dir}")
            return

        self.script_draft = {}
        self._start_script_preparation(payload)

    def _on_script_prepared(self, payload: dict):
        if self.worker:
            self.worker.quit()
            self.worker.wait()
        self.worker = None
        self._retry_action = None
        self.script_draft = dict(payload or {})
        self._show_script_panel("Draft script siap. Review dan sesuaikan dulu sebelum dibuat menjadi voice over.")

    def _on_script_back_requested(self):
        self.stack.setCurrentWidget(self.upload_panel)
        self.status.showMessage("Kembali ke halaman awal proyek.")
        self._refresh_toolbar_state()

    def _on_script_continue(self, payload: dict):
        self.script_draft = dict(payload or {})
        self._start_tts_generation(self.script_draft)

    def _on_tts_ready(self, payload: dict):
        if self.worker:
            self.worker.quit()
            self.worker.wait()
        self.worker = None
        self._retry_action = None
        self.pending_tts_payload = {}
        self.script_draft = dict(payload or {})
        self.audio_path = str(self.script_draft.get("audio_path", "") or "").strip()
        self._launch_processing_worker(f"Folder proyek: {self.output_dir}")

    def _clear_cache(self):
        self._stop_preview_worker()
        removed, freed = clear_cache(self.output_dir if self.output_dir else None)
        self.status.showMessage(f"Cache dibersihkan: {removed} file dihapus ({format_bytes(freed)})")
        if self.plan:
            self.draft_path = ""
            self.review_panel.update_draft_video("")
            self.review_panel.hide_inline_error()
            self.review_panel.hide_rerender_progress()
            self.review_panel.update_preview_status(
                0,
                len(self.plan.get("segments", [])),
                0.0,
                "Cache preview dibersihkan. Klik Render Semua Preview untuk membuat ulang draft 360p.",
            )
        QMessageBox.information(
            self,
            "Cache Dikosongkan",
            f"Berhasil menghapus {removed} file preview/render cache. Total ruang dibebaskan: {format_bytes(freed)}.",
        )
        self._refresh_toolbar_state()

    def _on_step_done(self, step: str, result):
        if step in {"validated_plan", "plan", "loaded_draft"}:
            self.plan = result
            if isinstance(result, dict) and result.get("segments"):
                failed_count = sum(1 for s in result["segments"] if s.get("broll_load_failed"))
                if failed_count > 0:
                    self.status.showMessage(
                        f"Warning: {failed_count} segmen gagal load video. Review dan retry di panel."
                    )

            self._refresh_toolbar_state()

    def _on_processing_done(self, draft_path: str):
        self.worker.quit()
        self.worker.wait()
        self.worker = None
        self._retry_action = None
        self.draft_path = draft_path
        self._show_review_panel("Edit plan siap. Source preview aktif, rendered preview tersedia saat diminta.")

    def _on_rerender_segment(self, segment_id: int):
        if not self.plan:
            return
        start_at = max(0, int(segment_id))
        self.status.showMessage(f"Menyegarkan preview mulai segmen {start_at + 1}...")
        self._start_preview_worker(
            start_index=start_at,
            reason=f"Menyegarkan preview mulai segmen {start_at + 1}.",
            operation="segment_rerender",
        )

    def _on_preview_refresh_requested(self, start_index: int):
        if not self.plan:
            return
        start_at = max(0, int(start_index or 0))
        self.status.showMessage("Merender preview 360p sesuai permintaan...")
        self._start_preview_worker(
            start_index=start_at,
            reason="Rendered preview sedang dibuat sesuai perubahan review.",
            operation="background",
        )

    def _on_preview_progress(self, current: int, total: int, message: str):
        self._current_preview_segment_index = max(0, min(int(current or 0), max(total - 1, 0)))
        manifest = load_preview_manifest(self.output_dir) or {}
        ready_count = int(manifest.get("ready_count", 0) or 0)
        available_duration = float(manifest.get("available_duration", 0) or 0)
        friendly = f"Rendered preview: {message} | siap {ready_count}/{total} segmen"
        self.review_panel.update_preview_status(ready_count, total, available_duration, friendly)

    def _on_preview_draft_updated(self, path: str, ready_count: int, total: int, available_duration: float, message: str):
        self.draft_path = path
        self.review_panel.update_draft_video(path)
        self.review_panel.update_preview_status(ready_count, total, available_duration, message)
        self.review_panel.hide_inline_error()
        if self._preview_operation == "rerender_all":
            self.review_panel.update_rerender_progress(ready_count, total)
        self.status.showMessage(f"Rendered preview siap {ready_count}/{total} segmen.")

    def _on_preview_done(self, path: str):
        if self.preview_worker:
            self.preview_worker.wait()
        self.preview_worker = None
        manifest = load_preview_manifest(self.output_dir) or {}
        ready_count = int(manifest.get("ready_count", 0) or 0)
        total = len(self.plan.get("segments", [])) if self.plan else 0
        available_duration = float(manifest.get("available_duration", 0) or 0)
        final_path = path or self.draft_path
        if final_path:
            self.draft_path = final_path
            self.review_panel.update_draft_video(final_path)
        self.review_panel.update_preview_status(
            ready_count,
            total,
            available_duration,
            "Rendered preview selesai dirender.",
        )
        self.review_panel.hide_inline_error()
        self.review_panel.hide_rerender_progress()
        self._preview_operation = ""
        self._current_preview_segment_index = -1
        self.status.showMessage("Rendered preview selesai dirender.")
        self._refresh_toolbar_state()

    def _on_preview_error(self, msg: str):
        if self.preview_worker:
            self.preview_worker.wait()
        self.preview_worker = None
        first_line = msg.splitlines()[0] if msg else "unknown"
        self._append_project_log(f"PREVIEW ERROR: {first_line}")
        manifest = load_preview_manifest(self.output_dir) or {}
        ready_count = int(manifest.get("ready_count", 0) or 0)
        total = len(self.plan.get("segments", [])) if self.plan else 0
        available_duration = float(manifest.get("available_duration", 0) or 0)
        self.review_panel.update_preview_status(
            ready_count,
            total,
            available_duration,
            f"Rendered preview gagal: {first_line}",
        )
        title = (
            f"Gagal render preview - Seg {self._current_preview_segment_index + 1}"
            if self._current_preview_segment_index >= 0
            else "Gagal render preview"
        )
        self.review_panel.show_inline_error(
            title,
            msg,
            "Coba klik Render Semua Preview setelah memastikan video segmen tersedia.",
        )
        self.review_panel.hide_rerender_progress()
        self._preview_operation = ""
        self._current_preview_segment_index = -1
        self.status.showMessage("Rendered preview gagal. Review masih bisa dilanjutkan dengan source preview.")
        self._refresh_toolbar_state()

    def _on_final_render(self):
        from core.planner import save_plan

        if not self.plan or not self.output_dir or not self.audio_path:
            QMessageBox.warning(self, "Error", "Project belum siap untuk render final.")
            return

        self._stop_preview_worker()
        plan_path = get_output_cache_paths(self.output_dir)["plan"]
        save_plan(self.plan, plan_path)

        self.status.showMessage("Rendering final video...")
        self.stack.setCurrentWidget(self.progress_panel)
        self.progress_panel.reset()

        self._retry_action = lambda: self._on_final_render()

        self.worker = ReRenderWorker(self.plan, self.audio_path, self.output_dir)
        self.worker.progress.connect(self.progress_panel.update_progress)
        self.worker.download_progress.connect(self.progress_panel.update_download_status)
        self.worker.log.connect(self.progress_panel.append_log)
        self.worker.log.connect(self._append_project_log)
        self.worker.finished.connect(self._on_final_done)
        self.worker.error.connect(self._on_final_error)
        self.worker.start()
        self._refresh_toolbar_state()

    def _on_final_done(self, path: str):
        from core.project_manager import save_project

        self.worker.quit()
        self.worker.wait()
        self.worker = None
        self._retry_action = None
        avep_path = get_output_cache_paths(self.output_dir)["project"]
        try:
            save_project(self.output_dir, avep_path)
            avep_msg = f"\n\nProyek otomatis tersimpan: {avep_path}"
        except Exception as e:
            avep_msg = f"\n\n(Gagal menyimpan proyek .avep: {e})"

        self.status.showMessage(f"Final video tersimpan: {path}")
        QMessageBox.information(
            self,
            "Selesai!",
            f"Video final berhasil dirender!\n\n{path}\n\nFolder proyek:\n{self.output_dir}{avep_msg}",
        )
        self.stack.setCurrentWidget(self.review_panel)
        self._refresh_toolbar_state()

    def _return_to_home(self):
        self._stop_preview_worker()
        if self.worker:
            try:
                if self.worker.isRunning():
                    self.worker.quit()
                    self.worker.wait()
            except Exception:
                pass
        self.worker = None
        self.plan = None
        self.draft_path = None
        self.audio_path = None
        self.output_dir = None
        self.script_draft = {}
        self.pending_start_payload = {}
        self.pending_tts_payload = {}
        self.current_mode = "voiceover"
        self.current_project_mode = "voiceover"
        self.current_review_profile = "standard"
        self.review_panel._on_stop_clicked()
        if hasattr(self.script_refine_panel, 'player') and self.script_refine_panel.player:
            self.script_refine_panel.player.stop()
        self.progress_panel.reset()
        self.stack.setCurrentWidget(self.home_panel)
        self.home_panel.refresh_history()
        self.status.showMessage("Kembali ke beranda.")
        self._refresh_toolbar_state()

    def _on_final_error(self, msg: str):
        if self.worker:
            self.worker.quit()
            self.worker.wait()
        self.worker = None
        self._retry_action = None
        self.status.showMessage("Gagal render final.")
        self._append_project_log(f"FINAL RENDER ERROR: {msg.splitlines()[0] if msg else 'unknown'}")
        QMessageBox.critical(
            self,
            "Gagal render final",
            f"Gagal render final.\n\n{msg}\n\nCoba periksa aset proyek lalu render ulang.",
        )
        self.stack.setCurrentWidget(self.review_panel)
        self._refresh_toolbar_state()

    def _on_download_missing_requested(self, indices: list[int]):
        from core.cache_manager import get_output_cache_paths
        
        paths = get_output_cache_paths(self.output_dir)
        self.worker = ProcessingWorker(self.output_dir, self.audio_path, mode="download_missing")
        self.worker.plan_path = paths["plan"]
        
        self.worker.progress.connect(self.progress_panel.update_progress)
        self.worker.download_progress.connect(self.progress_panel.update_download_progress)
        self.worker.log.connect(self.progress_panel.append_log)
        self.worker.step_done.connect(self._on_step_done)
        self.worker.finished.connect(self._on_download_missing_finished)
        self.worker.error.connect(self._on_error)
        
        self.stack.setCurrentWidget(self.script_refine_panel)
        self.progress_panel.reset(f"Mengunduh {len(indices)} klip video...")
        
        self.worker.start()
        self._refresh_toolbar_state()

    def _on_download_missing_finished(self, _):
        if self.worker:
            self.worker.quit()
            self.worker.wait()
        self.worker = None
        
        from core.planner import load_plan
        paths = get_output_cache_paths(self.output_dir)
        new_plan = load_plan(paths["plan"])
        
        self.review_panel.load_plan(new_plan, self.audio_path, self.output_dir)
        self.stack.setCurrentWidget(self.review_panel)
        self.status.showMessage("Proses pengunduhan klip kosong selesai.")
        self._refresh_toolbar_state()

    def _on_error(self, msg: str):
        self._stop_preview_worker()
        if self.worker:
            self.worker.quit()
            self.worker.wait()
        self.status.showMessage("Error saat memproses.")
        self._append_project_log(f"ERROR: {msg.splitlines()[0] if msg else 'unknown'}")
        dialog = ErrorDialog(self, "Error Pemrosesan", msg, retry_callback=self._retry_action)
        result = dialog.exec()
        self.worker = None
        self._retry_action = None
        if result == ErrorDialog.GO_HOME_RESULT:
            self._return_to_home()
        self._refresh_toolbar_state()

    def _restart_current_project(self):
        if not self.output_dir or not self.audio_path:
            return
        self._stop_preview_worker()
        self._launch_processing_worker(f"Melanjutkan proyek: {self.output_dir}")

    def _append_project_log(self, message: str):
        if self.output_dir:
            append_project_log(self.output_dir, message)
