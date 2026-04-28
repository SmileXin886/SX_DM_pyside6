# -*- coding: utf-8 -*-
"""
Bridge 通信模块 - 固定通信宪法
=====================================
本模块是前后端通信的唯一标准实现！

【新增功能】
- open_file_dialog: 唤起原生文件选择对话框
- process_files: 处理文件列表（图片、视频、音频）
- signal_files_updated: 推送处理好的文件列表到前端
- request_native_preview: 打开原生播放器预览视频
"""

import base64
import json
import logging
import os
from typing import List, Dict, Any

from PySide6.QtCore import QObject, Signal, Slot
from PySide6.QtWidgets import QFileDialog

from core.native_player import NativePlayer
from core.image_viewer import ImageViewer
from core.audio_player import AudioPlayer
from core.media_processor import MediaProcessor

logger = logging.getLogger("SX_DM.bridge")

# 文件类型限制常量
MAX_IMAGES = 12        # 图片动态调整，以总数12为上限
MAX_VIDEOS = 3         # 视频最多3个
MAX_AUDIOS = 3         # 音频最多3个
MAX_TOTAL = 12         # 总数不超过12个
MAX_VIDEO_DURATION = 15  # 视频最大时长（秒）
MAX_AUDIO_DURATION = 15  # 音频最大时长（秒）

# 支持的文件扩展名
IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'}
VIDEO_EXTS = {'.mp4', '.avi', '.mov', '.mkv', '.webm', '.flv'}
AUDIO_EXTS = {'.mp3', '.wav', '.aac', '.flac', '.ogg', '.m4a'}


def get_file_type(file_path: str) -> str:
    """根据扩展名判断文件类型"""
    ext = os.path.splitext(file_path)[1].lower()
    if ext in IMAGE_EXTS:
        return 'image'
    elif ext in VIDEO_EXTS:
        return 'video'
    elif ext in AUDIO_EXTS:
        return 'audio'
    return 'unknown'


def format_duration(seconds: float) -> str:
    """将秒数格式化为 mm:ss"""
    if seconds <= 0:
        return "00:00"
    total_seconds = int(seconds)
    minutes = total_seconds // 60
    secs = total_seconds % 60
    return f"{minutes:02d}:{secs:02d}"


# ============ WebChannelBridge - 固定通信网关 ============

class WebChannelBridge(QObject):
    """
    WebChannel 桥接器 - 唯一通信网关
    
    前端通过 window.pyBridge.receiveMessage(action, params) 调用本类的 receiveMessage Slot
    """

    # ===== 固定信号定义 =====
    signal_result = Signal(str, str)      # (task_id, result_json)
    signal_progress = Signal(str, int, str)  # (task_id, percent, message)
    signal_error = Signal(str, str)       # (task_id, error_message)
    signal_message = Signal(str, str)     # (action, data_json) - 通用消息推送
    
    # ===== 新增：文件更新信号 =====
    signal_files_updated = Signal(str)    # (files_json) - 推送处理好的文件列表
    # ===== 新增：文件删除信号 =====
    signal_file_removed = Signal(str)      # (deleted_file_json) - 推送被删除的文件信息
    # ===== 新增：编辑区拖拽信号 =====
    signal_editor_dropped = Signal(str)   # (data_json) - 包含 files 和 drop_pos，前端用 caretRangeFromPoint 精准定位光标

    def __init__(self):
        super().__init__()
        # 【新增】维护完整文件列表，用于追加模式
        self._all_files: List[Dict[str, Any]] = []
        # 【新增】保存编辑区拖拽时的 drop 位置
        self._last_drop_pos = None
        
        # 【新增】原生播放器实例（视频）
        self._native_player = NativePlayer()
        
        # 【新增】图片查看器实例
        self._image_viewer = ImageViewer()
        
        # 【新增】音频播放器实例
        self._audio_player = AudioPlayer()

    @Slot(bool)
    def set_drop_enabled(self, enabled: bool):
        """
        控制拖拽是否启用
        由前端通过 window.pyBridge.set_drop_enabled(true/false) 调用
        当鼠标进入/离开 reference-dropzone 时触发
        """
        from main import main_window
        if main_window and main_window.web_view:
            main_window.web_view.set_drop_enabled(enabled)
            logger.info(f"[Bridge] 设置拖拽状态: {enabled}")

    @Slot(int)
    def remove_file(self, index: int):
        """
        删除指定索引的文件
        由前端通过 window.pyBridge.remove_file(index) 调用
        """
        logger.info(f"[Bridge] 收到删除文件请求: index={index}, 当前数量={len(self._all_files)}")
        
        if 0 <= index < len(self._all_files):
            removed = self._all_files.pop(index)
            logger.info(f"[Bridge] 已删除文件: {removed.get('name', 'unknown')}")
            
            # 【新增】发送文件删除信号，携带被删除文件的信息
            self.signal_file_removed.emit(json.dumps(removed, ensure_ascii=False))
            
            # 更新 MainWindow 的文件统计
            from main import main_window
            if main_window:
                main_window.set_file_counts(self._all_files)
            
            # 重新广播完整列表
            self.signal_files_updated.emit(json.dumps(self._all_files, ensure_ascii=False))
        else:
            logger.warning(f"[Bridge] 删除失败：索引 {index} 超出范围")

    @Slot(int)
    def request_native_preview(self, index: int):
        """
        请求原生播放器预览视频/音频/图片
        根据文件类型分发到对应的播放器，并确保互斥播放
        由前端通过 window.pyBridge.request_native_preview(index) 调用
        """
        logger.info(f"[Bridge] 收到原生预览请求: index={index}")
        
        if 0 <= index < len(self._all_files):
            file_info = self._all_files[index]
            file_type = file_info.get('type')
            file_path = file_info.get('path')
            
            if file_type == 'video':
                # 播放视频前，先停止其他播放器
                self._image_viewer.hide()
                self._image_viewer._pixmap = None
                self._audio_player.stop_and_hide()
                # 播放视频
                self._native_player.play_media(file_path)
                logger.info(f"[Bridge] 打开原生播放器: {file_path}")
                
            elif file_type == 'audio':
                # 播放音频前，先停止其他播放器
                self._image_viewer.hide()
                self._image_viewer._pixmap = None
                if self._native_player.isVisible():
                    self._native_player.stop_and_hide()
                # 播放音频
                self._audio_player.play_audio(file_path)
                logger.info(f"[Bridge] 打开音频播放器: {file_path}")
                
            elif file_type == 'image':
                # 显示图片前，先停止其他播放器
                if self._native_player.isVisible():
                    self._native_player.stop_and_hide()
                self._audio_player.stop_and_hide()
                # 显示图片
                self._image_viewer.show_image(file_path)
                logger.info(f"[Bridge] 打开图片查看器: {file_path}")
                
            else:
                logger.warning(f"[Bridge] 不支持预览类型: {file_type}")
        else:
            logger.warning(f"[Bridge] 预览失败：索引 {index} 超出范围")

    @Slot(str, str, result=str)
    def receiveMessage(self, action: str, data: str):
        """
        接收前端消息 - 唯一入口
        【必须加 @Slot 装饰器，否则 JS 无法调用】
        """
        try:
            params = json.loads(data) if data else {}
        except json.JSONDecodeError:
            params = {}

        logger.info(f"[Bridge] 收到请求: {action}")

        handler = self._get_handler(action)
        if handler:
            handler(params)
        else:
            logger.warning(f"[Bridge] 未知操作: {action}")
            self.signal_error.emit(action, f"未知操作: {action}")

        return "ok"

    @Slot(str)
    def on_editor_drop(self, data_json: str):
        """
        输入框拖拽文件处理
        由前端通过 window.pyBridge.on_editor_drop(data_json) 调用
        data_json 格式: {"paths": [...], "drop_pos": {"x": int, "y": int}}
        """
        try:
            data = json.loads(data_json)
            paths = data.get('paths', [])
            drop_pos_data = data.get('drop_pos')
            
            if paths:
                logger.info(f"[Bridge] 输入框拖拽收到 {len(paths)} 个文件, drop_pos={drop_pos_data}")
                
                # 将 drop_pos 转换为 QPoint（如果提供了坐标）
                drop_pos = None
                if drop_pos_data and 'x' in drop_pos_data and 'y' in drop_pos_data:
                    from PySide6.QtCore import QPoint
                    drop_pos = QPoint(drop_pos_data['x'], drop_pos_data['y'])
                
                # 使用编辑区专用的处理方法（会发送 signal_editor_dropped 信号）
                self._process_file_list_for_editor(paths, drop_pos)
        except json.JSONDecodeError:
            logger.error(f"[Bridge] 解析拖拽数据失败: {data_json}")
        except Exception as e:
            logger.error(f"[Bridge] 处理拖拽文件失败: {e}")

    def _get_handler(self, action: str):
        """获取操作处理器"""
        handlers = {
            'start_server': self._handle_start_server,
            'stop_server': self._handle_stop_server,
            'get_presets': self._handle_get_presets,
            'create_preset': self._handle_create_preset,
            'apply_preset': self._handle_apply_preset,
            'delete_preset': self._handle_delete_preset,
            'generate': self._handle_generate,
            'get_server_status': self._handle_get_server_status,
            'open_file_dialog': self._handle_open_file_dialog,
            'process_dropped_files': self._handle_process_dropped_files,
        }
        return handlers.get(action)

    # ===== 文件处理方法 =====

    @Slot(result=str)
    def open_file_dialog(self) -> str:
        """
        唤起原生文件选择对话框
        由前端通过 window.pyBridge.open_file_dialog() 调用
        """
        logger.info("[Bridge] 唤起文件选择对话框")
        
        # 获取主窗口用于显示对话框
        from main import main_window
        parent = main_window if main_window else None
        
        # 打开文件选择对话框
        file_paths, _ = QFileDialog.getOpenFileNames(
            parent,
            "选择参考文件",
            "",
            "媒体文件 (*.png *.jpg *.jpeg *.gif *.mp4 *.avi *.mov *.mkv *.webm *.mp3 *.wav *.aac *.flac *.ogg *.m4a);;所有文件 (*.*)"
        )
        
        if not file_paths:
            logger.info("[Bridge] 用户取消选择，不更新文件列表")
            return "cancelled"
        
        # 处理选中的文件
        self._process_file_list(file_paths)
        return "ok"

    def _handle_open_file_dialog(self, params: dict):
        """处理 open_file_dialog 请求（通过 receiveMessage 调用）"""
        self.open_file_dialog()

    def _handle_process_dropped_files(self, params: dict):
        """处理拖拽文件请求"""
        files = params.get('files', [])
        if files:
            self._process_file_list(files)

    def _process_file_list(self, file_paths: List[str]):
        """处理文件列表，生成缩略图和元数据（追加模式）"""

        def _do_process():
            try:
                self.signal_progress.emit("process_files", 10, "正在处理文件...")

                # 从 Bridge 自身的历史列表统计当前数量
                current_counts = {'image': 0, 'video': 0, 'audio': 0}
                for f in self._all_files:
                    file_type = f.get('type', 'unknown')
                    if file_type in current_counts:
                        current_counts[file_type] += 1

                # 记录已有文件路径，用于去重
                existing_paths = set(f['path'] for f in self._all_files)

                new_files: List[Dict[str, Any]] = []
                limit_hit_msg = None  # 记录超限提示，用于最后发送给前端

                for i, file_path in enumerate(file_paths):
                    # 跳过已存在的文件
                    if file_path in existing_paths:
                        logger.info(f"[Bridge] 文件已存在，跳过: {file_path}")
                        continue

                    # 检查总数限制
                    total = len(self._all_files) + len(new_files)
                    if total >= MAX_TOTAL:
                        logger.info(f"[Bridge] 文件总数已达上限 ({MAX_TOTAL})")
                        limit_hit_msg = f"文件总数已达上限 ({MAX_TOTAL} 个)"
                        break

                    file_type = get_file_type(file_path)
                    if file_type == 'unknown':
                        logger.warning(f"[Bridge] 跳过不支持的文件类型: {file_path}")
                        continue

                    # 检查类型限制（图片不设独立上限，动态调整）
                    current_type_count = current_counts.get(file_type, 0) + len([f for f in new_files if f['type'] == file_type])

                    if file_type == 'video' and current_type_count >= MAX_VIDEOS:
                        logger.info(f"[Bridge] 视频数量已达上限 ({MAX_VIDEOS})")
                        limit_hit_msg = f"视频最多支持 {MAX_VIDEOS} 个"
                        continue
                    elif file_type == 'audio' and current_type_count >= MAX_AUDIOS:
                        logger.info(f"[Bridge] 音频数量已达上限 ({MAX_AUDIOS})")
                        limit_hit_msg = f"音频最多支持 {MAX_AUDIOS} 个"
                        continue

                    # 构建文件信息
                    file_info: Dict[str, Any] = {
                        'type': file_type,
                        'path': file_path,
                        'name': os.path.basename(file_path),
                        'url': "file:///" + file_path.replace("\\", "/"),
                    }

                    # 视频/音频需要使用 FFmpeg 提取缩略图和时长
                    if file_type in ('video', 'audio'):
                        media_info = MediaProcessor.get_media_info(file_path)
                        file_info['thumbnail_base64'] = media_info.get('thumbnail_base64', '')
                        file_info['duration'] = media_info.get('duration', '00:00')
                        file_info['duration_seconds'] = media_info.get('duration_seconds', 0)
                        # 视频/音频总时长检查在全部处理后进行（见下方）

                    # 图片直接使用文件 URL 作为缩略图
                    elif file_type == 'image':
                        file_info['thumbnail_base64'] = file_info['url']

                    new_files.append(file_info)

                    # 更新进度
                    progress = min(90, 10 + (i + 1) * 80 // len(file_paths))
                    self.signal_progress.emit("process_files", progress, f"已处理 {i + 1}/{len(file_paths)} 个文件")

                # 追加新文件到历史列表
                self._all_files.extend(new_files)

                # 【视频总时长检查】所有视频总时长不超过 15 秒，超限时移除多余文件
                video_files = [f for f in self._all_files if f.get('type') == 'video']
                total_video_dur = sum(f.get('duration_seconds', 0) for f in video_files)
                if total_video_dur > MAX_VIDEO_DURATION:
                    logger.info(f"[Bridge] 视频总时长超限 ({total_video_dur}s > {MAX_VIDEO_DURATION}s)，开始移除多余文件")
                    while video_files and sum(f.get('duration_seconds', 0) for f in video_files) > MAX_VIDEO_DURATION:
                        removed_video = video_files.pop(0)
                        self._all_files.remove(removed_video)
                        logger.info(f"[Bridge] 已自动移除视频: {removed_video.get('name')}")
                    video_files = [f for f in self._all_files if f.get('type') == 'video']
                    final_video_dur = sum(f.get('duration_seconds', 0) for f in video_files)
                    limit_hit_msg = f"视频总时长不能超过 {MAX_VIDEO_DURATION} 秒（当前: {int(final_video_dur)} 秒）"

                # 【音频总时长检查】所有音频总时长不超过 15 秒，超限时移除多余文件
                audio_files = [f for f in self._all_files if f.get('type') == 'audio']
                total_audio_dur = sum(f.get('duration_seconds', 0) for f in audio_files)
                if total_audio_dur > MAX_AUDIO_DURATION:
                    logger.info(f"[Bridge] 音频总时长超限 ({total_audio_dur}s > {MAX_AUDIO_DURATION}s)，开始移除多余文件")
                    while audio_files and sum(f.get('duration_seconds', 0) for f in audio_files) > MAX_AUDIO_DURATION:
                        removed_audio = audio_files.pop(0)
                        self._all_files.remove(removed_audio)
                        logger.info(f"[Bridge] 已自动移除音频: {removed_audio.get('name')}")
                    audio_files = [f for f in self._all_files if f.get('type') == 'audio']
                    final_audio_dur = sum(f.get('duration_seconds', 0) for f in audio_files)
                    limit_hit_msg = f"音频总时长不能超过 {MAX_AUDIO_DURATION} 秒（当前: {int(final_audio_dur)} 秒）"

                # 发送完整列表给前端
                self.signal_files_updated.emit(json.dumps(self._all_files, ensure_ascii=False))

                # 超限时发送 Toast 提示到前端
                if limit_hit_msg:
                    self.signal_message.emit("toast", json.dumps({"message": limit_hit_msg}))

                # 更新 MainWindow 的文件统计
                from main import main_window
                if main_window:
                    main_window.set_file_counts(self._all_files)

                self.signal_progress.emit("process_files", 100, "文件处理完成")
                logger.info(f"[Bridge] 已追加 {len(new_files)} 个文件，总计: {len(self._all_files)}")

            except Exception as e:
                logger.error(f"[Bridge] 文件处理失败: {e}")
                self.signal_error.emit("process_files", str(e))
        
        # 异步执行，避免阻塞主线程
        from main import thread_pool
        thread_pool.submit(_do_process)

    def _process_file_list_for_editor(self, file_paths: List[str], drop_pos=None):
        """
        处理编辑区拖拽的文件，与 _process_file_list 类似，但完成后发送 signal_editor_dropped
        用于在编辑区光标位置插入标签
        @param file_paths: 文件路径列表
        @param drop_pos: drop 时的鼠标位置 (QPoint)，用于前端精准定位光标
        """

        def _do_process():
            try:
                self.signal_progress.emit("process_editor_drop", 10, "正在处理文件...")

                # 从 Bridge 自身的历史列表统计当前数量
                current_counts = {'image': 0, 'video': 0, 'audio': 0}
                for f in self._all_files:
                    file_type = f.get('type', 'unknown')
                    if file_type in current_counts:
                        current_counts[file_type] += 1

                # 记录已有文件路径，用于去重
                existing_paths = set(f['path'] for f in self._all_files)

                new_files: List[Dict[str, Any]] = []
                limit_hit_msg = None

                for i, file_path in enumerate(file_paths):
                    # 跳过已存在的文件
                    if file_path in existing_paths:
                        logger.info(f"[Bridge] 文件已存在，跳过: {file_path}")
                        continue

                    # 检查总数限制
                    total = len(self._all_files) + len(new_files)
                    if total >= MAX_TOTAL:
                        logger.info(f"[Bridge] 文件总数已达上限 ({MAX_TOTAL})")
                        limit_hit_msg = f"文件总数已达上限 ({MAX_TOTAL} 个)"
                        break

                    file_type = get_file_type(file_path)
                    if file_type == 'unknown':
                        logger.warning(f"[Bridge] 跳过不支持的文件类型: {file_path}")
                        continue

                    # 检查类型限制
                    current_type_count = current_counts.get(file_type, 0) + len([f for f in new_files if f['type'] == file_type])

                    if file_type == 'video' and current_type_count >= MAX_VIDEOS:
                        logger.info(f"[Bridge] 视频数量已达上限 ({MAX_VIDEOS})")
                        limit_hit_msg = f"视频最多支持 {MAX_VIDEOS} 个"
                        continue
                    elif file_type == 'audio' and current_type_count >= MAX_AUDIOS:
                        logger.info(f"[Bridge] 音频数量已达上限 ({MAX_AUDIOS})")
                        limit_hit_msg = f"音频最多支持 {MAX_AUDIOS} 个"
                        continue

                    # 构建文件信息
                    file_info: Dict[str, Any] = {
                        'type': file_type,
                        'path': file_path,
                        'name': os.path.basename(file_path),
                        'url': "file:///" + file_path.replace("\\", "/"),
                    }

                    # 视频/音频需要使用 FFmpeg 提取缩略图和时长
                    if file_type in ('video', 'audio'):
                        media_info = MediaProcessor.get_media_info(file_path)
                        file_info['thumbnail_base64'] = media_info.get('thumbnail_base64', '')
                        file_info['duration'] = media_info.get('duration', '00:00')
                        file_info['duration_seconds'] = media_info.get('duration_seconds', 0)

                    # 图片直接使用文件 URL 作为缩略图
                    elif file_type == 'image':
                        file_info['thumbnail_base64'] = file_info['url']

                    new_files.append(file_info)

                    # 更新进度
                    progress = min(90, 10 + (i + 1) * 80 // len(file_paths))
                    self.signal_progress.emit("process_editor_drop", progress, f"已处理 {i + 1}/{len(file_paths)} 个文件")

                # 追加新文件到历史列表
                self._all_files.extend(new_files)

                # 视频总时长检查
                video_files = [f for f in self._all_files if f.get('type') == 'video']
                total_video_dur = sum(f.get('duration_seconds', 0) for f in video_files)
                if total_video_dur > MAX_VIDEO_DURATION:
                    logger.info(f"[Bridge] 视频总时长超限")
                    while video_files and sum(f.get('duration_seconds', 0) for f in video_files) > MAX_VIDEO_DURATION:
                        removed_video = video_files.pop(0)
                        self._all_files.remove(removed_video)
                    limit_hit_msg = f"视频总时长不能超过 {MAX_VIDEO_DURATION} 秒"

                # 音频总时长检查
                audio_files = [f for f in self._all_files if f.get('type') == 'audio']
                total_audio_dur = sum(f.get('duration_seconds', 0) for f in audio_files)
                if total_audio_dur > MAX_AUDIO_DURATION:
                    logger.info(f"[Bridge] 音频总时长超限")
                    while audio_files and sum(f.get('duration_seconds', 0) for f in audio_files) > MAX_AUDIO_DURATION:
                        removed_audio = audio_files.pop(0)
                        self._all_files.remove(removed_audio)
                    limit_hit_msg = f"音频总时长不能超过 {MAX_AUDIO_DURATION} 秒"

                # 【关键修复】从 new_files 中过滤出仍然存在于 _all_files 的文件
                # （时长超限时，被移除的文件不应再插入标签）
                valid_new_files = [f for f in new_files if f in self._all_files]

                # 【关键】发送 signal_editor_dropped 信号，包含新增文件和 drop 位置
                # 前端收到后用 caretRangeFromPoint 在 drop 位置精准插入标签
                if valid_new_files:
                    # 计算新增文件的起始索引
                    start_index = len(self._all_files) - len(valid_new_files)
                    for idx, f in enumerate(valid_new_files):
                        f['insert_index'] = start_index + idx

                    # 构造包含 drop 位置的数据
                    signal_data = {
                        'files': valid_new_files,
                        'drop_pos': {'x': drop_pos.x(), 'y': drop_pos.y()} if drop_pos else None
                    }
                    self.signal_editor_dropped.emit(json.dumps(signal_data, ensure_ascii=False))
                    logger.info(f"[Bridge] 编辑区拖拽: 发送 {len(valid_new_files)} 个文件的标签插入信号 (pos={drop_pos})")

                # 同时发送完整文件列表更新上传区
                self.signal_files_updated.emit(json.dumps(self._all_files, ensure_ascii=False))

                # 超限时发送 Toast 提示
                if limit_hit_msg:
                    self.signal_message.emit("toast", json.dumps({"message": limit_hit_msg}))

                # 更新 MainWindow 的文件统计
                from main import main_window
                if main_window:
                    main_window.set_file_counts(self._all_files)

                self.signal_progress.emit("process_editor_drop", 100, "文件处理完成")
                logger.info(f"[Bridge] 编辑区拖拽完成: {len(valid_new_files)} 个新增文件 (原始: {len(new_files)})")

            except Exception as e:
                logger.error(f"[Bridge] 编辑区拖拽处理失败: {e}")
                self.signal_error.emit("process_editor_drop", str(e))

        # 异步执行
        from main import thread_pool
        thread_pool.submit(_do_process)

    # ===== 任务处理器 =====

    def _handle_start_server(self, params: dict):
        """启动服务"""
        task_id = "start_server"
        host = params.get('host', '127.0.0.1')
        port = params.get('port', 8765)

        def _do_start():
            try:
                from server import server_manager
                
                # 检查是否已经在运行
                if server_manager.is_running():
                    self.signal_result.emit(task_id, json.dumps({
                        "success": True,
                        "host": server_manager.host,
                        "port": server_manager.port,
                        "ws_url": f"ws://{server_manager.host}:{server_manager.port}/ws",
                        "message": "服务已在运行中"
                    }))
                    return
                
                self.signal_progress.emit(task_id, 10, "正在检查端口...")
                
                import socket
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(1)
                result = sock.connect_ex((host, port))
                sock.close()

                if result == 0:
                    self.signal_error.emit(task_id, f"端口 {port} 已被占用")
                    return

                self.signal_progress.emit(task_id, 30, "正在启动服务...")
                
                # 启动服务
                def on_ready():
                    self.signal_progress.emit(task_id, 80, "服务启动完成")
                
                success = server_manager.start(host, port, ready_callback=on_ready)
                
                if success:
                    self.signal_result.emit(task_id, json.dumps({
                        "success": True,
                        "host": host,
                        "port": port,
                        "ws_url": f"ws://{host}:{port}/ws"
                    }))
                else:
                    self.signal_error.emit(task_id, "服务启动失败")

            except Exception as e:
                logger.error(f"[Bridge] 启动服务失败: {e}")
                self.signal_error.emit(task_id, str(e))

        from main import thread_pool
        thread_pool.submit(_do_start)

    def _handle_stop_server(self, params: dict):
        """停止服务"""
        task_id = "stop_server"

        def _do_stop():
            try:
                from server import server_manager
                
                if not server_manager.is_running():
                    self.signal_result.emit(task_id, json.dumps({
                        "success": True,
                        "message": "服务未运行"
                    }))
                    return
                
                self.signal_progress.emit(task_id, 50, "正在关闭连接...")
                
                success = server_manager.stop()
                
                if success:
                    self.signal_result.emit(task_id, json.dumps({
                        "success": True,
                        "message": "服务已停止"
                    }))
                else:
                    self.signal_error.emit(task_id, "停止服务失败")

            except Exception as e:
                logger.error(f"[Bridge] 停止服务失败: {e}")
                self.signal_error.emit(task_id, str(e))

        from main import thread_pool
        thread_pool.submit(_do_stop)

    def _handle_get_presets(self, params: dict):
        """获取预设列表"""
        task_id = "get_presets"

        def _do_get():
            try:
                from preset_manager import get_preset_manager
                pm = get_preset_manager()
                presets = pm.get_all()
                self.signal_result.emit(task_id, json.dumps({
                    "success": True,
                    "presets": presets,
                    "count": len(presets)
                }))
            except Exception as e:
                self.signal_error.emit(task_id, str(e))

        from main import thread_pool
        thread_pool.submit(_do_get)

    def _handle_create_preset(self, params: dict):
        """创建预设"""
        task_id = "create_preset"

        def _do_create():
            try:
                self.signal_progress.emit(task_id, 20, "正在创建预设...")
                from preset_manager import get_preset_manager
                pm = get_preset_manager()

                preset = pm.create(
                    name=params.get('name', '未命名预设'),
                    settings=params.get('settings', {}),
                    text_content=params.get('prompt', ''),
                    image_uris=params.get('imageURIs', []),
                    file_path=params.get('file_path', '')
                )

                self.signal_progress.emit(task_id, 80, "预设创建完成")
                self.signal_result.emit(task_id, json.dumps({
                    "success": True,
                    "preset": preset
                }))
            except Exception as e:
                self.signal_error.emit(task_id, str(e))

        from main import thread_pool
        thread_pool.submit(_do_create)

    def _handle_apply_preset(self, params: dict):
        """应用预设"""
        task_id = "apply_preset"
        preset_id = params.get('id', '')

        def _do_apply():
            try:
                self.signal_progress.emit(task_id, 10, "正在加载预设...")
                from preset_manager import get_preset_manager
                pm = get_preset_manager()
                preset = pm.get_by_id(preset_id)

                if not preset:
                    self.signal_error.emit(task_id, f"预设不存在: {preset_id}")
                    return

                self.signal_result.emit(task_id, json.dumps({
                    "success": True,
                    "preset": preset
                }))
            except Exception as e:
                self.signal_error.emit(task_id, str(e))

        from main import thread_pool
        thread_pool.submit(_do_apply)

    def _handle_delete_preset(self, params: dict):
        """删除预设"""
        task_id = "delete_preset"
        preset_id = params.get('id', '')

        def _do_delete():
            try:
                from preset_manager import get_preset_manager
                pm = get_preset_manager()
                success = pm.delete(preset_id)
                self.signal_result.emit(task_id, json.dumps({
                    "success": success,
                    "preset_id": preset_id
                }))
            except Exception as e:
                self.signal_error.emit(task_id, str(e))

        from main import thread_pool
        thread_pool.submit(_do_delete)

    def _handle_generate(self, params: dict):
        """处理生成请求"""
        task_id = "generate"
        logger.info(f"[Generate] {params}")
        self.signal_result.emit(task_id, json.dumps({"success": True}))

    def _handle_get_server_status(self, params: dict):
        """获取服务状态"""
        from main import main_window, manager
        task_id = "get_server_status"
        self.signal_result.emit(task_id, json.dumps({
            "success": True,
            "running": main_window.server_running if main_window else False,
            "host": main_window.host if main_window else "127.0.0.1",
            "port": main_window.port if main_window else 8765,
            "connections": manager.connection_count
        }))


# ============ 固定导出 ============
__all__ = ['WebChannelBridge']
