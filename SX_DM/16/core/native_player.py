# -*- coding: utf-8 -*-
import logging
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
                               QSlider, QLabel, QFrame, QGraphicsView, QGraphicsScene)
from PySide6.QtGui import QPainter
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtMultimediaWidgets import QGraphicsVideoItem
from PySide6.QtCore import Qt, QUrl, QTimer, QEvent, QPoint, QSizeF

logger = logging.getLogger("SX_DM.native_player")


# ============================================================
# === 自定义可点击进度条 ===
# ============================================================
class ClickableSlider(QSlider):
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            if self.width() > 0:
                val = self.minimum() + (self.maximum() - self.minimum()) * event.position().x() / self.width()
                self.setValue(int(val))
                self.sliderMoved.emit(int(val))
        super().mousePressEvent(event)


class NativePlayer(QWidget):
    def __init__(self):
        super().__init__()
        # 无边框 + 永远置顶 + 隐藏任务栏图标
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setStyleSheet("background-color: #000000; border-radius: 8px;")
        self.resize(800, 450)
        self.setMouseTracking(True)

        self._is_fullscreen = False
        self._is_tracking = False
        self._start_pos = QPoint()

        # ============================================================
        # === 图形视图架构（替代 QVideoWidget，解决显卡遮挡） ===
        # ============================================================

        # 场景
        self.scene = QGraphicsScene(self)
        self.scene.setSceneRect(0, 0, 800, 450)

        # 视图（铺满整个窗口）
        self.view = QGraphicsView(self.scene, self)
        self.view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.view.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.view.setStyleSheet("background-color: black; border: none;")
        self.view.setRenderHint(QPainter.Antialiasing)
        self.view.setMouseTracking(True)
        self.view.viewport().setMouseTracking(True)
        self.view.installEventFilter(self)
        self.view.viewport().installEventFilter(self)

        # 视频 Item
        self.video_item = QGraphicsVideoItem()
        self.video_item.setAspectRatioMode(Qt.KeepAspectRatio)
        self.scene.addItem(self.video_item)

        # 媒体播放器
        self.player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.player.setAudioOutput(self.audio_output)
        self.player.setVideoOutput(self.video_item)

        # ============================================================
        # === 绝对定位悬浮 UI（带透明度效果） ===
        # ============================================================

        # --- 顶部关闭栏 ---
        self.top_bar = QFrame(self)
        self.top_bar.setAttribute(Qt.WA_StyledBackground, True)
        self.top_bar.setStyleSheet("""
            background-color: rgba(20, 20, 22, 0.85);
            border-top-left-radius: 8px; border-top-right-radius: 8px;
        """)
        top_layout = QHBoxLayout(self.top_bar)
        top_layout.setContentsMargins(0, 5, 12, 5)
        top_layout.addStretch(1)

        self.close_btn = QPushButton("✕")
        self.close_btn.setFixedSize(30, 30)
        self.close_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(255, 255, 255, 0.15);
                color: white;
                border-radius: 15px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #ff4444; }
        """)
        self.close_btn.clicked.connect(self.stop_and_hide)
        top_layout.addWidget(self.close_btn)

        # --- 底部控制栏 ---
        self.control_bar = QFrame(self)
        self.control_bar.setAttribute(Qt.WA_StyledBackground, True)
        self.control_bar.setStyleSheet("""
            background-color: rgba(20, 20, 22, 0.85);
            border-bottom-left-radius: 8px; border-bottom-right-radius: 8px;
        """)
        control_layout = QHBoxLayout(self.control_bar)
        control_layout.setContentsMargins(15, 0, 15, 0)
        control_layout.setSpacing(12)

        self.play_btn = QPushButton("⏸")
        self.play_btn.setFixedSize(28, 28)
        self.play_btn.setStyleSheet("color: white; font-size: 16px; border: none; background: transparent;")
        self.play_btn.clicked.connect(self.toggle_play)
        control_layout.addWidget(self.play_btn)

        self.time_label = QLabel("00:00 / 00:00")
        self.time_label.setStyleSheet("color: white; font-size: 12px; font-family: monospace; background: transparent;")
        control_layout.addWidget(self.time_label)

        self.slider = ClickableSlider(Qt.Horizontal)
        self.slider.setCursor(Qt.PointingHandCursor)
        self.slider.setStyleSheet("""
            QSlider { background: transparent; }
            QSlider::groove:horizontal { border-radius: 2px; height: 3px; background: rgba(255, 255, 255, 0.3); }
            QSlider::sub-page:horizontal { background: white; border-radius: 2px; }
            QSlider::handle:horizontal { background: white; width: 10px; height: 10px; margin: -3px 0; border-radius: 5px; }
        """)
        self.slider.sliderMoved.connect(self.set_position)
        control_layout.addWidget(self.slider)

        self.mute_btn = QPushButton("🔊")
        self.mute_btn.setFixedSize(28, 28)
        self.mute_btn.setStyleSheet("color: white; font-size: 16px; border: none; background: transparent;")
        self.mute_btn.clicked.connect(self.toggle_mute)
        control_layout.addWidget(self.mute_btn)

        self.fs_btn = QPushButton("⛶")
        self.fs_btn.setFixedSize(28, 28)
        self.fs_btn.setStyleSheet("color: white; font-size: 18px; border: none; background: transparent;")
        self.fs_btn.clicked.connect(self.toggle_fullscreen)
        control_layout.addWidget(self.fs_btn)

        self.top_bar.installEventFilter(self)
        self.control_bar.installEventFilter(self)

        # === 信号绑定 ===
        self.player.positionChanged.connect(self._on_position_changed)
        self.player.durationChanged.connect(self._on_duration_changed)
        self.player.playbackStateChanged.connect(self._on_state_changed)
        self.player.mediaStatusChanged.connect(self._on_media_status_changed)

        # === UI 自动隐藏定时器 ===
        self.ui_timer = QTimer(self)
        self.ui_timer.setInterval(2500)
        self.ui_timer.timeout.connect(self.hide_ui)

    # --- 事件过滤器（拦截视图的鼠标事件） ---
    def eventFilter(self, obj, event):
        if obj in (self.view, self.view.viewport(), self.top_bar, self.control_bar):
            etype = event.type()
            if etype == QEvent.MouseMove:
                self.show_ui()
            elif etype == QEvent.MouseButtonDblClick and event.button() == Qt.LeftButton:
                if obj in (self.view, self.view.viewport()):
                    self.toggle_fullscreen()
                    return True
        return super().eventFilter(obj, event)

    # --- 窗口拖拽 ---
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and not self._is_fullscreen:
            self._is_tracking = True
            self._start_pos = event.globalPosition().toPoint() - self.pos()
            event.accept()

    def mouseMoveEvent(self, event):
        self.show_ui()
        if self._is_tracking and not self._is_fullscreen:
            self.move(event.globalPosition().toPoint() - self._start_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._is_tracking = False
            event.accept()

    # --- 尺寸同步（绝对定位 + 置顶） ---
    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._sync_geometry()

    def _sync_geometry(self):
        # 图形视图铺满
        self.view.setGeometry(0, 0, self.width(), self.height())
        self.scene.setSceneRect(0, 0, self.width(), self.height())
        self.video_item.setSize(QSizeF(self.width(), self.height()))

        # 绝对定位悬浮 UI
        self.top_bar.setGeometry(0, 0, self.width(), 45)
        self.control_bar.setGeometry(0, self.height() - 50, self.width(), 50)
        # 【关键】强制置顶，防止被显卡覆盖
        self.top_bar.raise_()
        self.control_bar.raise_()

    # --- UI 显示/隐藏 ---
    def show_ui(self):
        self.top_bar.show()
        self.top_bar.raise_()
        self.control_bar.show()
        self.control_bar.raise_()
        self.ui_timer.start()

    def hide_ui(self):
        if self.player.playbackState() == QMediaPlayer.PlayingState:
            self.top_bar.hide()
            self.control_bar.hide()

    # --- 核心对外接口 ---
    def play_media(self, file_path: str):
        self.player.setSource(QUrl.fromLocalFile(file_path))
        self.player.play()
        if self._is_fullscreen:
            self.toggle_fullscreen()
        self.show()
        self.show_ui()

    def stop_and_hide(self):
        self.player.stop()
        if self._is_fullscreen: self.toggle_fullscreen()
        self.hide()

    # --- 快捷键 ---
    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Space:
            self.toggle_play()
        elif event.key() == Qt.Key_Escape and self._is_fullscreen:
            self.toggle_fullscreen()
        super().keyPressEvent(event)

    # --- 鼠标离开窗口事件 ---
    def leaveEvent(self, event):
        self.top_bar.hide()
        self.control_bar.hide()
        super().leaveEvent(event)

    # --- 控制回调 ---
    def toggle_play(self):
        if self.player.playbackState() == QMediaPlayer.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def toggle_mute(self):
        is_muted = not self.audio_output.isMuted()
        self.audio_output.setMuted(is_muted)
        self.mute_btn.setText("🔇" if is_muted else "🔊")

    def toggle_fullscreen(self):
        self._is_fullscreen = not self._is_fullscreen
        if self._is_fullscreen:
            self.showFullScreen()
            self.control_bar.setStyleSheet("""
                background-color: rgba(20, 20, 22, 0.85);
                border-radius: 0px;
            """)
            self.top_bar.setStyleSheet("""
                background-color: rgba(20, 20, 22, 0.85);
                border-radius: 0px;
            """)
        else:
            self.showNormal()
            self.control_bar.setStyleSheet("""
                background-color: rgba(20, 20, 22, 0.85);
                border-bottom-left-radius: 8px; border-bottom-right-radius: 8px;
            """)
            self.top_bar.setStyleSheet("""
                background-color: rgba(20, 20, 22, 0.85);
                border-top-left-radius: 8px; border-top-right-radius: 8px;
            """)
        QTimer.singleShot(10, self._sync_geometry)

    def set_position(self, pos):
        self.player.setPosition(pos)

    def _on_position_changed(self, pos):
        if not self.slider.isSliderDown():
            self.slider.setValue(pos)
        self._update_time_label(pos, self.player.duration())

    def _on_duration_changed(self, dur):
        self.slider.setRange(0, dur)
        self._update_time_label(self.player.position(), dur)

    def _on_state_changed(self, state):
        self.play_btn.setText("▶" if state != QMediaPlayer.PlayingState else "⏸")

    def _on_media_status_changed(self, status):
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            self.player.setPosition(0)
            self.player.play()

    def _update_time_label(self, pos, dur):
        s = round(pos / 1000)
        d = round(dur / 1000)
        self.time_label.setText(f"{s // 60:02d}:{s % 60:02d} / {d // 60:02d}:{d % 60:02d}")
