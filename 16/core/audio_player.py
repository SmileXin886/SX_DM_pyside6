# -*- coding: utf-8 -*-
"""
AudioPlayer - 音频播放器组件
=====================================
提供轻量级悬浮音频播放条，支持：
- 无边框、带圆角、可拖拽的独立悬浮条
- 播放/暂停、进度拖拽、静音控制
- 永远置顶，不遮挡其他窗口操作
"""

import logging

from PySide6.QtWidgets import QWidget, QHBoxLayout, QPushButton, QSlider, QLabel, QFrame
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtCore import Qt, QUrl, QPoint

logger = logging.getLogger("SX_DM.audio_player")


class ClickableSlider(QSlider):
    """自定义可点击进度条 - 点击任意位置跳转到对应进度"""

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            if self.width() > 0:
                val = self.minimum() + (self.maximum() - self.minimum()) * event.position().x() / self.width()
                self.setValue(int(val))
                self.sliderMoved.emit(int(val))
        super().mousePressEvent(event)


class AudioPlayer(QWidget):
    """
    轻量级音频播放器组件

    特性：
    - 无边框悬浮条，视觉优雅
    - 可自由拖拽到屏幕任意位置
    - 永远置顶，不影响其他操作
    - 专为音频设计，无需复杂视频渲染
    """

    def __init__(self):
        super().__init__()
        # 无边框，永远置顶，不在任务栏显示图标
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.resize(450, 60)

        self._is_tracking = False
        self._start_pos = QPoint()

        # 媒体后端
        self.player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.player.setAudioOutput(self.audio_output)

        # 主界面容器（带圆角和半透明背景）
        self.container = QFrame(self)
        self.container.setGeometry(0, 0, 450, 60)
        self.container.setStyleSheet("""
            QFrame {
                background-color: rgba(30, 30, 35, 0.95);
                border-radius: 12px;
                border: 1px solid rgba(255, 255, 255, 0.1);
            }
        """)

        layout = QHBoxLayout(self.container)
        layout.setContentsMargins(15, 0, 15, 0)
        layout.setSpacing(12)

        # 播放/暂停按钮
        self.play_btn = QPushButton("⏸")
        self.play_btn.setFixedSize(32, 32)
        self.play_btn.setStyleSheet("""
            QPushButton { color: white; font-size: 18px; border: none; background: transparent; }
            QPushButton:hover { color: #4CAF50; }
        """)
        self.play_btn.clicked.connect(self.toggle_play)
        layout.addWidget(self.play_btn)

        # 时间标签
        self.time_label = QLabel("00:00 / 00:00")
        self.time_label.setStyleSheet("color: white; font-size: 12px; font-family: monospace; background: transparent; border: none;")
        layout.addWidget(self.time_label)

        # 进度条
        self.slider = ClickableSlider(Qt.Horizontal)
        self.slider.setCursor(Qt.PointingHandCursor)
        self.slider.setStyleSheet("""
            QSlider { background: transparent; border: none; }
            QSlider::groove:horizontal { border-radius: 2px; height: 4px; background: rgba(255, 255, 255, 0.2); }
            QSlider::sub-page:horizontal { background: #4CAF50; border-radius: 2px; }
            QSlider::handle:horizontal { background: white; width: 12px; height: 12px; margin: -4px 0; border-radius: 6px; }
        """)
        self.slider.sliderMoved.connect(self.set_position)
        layout.addWidget(self.slider)

        # 静音按钮
        self.mute_btn = QPushButton("🔊")
        self.mute_btn.setFixedSize(32, 32)
        self.mute_btn.setStyleSheet("""
            QPushButton { color: white; font-size: 16px; border: none; background: transparent; }
            QPushButton:hover { color: #4CAF50; }
        """)
        self.mute_btn.clicked.connect(self.toggle_mute)
        layout.addWidget(self.mute_btn)

        # 关闭按钮
        self.close_btn = QPushButton("✕")
        self.close_btn.setFixedSize(28, 28)
        self.close_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(255, 255, 255, 0.1);
                color: white; border-radius: 14px; font-weight: bold; border: none;
            }
            QPushButton:hover { background-color: #ff4444; }
        """)
        self.close_btn.clicked.connect(self.stop_and_hide)
        layout.addWidget(self.close_btn)

        # 信号绑定
        self.player.positionChanged.connect(self._on_position_changed)
        self.player.durationChanged.connect(self._on_duration_changed)
        self.player.playbackStateChanged.connect(self._on_state_changed)
        self.player.mediaStatusChanged.connect(self._on_media_status_changed)

        logger.info("[AudioPlayer] 组件已初始化")

    def play_audio(self, file_path: str):
        """
        播放指定路径的音频文件

        Args:
            file_path: 音频文件的绝对路径
        """
        logger.info(f"[AudioPlayer] 播放音频: {file_path}")
        self.player.setSource(QUrl.fromLocalFile(file_path))
        self.player.play()
        self.show()

    def stop_and_hide(self):
        """停止播放并隐藏播放器"""
        logger.info("[AudioPlayer] 停止播放")
        self.player.stop()
        self.hide()

    def toggle_play(self):
        """切换播放/暂停状态"""
        if self.player.playbackState() == QMediaPlayer.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def toggle_mute(self):
        """切换静音状态"""
        is_muted = not self.audio_output.isMuted()
        self.audio_output.setMuted(is_muted)
        self.mute_btn.setText("🔇" if is_muted else "🔊")

    def set_position(self, pos: int):
        """设置播放进度"""
        self.player.setPosition(pos)

    def _on_position_changed(self, pos: int):
        """播放进度更新"""
        if not self.slider.isSliderDown():
            self.slider.setValue(pos)
        self._update_time_label(pos, self.player.duration())

    def _on_duration_changed(self, dur: int):
        """媒体时长加载完成"""
        self.slider.setRange(0, dur)
        self._update_time_label(self.player.position(), dur)

    def _on_state_changed(self, state):
        """播放状态变化"""
        self.play_btn.setText("▶" if state != QMediaPlayer.PlayingState else "⏸")

    def _on_media_status_changed(self, status):
        """媒体状态变化（处理播放结束）"""
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            self.player.setPosition(0)
            self.player.play()

    def _update_time_label(self, pos: int, dur: int):
        """更新时间标签"""
        s = round(pos / 1000)
        d = round(dur / 1000)
        self.time_label.setText(f"{s // 60:02d}:{s % 60:02d} / {d // 60:02d}:{d % 60:02d}")

    # --- 窗口拖拽逻辑（点击空白处可移动音频条） ---
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._is_tracking = True
            self._start_pos = event.globalPosition().toPoint() - self.pos()
            event.accept()

    def mouseMoveEvent(self, event):
        if self._is_tracking:
            self.move(event.globalPosition().toPoint() - self._start_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._is_tracking = False
            event.accept()
