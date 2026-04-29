# -*- coding: utf-8 -*-
"""
Dreamina UI - 与网页版一致的对话框样式
一个对话框容器，内部包含所有功能选项
"""

from PySide6 import QtWidgets, QtCore
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QTextEdit, QPushButton,
    QComboBox, QSlider, QFrame,
)


# ============ 样式常量 - 深色主题 ============

COLORS = {
    "bg": "#161b22",              # 深色背景
    "text": "#c9d1d9",            # 浅色文字
    "text_secondary": "#8b949e",   # 灰色次级文字
    "border": "#30363d",          # 边框色
    "border_focus": "#4a90d9",    # 聚焦边框蓝
    "accent": "#4a90d9",          # 蓝色强调
    "accent_hover": "#6ba3e0",    # 蓝色悬停
    "text_on_accent": "#ffffff",   # 白色文字
    "placeholder": "#6e7681",      # 占位符
    "bg_hover": "#21262d",        # 悬停背景
}


# ============ 自定义下拉框 ============

class DreaminaCombo(QComboBox):
    """Dreamina 风格下拉框"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(32)
        self.setFont(QFont("Segoe UI", 11))
        self._apply_style()

    def _apply_style(self):
        self.setStyleSheet(f"""
            QComboBox {{
                background-color: transparent;
                color: {COLORS['text']};
                border: 1px solid {COLORS['border']};
                border-radius: 4px;
                padding: 4px 28px 4px 8px;
                min-width: 100px;
            }}
            QComboBox:hover {{
                border-color: {COLORS['text_secondary']};
            }}
            QComboBox:focus {{
                border-color: {COLORS['border_focus']};
            }}
            QComboBox::drop-down {{
                border: none;
                width: 24px;
            }}
            QComboBox::down-arrow {{
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 5px solid {COLORS['text_secondary']};
                margin-right: 6px;
            }}
            QComboBox QAbstractItemView {{
                background: {COLORS['bg']};
                color: {COLORS['text']};
                border: 1px solid {COLORS['border']};
                border-radius: 4px;
                selection-background-color: {COLORS['bg_hover']};
                padding: 4px;
                outline: none;
            }}
        """)


# ============ 选项按钮 ============

class SelectButton(QPushButton):
    """可点击选择的按钮"""

    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.setFixedHeight(28)
        self.setFont(QFont("Segoe UI", 10))
        self._is_selected = False
        self._update_style()

    def set_selected(self, selected: bool):
        self._is_selected = selected
        self._update_style()

    def _update_style(self):
        if self._is_selected:
            self.setStyleSheet(f"""
                QPushButton {{
                    background: {COLORS['accent']};
                    color: {COLORS['text_on_accent']};
                    border: none;
                    border-radius: 4px;
                    font-weight: 500;
                }}
            """)
        else:
            self.setStyleSheet(f"""
                QPushButton {{
                    background: transparent;
                    color: {COLORS['text_secondary']};
                    border: 1px solid {COLORS['border']};
                    border-radius: 4px;
                }}
                QPushButton:hover {{
                    border-color: {COLORS['text_secondary']};
                }}
            """)


class TagButton(QPushButton):
    """标签样式按钮（模型类型选择）"""

    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.setFixedHeight(32)
        self.setFont(QFont("Segoe UI", 11))
        self._is_selected = False
        self._update_style()

    def set_selected(self, selected: bool):
        self._is_selected = selected
        self._update_style()

    def _update_style(self):
        if self._is_selected:
            self.setStyleSheet(f"""
                QPushButton {{
                    background: {COLORS['bg_hover']};
                    color: {COLORS['text']};
                    border: 1px solid {COLORS['border']};
                    border-radius: 16px;
                    padding: 4px 16px;
                    font-weight: 500;
                }}
            """)
        else:
            self.setStyleSheet(f"""
                QPushButton {{
                    background: transparent;
                    color: {COLORS['text_secondary']};
                    border: none;
                    border-radius: 16px;
                    padding: 4px 16px;
                }}
                QPushButton:hover {{
                    background: {COLORS['bg_hover']};
                    color: {COLORS['text']};
                }}
            """)


# ============ 主对话框面板 ============

class DreaminaDialog(QWidget):
    """
    Dreamina 主对话框 - 参考网页布局
    单一对话框容器，内部包含所有功能选项
    """

    # 信号
    generate_clicked = Signal(dict)
    save_preset_clicked = Signal(dict)
    load_preset_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        # 数据配置
        self._model_types = ["AI Video", "AI Image", "AI Avatar", "Audio Generation", "Mimic Motion", "AI Agent"]
        self._model_versions = {
            "AI Video": ["Dreamina Seedance 2.0 Fast", "Dreamina Seedance 2.0", "Dreamina Seedance 1.0 Mini"],
            "AI Image": ["Seedream 4.1", "Seedream 3.1"],
            "AI Avatar": ["OmniHuman"],
            "AI Agent": ["Agent 1.0"],
            "Audio Generation": ["Feel the scene"],
            "Mimic Motion": ["Motion 1.0"],
        }
        self._reference_modes = ["Omni reference", "First and last frames", "Multiframes"]
        self._ratios = ["16:9", "9:16", "1:1", "4:3"]
        self._durations = ["5s", "10s", "15s"]

        self._current_type = "AI Video"
        self._ratio_buttons = {}
        self._duration_buttons = {}
        self._type_buttons = {}

        self._setup_ui()

    def _setup_ui(self):
        """构建对话框 UI"""

        # 主容器 - 对话框样式
        container = QFrame()
        container.setStyleSheet(f"""
            QFrame {{
                background: {COLORS['bg']};
                border: 1px solid {COLORS['border']};
                border-radius: 12px;
            }}
        """)

        main_layout = QVBoxLayout(container)
        main_layout.setContentsMargins(24, 24, 24, 24)
        main_layout.setSpacing(20)

        # ===== 1. 顶部标题 =====
        title = QLabel("Start creating with")
        title.setFont(QFont("Segoe UI", 12))
        title.setStyleSheet(f"color: {COLORS['text_secondary']};")
        main_layout.addWidget(title)

        # ===== 2. 模型类型选择（横向排列） =====
        types_layout = QHBoxLayout()
        types_layout.setSpacing(8)
        for type_name in self._model_types:
            btn = TagButton(type_name)
            btn.set_selected(type_name == self._current_type)
            btn.clicked.connect(lambda checked, t=type_name: self._on_type_selected(t))
            self._type_buttons[type_name] = btn
            types_layout.addWidget(btn)
        types_layout.addStretch()
        main_layout.addLayout(types_layout)

        # ===== 3. Reference 上传区 =====
        ref_layout = QHBoxLayout()
        ref_layout.setSpacing(12)

        self.ref_btn = QPushButton("Reference")
        self.ref_btn.setFont(QFont("Segoe UI", 11))
        self.ref_btn.setCursor(Qt.PointingHandCursor)
        self.ref_btn.setFixedHeight(36)
        self.ref_btn.setStyleSheet(f"""
            QPushButton {{
                background: {COLORS['bg']};
                color: {COLORS['text']};
                border: 1px dashed {COLORS['border']};
                border-radius: 8px;
                padding: 0 16px;
                text-align: left;
            }}
            QPushButton:hover {{
                border-color: {COLORS['accent']};
                color: {COLORS['accent']};
            }}
        """)
        self.ref_btn.clicked.connect(self._on_select_files)
        ref_layout.addWidget(self.ref_btn)

        self.ref_label = QLabel("Upload up to 12 references...")
        self.ref_label.setFont(QFont("Segoe UI", 10))
        self.ref_label.setStyleSheet(f"color: {COLORS['placeholder']};")
        ref_layout.addWidget(self.ref_label, 1)
        main_layout.addLayout(ref_layout)

        # ===== 4. Model 下拉 =====
        model_layout = QHBoxLayout()
        model_layout.setSpacing(8)

        model_label = QLabel("Model:")
        model_label.setFont(QFont("Segoe UI", 11))
        model_label.setStyleSheet(f"color: {COLORS['text_secondary']}; min-width: 50px;")
        model_layout.addWidget(model_label)

        self.model_combo = DreaminaCombo()
        self.model_combo.addItems(self._model_versions[self._current_type])
        model_layout.addWidget(self.model_combo, 1)
        main_layout.addLayout(model_layout)

        # ===== 5. Mode 下拉 =====
        mode_layout = QHBoxLayout()
        mode_layout.setSpacing(8)

        mode_label = QLabel("Mode:")
        mode_label.setFont(QFont("Segoe UI", 11))
        mode_label.setStyleSheet(f"color: {COLORS['text_secondary']}; min-width: 50px;")
        mode_layout.addWidget(mode_label)

        self.mode_combo = DreaminaCombo()
        self.mode_combo.addItems(self._reference_modes)
        mode_layout.addWidget(self.mode_combo, 1)
        main_layout.addLayout(mode_layout)

        # ===== 6. Aspect + Duration（横向排列） =====
        ratio_duration_layout = QHBoxLayout()
        ratio_duration_layout.setSpacing(24)

        # Aspect
        aspect_layout = QHBoxLayout()
        aspect_layout.setSpacing(8)

        aspect_label = QLabel("Aspect:")
        aspect_label.setFont(QFont("Segoe UI", 11))
        aspect_label.setStyleSheet(f"color: {COLORS['text_secondary']};")
        aspect_layout.addWidget(aspect_label)

        for ratio in self._ratios:
            btn = SelectButton(ratio)
            btn.set_selected(ratio == "16:9")
            btn.clicked.connect(lambda checked, r=ratio: self._on_ratio_selected(r))
            self._ratio_buttons[ratio] = btn
            aspect_layout.addWidget(btn)

        ratio_duration_layout.addLayout(aspect_layout)

        # Duration
        duration_layout = QHBoxLayout()
        duration_layout.setSpacing(8)

        duration_label = QLabel("Duration:")
        duration_label.setFont(QFont("Segoe UI", 11))
        duration_label.setStyleSheet(f"color: {COLORS['text_secondary']};")
        duration_layout.addWidget(duration_label)

        for duration in self._durations:
            btn = SelectButton(duration)
            btn.set_selected(duration == "5s")
            btn.clicked.connect(lambda checked, d=duration: self._on_duration_selected(d))
            self._duration_buttons[duration] = btn
            duration_layout.addWidget(btn)

        ratio_duration_layout.addLayout(duration_layout)
        ratio_duration_layout.addStretch()

        main_layout.addLayout(ratio_duration_layout)

        # ===== 7. Intensity 滑块 =====
        intensity_layout = QHBoxLayout()
        intensity_layout.setSpacing(8)

        intensity_label = QLabel("Intensity:")
        intensity_label.setFont(QFont("Segoe UI", 11))
        intensity_label.setStyleSheet(f"color: {COLORS['text_secondary']};")
        intensity_layout.addWidget(intensity_label)

        self.intensity_slider = QSlider(Qt.Horizontal)
        self.intensity_slider.setMinimum(0)
        self.intensity_slider.setMaximum(100)
        self.intensity_slider.setValue(70)
        self.intensity_slider.setFixedHeight(20)
        self.intensity_slider.setStyleSheet(f"""
            QSlider {{
                background: transparent;
            }}
            QSlider::groove:horizontal {{
                background: {COLORS['bg_hover']};
                height: 4px;
                border-radius: 2px;
            }}
            QSlider::handle:horizontal {{
                background: {COLORS['text']};
                width: 14px;
                height: 14px;
                margin: -5px 0;
                border-radius: 7px;
            }}
            QSlider::sub-page:horizontal {{
                background: {COLORS['accent']};
                border-radius: 2px;
            }}
        """)
        intensity_layout.addWidget(self.intensity_slider, 1)

        self.intensity_label = QLabel("70")
        self.intensity_label.setFont(QFont("Segoe UI", 11, QFont.Bold))
        self.intensity_label.setFixedWidth(28)
        self.intensity_label.setAlignment(Qt.AlignCenter)
        self.intensity_label.setStyleSheet(f"color: {COLORS['text']};")
        intensity_layout.addWidget(self.intensity_label)

        self.intensity_slider.valueChanged.connect(
            lambda v: self.intensity_label.setText(str(v))
        )

        main_layout.addLayout(intensity_layout)

        # ===== 8. Prompt 输入框 =====
        self.prompt_input = QTextEdit()
        self.prompt_input.setPlaceholderText("Describe the video you're imagining")
        self.prompt_input.setFont(QFont("Segoe UI", 12))
        self.prompt_input.setMinimumHeight(80)
        self.prompt_input.setMaximumHeight(120)
        self.prompt_input.setStyleSheet(f"""
            QTextEdit {{
                background: transparent;
                color: {COLORS['text']};
                border: 1px solid {COLORS['border']};
                border-radius: 8px;
                padding: 12px;
            }}
            QTextEdit:focus {{
                border-color: {COLORS['border_focus']};
            }}
            QTextEdit::placeholder {{
                color: {COLORS['placeholder']};
            }}
        """)
        main_layout.addWidget(self.prompt_input)

        # ===== 9. 按钮行 =====
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(12)

        self.btn_load = QPushButton("📂 加载预设")
        self.btn_load.setFont(QFont("Segoe UI", 10))
        self.btn_load.setCursor(Qt.PointingHandCursor)
        self.btn_load.setFixedHeight(36)
        self.btn_load.setStyleSheet(f"""
            QPushButton {{
                background: {COLORS['bg_hover']};
                color: {COLORS['text']};
                border: 1px solid {COLORS['border']};
                border-radius: 4px;
                padding: 0 16px;
            }}
            QPushButton:hover {{
                border-color: {COLORS['text_secondary']};
            }}
        """)
        self.btn_load.clicked.connect(self.load_preset_clicked.emit)

        self.btn_save = QPushButton("💾 保存预设")
        self.btn_save.setFont(QFont("Segoe UI", 10))
        self.btn_save.setCursor(Qt.PointingHandCursor)
        self.btn_save.setFixedHeight(36)
        self.btn_save.setStyleSheet(f"""
            QPushButton {{
                background: {COLORS['bg_hover']};
                color: {COLORS['text']};
                border: 1px solid {COLORS['border']};
                border-radius: 4px;
                padding: 0 16px;
            }}
            QPushButton:hover {{
                border-color: {COLORS['text_secondary']};
            }}
        """)
        self.btn_save.clicked.connect(self._on_save)

        btn_layout.addWidget(self.btn_load)
        btn_layout.addWidget(self.btn_save)
        btn_layout.addStretch()

        self.btn_generate = QPushButton("See results")
        self.btn_generate.setFont(QFont("Segoe UI", 12, QFont.Bold))
        self.btn_generate.setCursor(Qt.PointingHandCursor)
        self.btn_generate.setFixedHeight(40)
        self.btn_generate.setStyleSheet(f"""
            QPushButton {{
                background: {COLORS['accent']};
                color: {COLORS['text_on_accent']};
                border: none;
                border-radius: 8px;
                padding: 0 32px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background: {COLORS['accent_hover']};
            }}
        """)
        self.btn_generate.clicked.connect(self._on_generate)

        btn_layout.addWidget(self.btn_generate)
        main_layout.addLayout(btn_layout)

        # ===== 外层布局 =====
        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 16, 16, 16)
        outer.addWidget(container)

    def _on_type_selected(self, type_name: str):
        """模型类型选择"""
        for name, btn in self._type_buttons.items():
            btn.set_selected(name == type_name)
        self._current_type = type_name

        self.model_combo.clear()
        self.model_combo.addItems(self._model_versions[type_name])

    def _on_ratio_selected(self, ratio: str):
        for r, btn in self._ratio_buttons.items():
            btn.set_selected(r == ratio)

    def _on_duration_selected(self, duration: str):
        for d, btn in self._duration_buttons.items():
            btn.set_selected(d == duration)

    def _on_select_files(self):
        files, _ = QtWidgets.QFileDialog.getOpenFileNames(
            self,
            "选择参考文件",
            "",
            "媒体文件 (*.png *.jpg *.jpeg *.mp4 *.avi *.mov *.mp3 *.wav);;所有文件 (*.*)"
        )
        if files:
            self.ref_btn.setText(f"Reference ({len(files)})")

    def _on_save(self):
        config = self.get_config()
        self.save_preset_clicked.emit(config)

    def _on_generate(self):
        self.generate_clicked.emit(self.get_config())

    def get_config(self) -> dict:
        return {
            "model_type": self._current_type,
            "model_version": self.model_combo.currentText(),
            "reference_mode": self.mode_combo.currentText(),
            "aspect_ratio": self._get_selected_ratio(),
            "duration": self._get_selected_duration(),
            "intensity": self.intensity_slider.value(),
            "prompt": self.prompt_input.toPlainText(),
        }

    def _get_selected_ratio(self) -> str:
        for r, btn in self._ratio_buttons.items():
            if btn._is_selected:
                return r
        return "16:9"

    def _get_selected_duration(self) -> str:
        for d, btn in self._duration_buttons.items():
            if btn._is_selected:
                return d
        return "5s"


# 别名 - 兼容旧代码
DreaminaControlPanel = DreaminaDialog
