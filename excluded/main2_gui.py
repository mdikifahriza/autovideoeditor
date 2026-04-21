import os
import sys
from pathlib import Path

from PySide6.QtCore import QProcess
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QProgressBar,
)

from config import OUTPUT_BITRATE, OUTPUT_FPS, OUTPUT_HEIGHT, OUTPUT_WIDTH


class Main2Window(QMainWindow):
    def __init__(self):
        super().__init__()
        self.process = QProcess(self)
        self.last_output_path = ""
        self._build_ui()
        self._wire_process()

    def _build_ui(self):
        self.setWindowTitle("Main2 Fast Render GUI")
        self.resize(980, 680)

        root = QWidget()
        self.setCentralWidget(root)
        main_layout = QVBoxLayout(root)
        main_layout.setContentsMargins(14, 14, 14, 14)
        main_layout.setSpacing(10)

        form = QGridLayout()
        form.setHorizontalSpacing(8)
        form.setVerticalSpacing(8)

        row = 0
        form.addWidget(QLabel("Project"), row, 0)
        self.input_project = QLineEdit()
        self.input_project.setPlaceholderText("Pilih folder proyek atau file .avep")
        form.addWidget(self.input_project, row, 1)
        btn_pick_folder = QPushButton("Folder")
        btn_pick_folder.clicked.connect(self._pick_project_folder)
        form.addWidget(btn_pick_folder, row, 2)
        btn_pick_avep = QPushButton(".avep")
        btn_pick_avep.clicked.connect(self._pick_project_avep)
        form.addWidget(btn_pick_avep, row, 3)

        row += 1
        form.addWidget(QLabel("Audio"), row, 0)
        self.input_audio = QLineEdit()
        self.input_audio.setPlaceholderText("Opsional: isi audio untuk auto-buat proyek baru")
        form.addWidget(self.input_audio, row, 1, 1, 2)
        btn_pick_audio = QPushButton("Audio")
        btn_pick_audio.clicked.connect(self._pick_audio_file)
        form.addWidget(btn_pick_audio, row, 3)

        row += 1
        form.addWidget(QLabel("Nama Proyek"), row, 0)
        self.input_project_name = QLineEdit()
        self.input_project_name.setPlaceholderText("Opsional (dipakai saat Project kosong + Audio diisi)")
        form.addWidget(self.input_project_name, row, 1, 1, 3)

        row += 1
        form.addWidget(QLabel("Output"), row, 0)
        self.input_output = QLineEdit()
        self.input_output.setPlaceholderText("Opsional (kosong = default final_video_fast.mp4)")
        form.addWidget(self.input_output, row, 1, 1, 2)
        btn_pick_output = QPushButton("Pilih")
        btn_pick_output.clicked.connect(self._pick_output_file)
        form.addWidget(btn_pick_output, row, 3)

        row += 1
        form.addWidget(QLabel("Width"), row, 0)
        self.spin_width = QSpinBox()
        self.spin_width.setRange(320, 3840)
        self.spin_width.setValue(int(OUTPUT_WIDTH))
        form.addWidget(self.spin_width, row, 1)

        form.addWidget(QLabel("Height"), row, 2)
        self.spin_height = QSpinBox()
        self.spin_height.setRange(180, 2160)
        self.spin_height.setValue(int(OUTPUT_HEIGHT))
        form.addWidget(self.spin_height, row, 3)

        row += 1
        form.addWidget(QLabel("FPS"), row, 0)
        self.spin_fps = QSpinBox()
        self.spin_fps.setRange(10, 60)
        self.spin_fps.setValue(int(OUTPUT_FPS))
        form.addWidget(self.spin_fps, row, 1)

        form.addWidget(QLabel("Bitrate"), row, 2)
        self.input_bitrate = QLineEdit(str(OUTPUT_BITRATE))
        form.addWidget(self.input_bitrate, row, 3)

        row += 1
        self.chk_no_download = QCheckBox("No Download (jangan unduh B-roll yang hilang)")
        form.addWidget(self.chk_no_download, row, 0, 1, 4)

        row += 1
        self.chk_rebuild_plan = QCheckBox(
            "Rebuild Plan (transkripsi Gemini 2.5 Flash + generate plan + fallback media)"
        )
        form.addWidget(self.chk_rebuild_plan, row, 0, 1, 4)

        main_layout.addLayout(form)

        action_row = QHBoxLayout()
        self.btn_start = QPushButton("Render Cepat")
        self.btn_start.clicked.connect(self._start_render)
        action_row.addWidget(self.btn_start)

        self.btn_stop = QPushButton("Stop")
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self._stop_render)
        action_row.addWidget(self.btn_stop)

        self.btn_open_output = QPushButton("Buka Folder Output")
        self.btn_open_output.setEnabled(False)
        self.btn_open_output.clicked.connect(self._open_output_folder)
        action_row.addWidget(self.btn_open_output)
        action_row.addStretch(1)
        main_layout.addLayout(action_row)

        self.progress = QProgressBar()
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        main_layout.addWidget(self.progress)

        self.label_status = QLabel("Siap.")
        main_layout.addWidget(self.label_status)

        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        main_layout.addWidget(self.log_box, 1)

    def _wire_process(self):
        self.process.setProcessChannelMode(QProcess.SeparateChannels)
        self.process.readyReadStandardOutput.connect(self._read_stdout)
        self.process.readyReadStandardError.connect(self._read_stderr)
        self.process.finished.connect(self._on_finished)

    def _append_log(self, text: str):
        if not text:
            return
        self.log_box.moveCursor(QTextCursor.End)
        self.log_box.insertPlainText(text)
        if not text.endswith("\n"):
            self.log_box.insertPlainText("\n")
        self.log_box.ensureCursorVisible()

    def _pick_project_folder(self):
        path = QFileDialog.getExistingDirectory(self, "Pilih Folder Proyek")
        if path:
            self.input_project.setText(path)

    def _pick_project_avep(self):
        path, _ = QFileDialog.getOpenFileName(self, "Pilih File .avep", "", "Project (*.avep)")
        if path:
            self.input_project.setText(path)

    def _pick_output_file(self):
        path, _ = QFileDialog.getSaveFileName(self, "Simpan Final MP4", "", "Video (*.mp4)")
        if path:
            if not path.lower().endswith(".mp4"):
                path += ".mp4"
            self.input_output.setText(path)

    def _pick_audio_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Pilih Audio Voice Over",
            "",
            "Audio (*.mp3 *.wav *.m4a *.aac *.flac *.ogg)",
        )
        if path:
            self.input_audio.setText(path)

    def _set_running_state(self, running: bool):
        self.btn_start.setEnabled(not running)
        self.btn_stop.setEnabled(running)
        self.btn_open_output.setEnabled((not running) and bool(self.last_output_path and os.path.exists(self.last_output_path)))
        self.input_project.setEnabled(not running)
        self.input_audio.setEnabled(not running)
        self.input_project_name.setEnabled(not running)
        self.input_output.setEnabled(not running)
        self.spin_width.setEnabled(not running)
        self.spin_height.setEnabled(not running)
        self.spin_fps.setEnabled(not running)
        self.input_bitrate.setEnabled(not running)
        self.chk_no_download.setEnabled(not running)
        self.chk_rebuild_plan.setEnabled(not running)
        if running:
            self.progress.setRange(0, 0)
        else:
            self.progress.setRange(0, 1)
            self.progress.setValue(1)

    def _expected_output_path(self, project_input: str, output_input: str) -> str:
        if output_input.strip():
            return os.path.abspath(output_input.strip())
        project_input = os.path.abspath(project_input.strip())
        if os.path.isfile(project_input) and project_input.lower().endswith(".avep"):
            stem = Path(project_input).stem
            return os.path.join(os.path.dirname(project_input), f"{stem}_final_fast.mp4")
        return os.path.join(project_input, "exports", "final_video_fast.mp4")

    def _start_render(self):
        project = self.input_project.text().strip()
        audio = self.input_audio.text().strip()
        project_name = self.input_project_name.text().strip()

        if not project and not audio:
            QMessageBox.warning(self, "Error", "Isi salah satu: Project atau Audio.")
            return
        if project and not os.path.exists(project):
            QMessageBox.warning(self, "Error", f"Path tidak ditemukan:\n{project}")
            return
        if audio and not os.path.exists(audio):
            QMessageBox.warning(self, "Error", f"File audio tidak ditemukan:\n{audio}")
            return

        script_path = os.path.join(os.path.dirname(__file__), "main2.py")
        if not os.path.exists(script_path):
            QMessageBox.critical(self, "Error", f"File main2.py tidak ditemukan:\n{script_path}")
            return

        output = self.input_output.text().strip()
        if output:
            self.last_output_path = os.path.abspath(output)
        elif project:
            self.last_output_path = self._expected_output_path(project, output)
        else:
            self.last_output_path = ""

        args = [
            "-u",
            script_path,
            "--width",
            str(int(self.spin_width.value())),
            "--height",
            str(int(self.spin_height.value())),
            "--fps",
            str(int(self.spin_fps.value())),
            "--bitrate",
            self.input_bitrate.text().strip() or str(OUTPUT_BITRATE),
        ]
        if project:
            args.extend(["--project", project])
        if audio:
            args.extend(["--audio", audio])
        if project_name:
            args.extend(["--project-name", project_name])
        if output:
            args.extend(["--output", output])
        if self.chk_no_download.isChecked():
            args.append("--no-download")
        if self.chk_rebuild_plan.isChecked():
            args.append("--rebuild-plan")

        self.log_box.clear()
        self._append_log(f"[GUI] Start: {sys.executable} {' '.join(args)}")
        self.label_status.setText("Rendering...")
        self._set_running_state(True)
        self.process.start(sys.executable, args)
        if not self.process.waitForStarted(3000):
            self._set_running_state(False)
            self.label_status.setText("Gagal mulai proses.")
            QMessageBox.critical(self, "Error", "Gagal memulai proses render.")

    def _stop_render(self):
        if self.process.state() != QProcess.NotRunning:
            self._append_log("[GUI] Proses dihentikan user.")
            self.process.kill()

    def _read_stdout(self):
        data = bytes(self.process.readAllStandardOutput()).decode("utf-8", errors="ignore")
        if data:
            self._append_log(data)

    def _read_stderr(self):
        data = bytes(self.process.readAllStandardError()).decode("utf-8", errors="ignore")
        if data:
            self._append_log(data)

    def _on_finished(self, exit_code: int, _exit_status):
        self._set_running_state(False)
        if exit_code == 0:
            self.label_status.setText("Selesai.")
            output_exists = bool(self.last_output_path and os.path.exists(self.last_output_path))
            self.btn_open_output.setEnabled(output_exists)
            if output_exists:
                QMessageBox.information(
                    self,
                    "Sukses",
                    f"Render selesai.\n\nOutput:\n{self.last_output_path}",
                )
            else:
                if not self.last_output_path:
                    QMessageBox.information(
                        self,
                        "Selesai",
                        "Proses selesai.\nPath output final ada di log (baris '[main2] Selesai. Output final: ...').",
                    )
                    return
                QMessageBox.information(
                    self,
                    "Selesai",
                    "Proses selesai, tapi file output tidak terdeteksi di path default.\nCek log untuk detail.",
                )
            return

        self.label_status.setText("Gagal.")
        QMessageBox.critical(
            self,
            "Gagal",
            "Render gagal. Cek log di bawah untuk detail error.",
        )

    def _open_output_folder(self):
        if not self.last_output_path:
            return
        folder = os.path.dirname(self.last_output_path)
        if os.path.isdir(folder):
            os.startfile(folder)


def main():
    app = QApplication(sys.argv)
    win = Main2Window()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
