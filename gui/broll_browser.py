from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from gui.ui_theme import set_widget_props


class BrollBrowser(QDialog):
    def __init__(self, candidates: list, current_chosen: dict = None, parent=None):
        super().__init__(parent)
        self.candidates = candidates
        self.current_chosen = current_chosen
        self.selected_broll = None

        self.setWindowTitle("Pilih B-Roll Alternatif")
        self.resize(900, 600)

        self._build_ui()

    def _build_ui(self):
        self.setStyleSheet(
            """
            QFrame[candidateCard="true"] {
                border-radius: 20px;
            }
            QFrame[candidateCard="true"][currentChoice="true"] {
                background-color: #10291f;
                border: 2px solid #4df0af;
            }
            QFrame[candidateCard="true"][currentChoice="false"]:hover {
                background-color: #13203a;
                border-color: #67b2ff;
            }
            QLabel[candidateThumb="true"] {
                background-color: #08111d;
                border: 1px solid #172641;
                border-radius: 16px;
                padding: 10px;
            }
            QLabel[candidateThumb="true"][empty="true"] {
                color: #8ea5c8;
            }
            QPushButton[currentChoice="true"]:disabled {
                background-color: #2de29a;
                border-color: #4df0af;
                color: #032019;
            }
            """
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(18)

        header = set_widget_props(QFrame(), role="heroCard")
        layout.addWidget(header)

        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(24, 24, 24, 24)
        header_layout.setSpacing(10)

        header_layout.addWidget(set_widget_props(QLabel("B-roll picker"), role="eyebrow"))
        header_layout.addWidget(set_widget_props(QLabel("Pilih B-Roll Manual"), role="sectionTitle"))

        chip_row = QHBoxLayout()
        chip_row.setSpacing(10)

        chip_row.addWidget(
            set_widget_props(QLabel(f"{len(self.candidates)} kandidat"), role="statusChip")
        )
        if self.current_chosen:
            chip_row.addWidget(
                set_widget_props(QLabel("1 pilihan aktif"), role="statusChip", tone="success")
            )
        chip_row.addStretch(1)
        header_layout.addLayout(chip_row)

        browser_frame = set_widget_props(QFrame(), role="panelCard")
        browser_frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout.addWidget(browser_frame, 1)

        browser_layout = QVBoxLayout(browser_frame)
        browser_layout.setContentsMargins(18, 18, 18, 18)
        browser_layout.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        browser_layout.addWidget(scroll)

        container = QWidget()
        grid = QGridLayout(container)
        grid.setContentsMargins(4, 4, 4, 4)
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(16)

        row = 0
        col = 0
        for cand in self.candidates:
            card = self._build_cand_card(cand)
            grid.addWidget(card, row, col)
            col += 1
            if col > 2:
                col = 0
                row += 1

        for column in range(3):
            grid.setColumnStretch(column, 1)

        scroll.setWidget(container)

        footer = QHBoxLayout()
        footer.setSpacing(10)
        footer.addStretch(1)

        btn_cancel = QPushButton("Batal")
        set_widget_props(btn_cancel, variant="ghost")
        btn_cancel.setMinimumWidth(120)
        btn_cancel.clicked.connect(self.reject)
        footer.addWidget(btn_cancel)

        layout.addLayout(footer)

    def _build_cand_card(self, cand: dict) -> QFrame:
        card = QFrame()
        is_current = bool(
            self.current_chosen and cand.get("id") == self.current_chosen.get("id")
        )
        set_widget_props(
            card,
            role="subCard",
            candidateCard="true",
            currentChoice="true" if is_current else "false",
        )
        card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        card.setMinimumWidth(250)

        c_layout = QVBoxLayout(card)
        c_layout.setContentsMargins(16, 16, 16, 16)
        c_layout.setSpacing(12)

        if is_current:
            c_layout.addWidget(
                set_widget_props(QLabel("Sedang dipakai"), role="statusChip", tone="success")
            )

        lbl_img = QLabel()
        lbl_img.setAlignment(Qt.AlignCenter)
        lbl_img.setMinimumHeight(170)
        lbl_img.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        img_path = cand.get("thumbnail_path")
        if img_path:
            pixmap = QPixmap(img_path)
            if not pixmap.isNull():
                lbl_img.setPixmap(
                    pixmap.scaled(250, 150, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                )
            set_widget_props(lbl_img, candidateThumb="true", empty="false")
        else:
            lbl_img.setText("No Thumbnail")
            set_widget_props(lbl_img, candidateThumb="true", empty="true")
        c_layout.addWidget(lbl_img)

        source_text = cand.get("source", "unknown")
        source_label = set_widget_props(QLabel(f"Source: {source_text}"), role="subTitle")
        source_label.setWordWrap(True)
        c_layout.addWidget(source_label)

        url_text = cand.get("url", cand.get("video_url", "unknown"))
        url_label = set_widget_props(QLabel(f"URL: {url_text[:30]}..."), role="previewMeta")
        url_label.setWordWrap(True)
        c_layout.addWidget(url_label)

        c_layout.addStretch(1)

        btn_choose = QPushButton("Terpilih" if is_current else "Pilih")
        set_widget_props(
            btn_choose,
            variant="primary" if not is_current else "secondary",
            currentChoice="true" if is_current else "false",
        )
        btn_choose.setCursor(Qt.PointingHandCursor)
        if is_current:
            btn_choose.setEnabled(False)
        else:
            def on_click(checked=False, c=cand):
                self.selected_broll = c
                self.accept()

            btn_choose.clicked.connect(on_click)

        c_layout.addWidget(btn_choose)
        return card
