"""Progress panel UI."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from gui.ui_theme import set_widget_props


class ProgressPanel(QWidget):
    def __init__(self):
        super().__init__()
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 28, 28, 28)
        root.setSpacing(20)
        root.setAlignment(Qt.AlignTop | Qt.AlignHCenter)

        shell = set_widget_props(QFrame(), role="heroCard")
        shell.setMaximumWidth(980)
        shell.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        root.addWidget(shell, 1)

        shell_layout = QVBoxLayout(shell)
        shell_layout.setContentsMargins(28, 28, 28, 28)
        shell_layout.setSpacing(20)

        header_row = QHBoxLayout()
        header_row.setSpacing(16)

        title_col = QVBoxLayout()
        title_col.setSpacing(8)

        title_col.addWidget(set_widget_props(QLabel("Workflow aktif"), role="eyebrow"))

        self.title = set_widget_props(QLabel("Memproses..."), role="heroTitle")
        self.title.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        title_col.addWidget(self.title)

        self.message = set_widget_props(QLabel("Memulai..."), role="heroSubtitle")
        self.message.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.message.setWordWrap(True)
        title_col.addWidget(self.message)

        header_row.addLayout(title_col, 1)

        self.step_label = set_widget_props(QLabel("Langkah 0 / 0"), role="statusChip")
        self.step_label.setAlignment(Qt.AlignCenter)
        self.step_label.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        header_row.addWidget(self.step_label, 0, Qt.AlignTop)

        shell_layout.addLayout(header_row)

        status_frame = set_widget_props(QFrame(), role="panelCard")
        shell_layout.addWidget(status_frame)

        status_layout = QVBoxLayout(status_frame)
        status_layout.setContentsMargins(22, 22, 22, 22)
        status_layout.setSpacing(14)

        status_layout.addWidget(set_widget_props(QLabel("Info download"), role="subTitle"))

        self.download_label = set_widget_props(QLabel(""), role="infoBanner")
        self.download_label.setAlignment(Qt.AlignCenter)
        self.download_label.setWordWrap(True)
        self.download_label.setMaximumWidth(800)
        self.download_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        status_layout.addWidget(self.download_label)

        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setValue(0)
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(12)
        self.bar.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        status_layout.addWidget(self.bar)

        console_frame = set_widget_props(QFrame(), role="panelCard")
        console_frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        shell_layout.addWidget(console_frame, 1)

        console_layout = QVBoxLayout(console_frame)
        console_layout.setContentsMargins(22, 22, 22, 22)
        console_layout.setSpacing(14)

        console_header = QHBoxLayout()
        console_header.setSpacing(12)
        console_header.addWidget(set_widget_props(QLabel("Log proses"), role="sectionTitle"))
        console_header.addStretch(1)
        console_layout.addLayout(console_header)

        self.log_console = QTextEdit()
        self.log_console.setReadOnly(True)
        self.log_console.setMinimumHeight(220)
        self.log_console.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        set_widget_props(self.log_console, role="codeConsole")
        console_layout.addWidget(self.log_console, 1)

        button_row = QHBoxLayout()
        button_row.setSpacing(10)
        button_row.addStretch(1)

        self.btn_clear_log = QPushButton("Clear Log")
        set_widget_props(self.btn_clear_log, variant="ghost")
        self.btn_clear_log.setMinimumWidth(120)
        self.btn_clear_log.clicked.connect(self.log_console.clear)
        button_row.addWidget(self.btn_clear_log)

        self.btn_clear_download = QPushButton("Clear Info Download")
        set_widget_props(self.btn_clear_download, variant="secondary")
        self.btn_clear_download.setMinimumWidth(180)
        self.btn_clear_download.clicked.connect(lambda: self.download_label.setText(""))
        button_row.addWidget(self.btn_clear_download)

        console_layout.addLayout(button_row)

    def reset(self, initial_message: str = "Memulai..."):
        self.bar.setValue(0)
        self.message.setText(initial_message)
        self.step_label.setText("Langkah 0 / 0")
        self.download_label.setText("")
        self.log_console.clear()

    def update_download_status(self, downloaded: int, total: int, message: str):
        self.download_label.setText(message)

    def update_progress(self, current: int, total: int, message: str):
        pct = int((current / max(total, 1)) * 100)
        self.bar.setValue(pct)
        self.message.setText(message)
        if total > 0:
            step_index = min(max(current, 0), total)
            self.step_label.setText(f"Langkah {step_index} / {total}")
        else:
            self.step_label.setText("Langkah 0 / 0")

    def append_log(self, text: str):
        self.log_console.append(text)
        scrollbar = self.log_console.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
