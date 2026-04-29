# -*- coding: utf-8 -*-
"""
Dreamina Toolkit - 全网页化桌面应用
基于 PySide6 + QWebEngineView 构建

【Qt WebChannel 官方方式】
1. 创建 QWebChannel 并 registerObject 注册 Bridge 对象
2. page.setWebChannel 绑定通道
3. 网页中使用 qrc:///qtwebchannel/qwebchannel.js
4. JavaScript 中用 .connect() 连接 Python Signal
"""

import ctypes
import json
import logging
import os
import sys
import time

from PySide6 import QtWidgets, QtCore
from PySide6.QtCore import Qt, QUrl, QObject, Slot
from PySide6.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEngineProfile, QWebEnginePage
from PySide6.QtWebChannel import QWebChannel

from bridge import WebChannelBridge
from server import app, qt_integrator, manager, server_manager

logger = logging.getLogger("SX_DM.main")


# ============ 日志捕获 ============

class LogEmitter(QObject):
    signal = QtCore.Signal(str, str)


emitter = LogEmitter()


class QTextEditHandler(logging.Handler):
    def __init__(self, callback):
        super().__init__()
        self.callback = callback
        self.setFormatter(logging.Formatter("%(asctime)s  %(message)s", datefmt="%H:%M:%S"))

    def emit(self, record):
        msg = self.format(record)
        level = {logging.DEBUG: "debug", logging.INFO: "info", logging.WARNING: "warning",
                 logging.ERROR: "error"}.get(record.levelno, "info")
        self.callback(level, msg)


# ============ 线程池 ============

class ThreadPoolManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            from concurrent.futures import ThreadPoolExecutor
            cls._instance = super().__new__(cls)
            cls._instance._executor = ThreadPoolExecutor(max_workers=4)
        return cls._instance

    def submit(self, func, *args, **kwargs):
        return self._executor.submit(func, *args, **kwargs)


thread_pool = ThreadPoolManager()


# ============ Windows 暗色标题栏 ============

def set_dark_title_bar():
    try:
        DWMWA_USE_IMMERSIVE_DARK_MODE = 20
        hwnd = ctypes.windll.user32.GetForegroundWindow()
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE, ctypes.byref(ctypes.c_int(1)), 4)
        logger.info("[Windows] 标题栏已设为暗色模式")
    except Exception as e:
        logger.warning(f"[Windows] 无法设置暗色标题栏: {e}")


# ============ ModernWebView ============

class ModernWebView(QWebEngineView):
    """
    支持拖拽的 WebEngineView

    【Qt WebChannel 官方流程】
    1. 创建 QWebChannel
    2. registerObject 注册 Bridge 对象
    3. page.setWebChannel 绑定通道
    4. 加载页面
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._bridge = None
        self._channel = None
        self._drop_enabled = False  # 拖拽是否在上载区生效
        self._last_check_time = 0
        self._setup_page()

    def set_drop_enabled(self, enabled: bool):
        """由前端控制是否启用拖拽"""
        self._drop_enabled = enabled

    def _setup_page(self):
        profile = QWebEngineProfile.defaultProfile()
        page = QWebEnginePage(profile, self)
        page.setBackgroundColor(Qt.GlobalColor.transparent)
        self.setPage(page)

        # 创建 Bridge 对象（WebChannelBridge 包含 signal_result 等信号）
        self._bridge = WebChannelBridge()

        # 【关键】创建 WebChannel 并注册对象
        self._channel = QWebChannel(self)
        self._channel.registerObject("pyBridge", self._bridge)

        # 【关键】必须先注册，再设置 WebChannel
        self.page().setWebChannel(self._channel)

        logger.info("[WebView] WebChannel 已初始化")
        logger.info("[WebView] 已注册 pyBridge 对象")

        # 页面加载完成后注入初始化脚本
        self.page().loadFinished.connect(self._on_page_loaded)

    def _on_page_loaded(self, ok: bool):
        """页面加载完成后注入脚本"""
        if ok:
            logger.info("[WebView] 页面加载完成")

            # 【关键】按照 Qt WebChannel 官方方式，JavaScript 用 .connect() 连接信号
            script = """
            (function() {
                console.log('[Main] 初始化 Qt WebChannel');

                // 【关键】使用 qt.webChannelTransport 连接
                if (typeof qt !== 'undefined' && qt.webChannelTransport) {
                    new QWebChannel(qt.webChannelTransport, function(channel) {
                        console.log('[QWebChannel] 连接成功');
                        if (channel.objects.pyBridge) {
                            window.pyBridge = channel.objects.pyBridge;

                            // ✅ 【关键】必须用 .connect() 显式连接 Python Signal
                            window.pyBridge.signal_result.connect(function(taskId, result) {
                                console.log('[Qt 响应] 任务完成:', taskId, result);
                            });

                            window.pyBridge.signal_progress.connect(function(taskId, percent, msg) {
                                console.log('[Qt 进度]:', percent, msg);
                            });

                            window.pyBridge.signal_error.connect(function(taskId, error) {
                                console.error('[Qt 错误]:', taskId, error);
                            });

                            // ✅ 新增：监听文件更新信号
                            window.pyBridge.signal_files_updated.connect(function(filesJson) {
                                console.log('[Qt 文件更新]', filesJson);
                                try {
                                    var filesList = JSON.parse(filesJson);
                                    if (window.renderPreviewsFromPython) {
                                        window.renderPreviewsFromPython(filesList);
                                    }
                                } catch (e) {
                                    console.error('[Qt 文件更新] 解析失败:', e);
                                }
                            });

                            console.log('[Bridge] pyBridge 已就绪并绑定信号');
                            document.dispatchEvent(new CustomEvent('bridge-ready'));
                        }
                    });
                }
            })();
            """
            self.page().runJavaScript(script)
        else:
            logger.error("[WebView] 页面加载失败")

    def load_html(self, html_path: str):
        """加载 HTML"""
        html_path = os.path.abspath(html_path)
        if os.path.exists(html_path):
            self.setUrl(QUrl.fromLocalFile(html_path))
            logger.info(f"[WebView] 加载: {html_path}")
        else:
            logger.error(f"[WebView] HTML 不存在: {html_path}")

    def send_to_web(self, action: str, data: object):
        """发送消息到网页（通过 runJavaScript）"""
        js = f"if (window.onQtMessage) window.onQtMessage({json.dumps(action)}, {json.dumps(data, ensure_ascii=False)});"
        self.page().runJavaScript(js)

    def dragEnterEvent(self, event):
        """拦截拖拽进入事件 - 通知前端开始拖拽"""
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            logger.info("[WebView] 检测到文件拖拽")
            # 通知前端开始拖拽
            self.page().runJavaScript("""
                window.__isDragging = true;
                if (window.updateDragState) {
                    window.updateDragState(true);
                }
            """)

    def dragMoveEvent(self, event):
        """拖拽移动时检测位置并更新UI，同时在编辑区显示自定义光标"""
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            # 获取鼠标在页面中的位置
            pos = event.position()
            # 检测是否在 reference-dropzone 或 dreaminaPrompt 上方，并更新状态
            js = f"""
                (function() {{
                    var dropzone = document.getElementById('reference-dropzone');
                    var editor = document.getElementById('dreaminaPrompt');
                    if (!dropzone && !editor) {{
                        console.log('[DRAG] 拖拽区域都不存在');
                        return;
                    }}

                    // 获取或创建自定义光标元素
                    var cursor = document.getElementById('drag-cursor');
                    if (!cursor) {{
                        cursor = document.createElement('div');
                        cursor.id = 'drag-cursor';
                        cursor.style.cssText = 'position:fixed;width:2px;height:1.2em;background:rgb(0,202,224);pointer-events:none;z-index:9999;transition:none;margin:0;padding:0;';
                        document.body.appendChild(cursor);
                    }}

                    // 检测 reference-dropzone
                    if (dropzone) {{
                        var rect = dropzone.getBoundingClientRect();
                        var isOver = {pos.x()} >= rect.left && {pos.x()} <= rect.right &&
                                     {pos.y()} >= rect.top && {pos.y()} <= rect.bottom;

                        dropzone.classList.add('drag-active');
                        if (isOver) {{
                            dropzone.classList.add('drag-over');
                            cursor.style.display = 'none'; // 在 dropzone 区域隐藏光标
                            console.log('[DRAG] 悬停在 reference-dropzone 上');
                        }} else {{
                            dropzone.classList.remove('drag-over');
                        }}
                    }}

                    // 检测 dreaminaPrompt 编辑区 - 使用 caretRangeFromPoint 精准定位光标
                    if (editor) {{
                        var rect = editor.getBoundingClientRect();
                        var isOverEditor = {pos.x()} >= rect.left && {pos.x()} <= rect.right &&
                                           {pos.y()} >= rect.top && {pos.y()} <= rect.bottom;

                        if (isOverEditor) {{
                            editor.classList.add('drag-over');
                            console.log('[DRAG] 悬停在 dreaminaPrompt 编辑区');

                            // 1. 新增：拾取当前鼠标正下方的元素，判断是否悬停在素材标签上
                            var targetNode = document.elementFromPoint({pos.x()}, {pos.y()});
                            var isOverTag = targetNode && (targetNode.getAttribute('contenteditable') === 'false' || targetNode.closest('[contenteditable="false"]'));

                            if (isOverTag) {{
                                cursor.style.display = 'none';
                                return;
                            }}

                            // 【核心】使用 caretRangeFromPoint 精准定位光标
                            var selection = window.getSelection();
                            var range;

                            if (document.caretRangeFromPoint) {{
                                range = document.caretRangeFromPoint({pos.x()}, {pos.y()});
                            }} else if (document.caretPositionFromPoint) {{
                                var cp = document.caretPositionFromPoint({pos.x()}, {pos.y()});
                                if (cp) {{
                                    range = document.createRange();
                                    range.setStart(cp.offsetNode, cp.offset);
                                    range.collapse(true);
                                }}
                            }}

                            if (range) {{
                                // 检查光标是否在编辑区内
                                var inEditor = editor.contains(range.startContainer) || editor === range.startContainer;

                                if (inEditor) {{
                                    // 设置选区（虽然不显示，但保持数据正确）
                                    selection.removeAllRanges();
                                    selection.addRange(range);

                                    // 获取光标的视觉位置并显示自定义光标
                                    try {{
                                        var cursorRect = range.getBoundingClientRect();

                                        // 2. 新增：拦截无效的 Rect (左上角 Bug 的元凶)
                                        var isInvalidRect = (cursorRect.left === 0 && cursorRect.top === 0 && cursorRect.height === 0);

                                        if (cursorRect && cursorRect.width !== undefined && !isInvalidRect) {{
                                            cursor.style.left = cursorRect.left + 'px';
                                            cursor.style.top = cursorRect.top + 'px';
                                            cursor.style.height = (cursorRect.height > 0 ? cursorRect.height : 18) + 'px';
                                            cursor.style.display = 'block';
                                            console.log('[DRAG] 光标位置已更新 rect:', cursorRect);
                                        }} else {{
                                            // 如果获取到的是无效位置，直接隐藏，避免乱飞
                                            cursor.style.display = 'none';
                                        }}
                                    }} catch (e) {{
                                        cursor.style.display = 'none';
                                    }}
                                }} else {{
                                    // 光标不在编辑区内
                                    cursor.style.display = 'none';
                                }}
                            }} else {{
                                cursor.style.display = 'none';
                            }}
                        }} else {{
                            editor.classList.remove('drag-over');
                            cursor.style.display = 'none';
                        }}
                    }} else {{
                        cursor.style.display = 'none';
                    }}
                }})();
            """
            self.page().runJavaScript(js)

    def dragLeaveEvent(self, event):
        """拖拽离开窗口时重置状态"""
        event.accept()
        self.page().runJavaScript("""
            window.__isDragging = false;
            var dropzone = document.getElementById('reference-dropzone');
            var editor = document.getElementById('dreaminaPrompt');
            var cursor = document.getElementById('drag-cursor');
            if (dropzone) {
                dropzone.classList.remove('drag-over');
                dropzone.classList.remove('drag-active');
            }
            if (editor) {
                editor.classList.remove('drag-over');
            }
            if (cursor) {
                cursor.remove();
            }
        """)

    def _update_dropzone_state(self, state):
        """更新拖拽区域状态"""
        if state == 'over':
            self.page().runJavaScript("""
                var dropzone = document.getElementById('reference-dropzone');
                if (dropzone) {
                    dropzone.classList.add('drag-over');
                    dropzone.classList.add('drag-active');
                }
            """)
        else:
            self.page().runJavaScript("""
                var dropzone = document.getElementById('reference-dropzone');
                if (dropzone) dropzone.classList.remove('drag-over');
            """)

    def dropEvent(self, event):
        """
        拦截拖拽放下事件，允许在 reference-dropzone 或 dreaminaPrompt 区域内处理文件
        - reference-dropzone: 文件添加到上传区
        - dreaminaPrompt: 文件在编辑区光标位置插入标签
        """
        # 先提取文件列表
        files = []
        for url in event.mimeData().urls():
            file_path = url.toLocalFile()
            if file_path and os.path.isfile(file_path):
                files.append(file_path)

        if not files:
            event.acceptProposedAction()
            return

        # 获取释放时的鼠标页面坐标
        drop_pos = event.position().toPoint()

        # 通过 JavaScript 检测拖拽区域，并获取/设置 drop 时的光标位置
        js = f"""
            (function() {{
                var elem = document.elementFromPoint({drop_pos.x()}, {drop_pos.y()});
                var dropzone = document.getElementById('reference-dropzone');
                var editor = document.getElementById('dreaminaPrompt');
                var cursor = document.getElementById('drag-cursor');

                // 检查是否在 reference-dropzone 区域内
                var inDropzone = dropzone && (dropzone.contains(elem) || elem === dropzone);
                // 检查是否在 dreaminaPrompt 编辑区域内
                var inEditor = editor && (editor.contains(elem) || elem === editor);

                // 清除所有拖拽状态和自定义光标
                window.__isDragging = false;
                if (dropzone) {{
                    dropzone.classList.remove('drag-over');
                    dropzone.classList.remove('drag-active');
                }}
                if (editor) {{
                    editor.classList.remove('drag-over');
                }}
                if (cursor) {{
                    cursor.remove();
                }}

                // 返回区域类型
                if (inDropzone) return 'dropzone';
                if (inEditor) return 'editor';
                return 'none';
            }})();
        """

        # 使用 QTimer.singleShot 延迟检查
        def check_and_process():
            result = []
            def capture(r):
                result.append(r)

            self.page().runJavaScript(js, capture)

            from PySide6.QtCore import QTimer
            def check_result():
                if result:
                    drop_area = result[0]
                    if drop_area == 'dropzone':
                        logger.info(f"[WebView] 拖拽到 Reference 上传区: {files}")
                        self._bridge._process_file_list(files)
                    elif drop_area == 'editor':
                        logger.info(f"[WebView] 拖拽到编辑区: {files}")
                        # 保存 drop 位置，用于前端精准定位光标
                        self._bridge._last_drop_pos = drop_pos
                        self._bridge._process_file_list_for_editor(files, drop_pos)
                    else:
                        logger.info(f"[WebView] 拖拽不在允许区域: {files}")
                else:
                    # 超时后默认处理
                    logger.info(f"[WebView] 拖拽超时检测，默认处理: {files}")
                    self._bridge._process_file_list(files)

            QTimer.singleShot(100, check_result)

        # 延迟执行检查
        from PySide6.QtCore import QTimer
        QTimer.singleShot(0, check_and_process)

        event.acceptProposedAction()


# ============ 主窗口 ============

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.server_running = False
        self.host = "127.0.0.1"
        self.port = 8765
        self.web_view = None
        # 文件统计
        self._file_counts = {'image': 0, 'video': 0, 'audio': 0}

        self.setWindowTitle("Dreamina Toolkit")
        self.setMinimumSize(900, 650)
        self.resize(1100, 750)
        self.setStyleSheet("background: #0f0f0f;")

        set_dark_title_bar()
        self._setup_ui()

        emitter.signal.connect(self._on_log_signal)

    def get_file_counts(self) -> dict:
        """获取当前文件统计"""
        return self._file_counts.copy()

    def set_file_counts(self, files_list: list):
        """根据文件列表更新统计"""
        self._file_counts = {'image': 0, 'video': 0, 'audio': 0}
        for f in files_list:
            file_type = f.get('type', 'unknown')
            if file_type in self._file_counts:
                self._file_counts[file_type] += 1

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.web_view = ModernWebView(self)
        self.web_view.setStyleSheet("QWebEngineView { background: #0f0f0f; border: none; }")
        self.web_view.page().setBackgroundColor(Qt.GlobalColor.transparent)

        web_ui_path = os.path.join(os.path.dirname(__file__), "web_ui", "index.html")
        self.web_view.load_html(web_ui_path)

        layout.addWidget(self.web_view)

    def _on_log_signal(self, level: str, msg: str):
        if self.web_view:
            self.web_view.send_to_web("log", {"type": level, "message": msg})


# ============ 入口 ============

main_window = None


def main():
    global main_window

    os.environ.setdefault("QT_OPENGL", "software")

    app_instance = QApplication(sys.argv)
    app_instance.setApplicationName("Dreamina Toolkit")
    app_instance.setStyleSheet("""
        QApplication { background: #0f0f0f; }
        QScrollBar:vertical { background: #1a1a1a; width: 8px; }
        QScrollBar::handle:vertical { background: #3a3a3a; border-radius: 4px; }
    """)

    qt_integrator.set_qapp(app_instance)

    main_window = MainWindow()
    main_window.show()

    handler = QTextEditHandler(lambda level, msg: emitter.signal.emit(level, msg))
    logging.getLogger("SX_DM").addHandler(handler)
    logging.getLogger("SX_DM.main").setLevel(logging.INFO)

    logger.info("Dreamina Toolkit 已启动")
    logger.info("[通信宪法] 使用官方 QWebChannel 方式")

    sys.exit(app_instance.exec())


if __name__ == "__main__":
    main()
