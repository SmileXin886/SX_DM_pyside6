# -*- coding: utf-8 -*-
"""
ImageViewer - 图片查看器组件
=====================================
提供全屏遮罩 + 居中显示的图片预览功能，支持：
- 点击图片外空白处自动关闭
- ESC 键退出
- 等比缩放自适应屏幕
"""

import logging

from PySide6.QtWidgets import QWidget
from PySide6.QtGui import QPixmap, QPainter, QColor
from PySide6.QtCore import Qt, QRect

logger = logging.getLogger("SX_DM.image_viewer")


class ImageViewer(QWidget):
    """
    全屏图片查看器组件

    特性：
    - 全屏显示，带半透明黑色遮罩（Lightbox 效果）
    - 图片等比缩放自适应屏幕（留 60px 边缘）
    - 点击空白处关闭
    - ESC 键退出
    """

    def __init__(self):
        super().__init__()
        # 无边框，永远置顶，不在任务栏显示图标
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        # 允许背景透明
        self.setAttribute(Qt.WA_TranslucentBackground)

        self._pixmap = None
        self._draw_rect = QRect()

        logger.info("[ImageViewer] 组件已初始化")

    def show_image(self, file_path: str):
        """
        显示指定路径的图片（全屏）

        Args:
            file_path: 图片文件的绝对路径
        """
        self._pixmap = QPixmap(file_path)
        if self._pixmap.isNull():
            logger.warning(f"[ImageViewer] 无法加载图片: {file_path}")
            return

        logger.info(f"[ImageViewer] 显示图片: {file_path}")
        # 全屏显示遮罩
        self.showFullScreen()
        self.update()

    def paintEvent(self, event):
        if not self._pixmap or self._pixmap.isNull():
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)

        # 1. 绘制半透明黑色背景遮罩 (类似网页 Lightbox)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 215))

        # 2. 计算图片缩放尺寸 (留出边缘 margin)
        window_rect = self.rect()
        margin = 60
        target_size = window_rect.adjusted(margin, margin, -margin, -margin).size()

        # 如果图片比屏幕小，则保持原尺寸；如果比屏幕大，则等比缩放
        pic_size = self._pixmap.size()
        if pic_size.width() > target_size.width() or pic_size.height() > target_size.height():
            pic_size.scale(target_size, Qt.KeepAspectRatio)

        scaled_pixmap = self._pixmap.scaled(
            pic_size, Qt.KeepAspectRatio, Qt.SmoothTransformation
        )

        # 3. 居中绘制图片
        x = (window_rect.width() - scaled_pixmap.width()) // 2
        y = (window_rect.height() - scaled_pixmap.height()) // 2
        self._draw_rect = QRect(x, y, scaled_pixmap.width(), scaled_pixmap.height())

        painter.drawPixmap(self._draw_rect, scaled_pixmap)

    def mousePressEvent(self, event):
        # 点击左键时，如果点击位置不在图片区域内（即点击了空白处），则关闭
        if event.button() == Qt.LeftButton:
            if not self._draw_rect.contains(event.pos()):
                logger.info("[ImageViewer] 点击空白处，关闭查看器")
                self.hide()
                self._pixmap = None  # 释放内存

    def keyPressEvent(self, event):
        # 支持 ESC 键退出
        if event.key() == Qt.Key_Escape:
            logger.info("[ImageViewer] ESC 键退出")
            self.hide()
            self._pixmap = None
        super().keyPressEvent(event)
