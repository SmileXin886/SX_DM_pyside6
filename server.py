# -*- coding: utf-8 -*-
"""
Dreamina Toolkit - WebSocket 服务端模块
基于 FastAPI + uvicorn + websockets 构建的本地文件中继服务

核心职责:
1. 维护 WebSocket 长连接池，供浏览器扩展端连接
2. 响应浏览器端的预设请求（CRUD 操作）
3. 文件读取与流式传输（供预设应用时使用）
4. PySide6 集成：通过 QFileDialog 让用户选择本地文件

通信协议（JSON over WebSocket）:

  【预设操作】
  - GET_PRESETS:    获取所有预设列表
    请求: { "type": "GET_PRESETS" }
    响应: { "type": "PRESETS_LIST", "presets": [...], "count": n }

  - CREATE_PRESET:  创建新预设（触发文件选择弹窗）
    请求: { "type": "CREATE_PRESET", "name": "预设名", "settings": {...}, "textContent": "...", "imageURIs": [...] }
    响应: { "type": "PRESET_CREATED", "preset": {...} }
           或 { "type": "ERROR", "error": "..." }

  - APPLY_PRESET:   应用预设（读取文件并发送）
    请求: { "type": "APPLY_PRESET", "preset_id": "abc123" }
    响应（流式）:
      { "type": "PRESET_DATA", "preset": {...}, "hasFile": true, "fileName": "...", "fileSize": n, "mime": "..." }
      { "type": "FILE_CHUNK", "chunkIndex": 0, "data": "base64...", "offset": 0, "length": n, "isLast": false }
      ...
      { "type": "FILE_CHUNK", "chunkIndex": N, "data": "base64...", "offset": x, "length": n, "isLast": true }
      { "type": "PRESET_COMPLETE", "preset_id": "abc123" }
      或 { "type": "ERROR", "error": "..." }

  - DELETE_PRESET:  删除预设
    请求: { "type": "DELETE_PRESET", "preset_id": "abc123" }
    响应: { "type": "PRESET_DELETED", "preset_id": "abc123", "success": true }

  【心跳】
  - PING:           心跳检测
    请求: { "type": "PING" }
    响应: { "type": "PONG" }
"""

import asyncio
import base64
import json
import logging
import mimetypes
import os
import threading
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

# FastAPI 与 uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
import uvicorn

# PySide6（用于文件选择弹窗）
from PySide6.QtWidgets import QApplication, QFileDialog
from PySide6.QtCore import QTimer

# 本地模块
from preset_manager import get_preset_manager

logger = logging.getLogger("SX_DM.server")

# ============ 全局服务状态管理 ============

class ServerManager:
    """管理 uvicorn 服务的生命周期"""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._reset()
        return cls._instance
    
    def _reset(self):
        self.server = None
        self.thread = None
        self.running = False
        self.host = "127.0.0.1"
        self.port = 8765
    
    def is_running(self) -> bool:
        return self.running and self.server is not None
    
    def start(self, host: str = "127.0.0.1", port: int = 8765, ready_callback=None) -> bool:
        """启动服务"""
        if self.running:
            logger.warning("[Server] 服务已在运行中")
            return False
        
        self.host = host
        self.port = port
        
        def run_server():
            try:
                config = uvicorn.Config(
                    "server:app",
                    host=host,
                    port=port,
                    log_level="info",
                    access_log=False
                )
                self.server = uvicorn.Server(config)
                
                # 标记为运行中
                self.running = True
                if ready_callback:
                    ready_callback()
                
                # 运行服务（会阻塞当前线程）
                self.server.run()
            except Exception as e:
                logger.error(f"[Server] 启动失败: {e}")
                self._reset()
        
        self.thread = threading.Thread(target=run_server, daemon=True)
        self.thread.start()
        
        # 等待服务启动（最多 5 秒）
        import time
        for _ in range(50):
            time.sleep(0.1)
            if self.running:
                logger.info(f"[Server] 服务已启动: ws://{host}:{port}/ws")
                return True
        
        logger.warning("[Server] 服务启动超时")
        return False
    
    def stop(self) -> bool:
        """停止服务"""
        if not self.running or not self.server:
            logger.warning("[Server] 服务未运行")
            return False
        
        logger.info("[Server] 正在停止服务...")
        
        try:
            # 关闭服务器
            self.server.should_exit = True
            
            # 等待线程结束
            if self.thread and self.thread.is_alive():
                self.thread.join(timeout=3)
            
            # 关闭所有 WebSocket 连接
            asyncio.run(self._close_all_connections())
            
            self._reset()
            logger.info("[Server] 服务已停止")
            return True
            
        except Exception as e:
            logger.error(f"[Server] 停止失败: {e}")
            return False
    
    async def _close_all_connections(self):
        """关闭所有 WebSocket 连接"""
        try:
            from server import manager
            clients = list(manager.active_connections.keys())
            for client_id in clients:
                await manager.disconnect(client_id)
        except Exception as e:
            logger.warning(f"[Server] 关闭连接时出错: {e}")


# 全局服务管理器
server_manager = ServerManager()

# ============ PySide6 应用集成 ============
# 用于在 WebSocket 异步处理中触发 Qt 文件选择对话框


class QtIntegrator:
    """
    PySide6 与 asyncio 集成器
    解决异步 WebSocket 处理中调用 Qt UI 的线程安全问题
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self._qapp: Optional[QApplication] = None
        self._pending_file_dialogs: Dict[str, asyncio.Future] = {}
        self._initialized = True

    def set_qapp(self, qapp: QApplication):
        """注入 QApplication 实例"""
        self._qapp = qapp

    def get_qapp(self) -> Optional[QApplication]:
        """获取 QApplication 实例"""
        return self._qapp

    async def open_file_dialog(self, title: str = "选择素材文件",
                               filters: str = "视频文件 (*.mp4 *.avi *.mov *.mkv);;所有文件 (*.*)") -> Optional[str]:
        """
        在主线程打开文件选择对话框（异步安全）
        返回选中的文件路径，或 None（用户取消）
        """
        if self._qapp is None:
            logger.warning("[Qt] QApplication 未注入，无法打开文件对话框")
            return None

        loop = asyncio.get_running_loop()
        future = loop.create_future()

        # 存储待处理的对话框
        dialog_id = f"dialog_{id(future)}"
        self._pending_file_dialogs[dialog_id] = future

        # 在主线程执行 Qt 代码
        def _show_dialog():
            try:
                file_path, _ = QFileDialog.getOpenFileName(
                    None,  # parent
                    title,
                    "",     # dir（默认打开用户目录）
                    filters
                )
                if file_path:
                    loop.call_soon_threadsafe(future.set_result, file_path)
                else:
                    loop.call_soon_threadsafe(future.set_result, None)
            except Exception as e:
                logger.error(f"[Qt] 文件对话框异常: {e}")
                loop.call_soon_threadsafe(future.set_exception, e)
            finally:
                self._pending_file_dialogs.pop(dialog_id, None)

        # 调度到主线程
        QTimer.singleShot(0, _show_dialog)

        try:
            return await future
        except Exception as e:
            logger.error(f"[Qt] 文件对话框异常: {e}")
            return None


# 全局 Qt 集成器
qt_integrator = QtIntegrator()


def setup_logging():
    """配置结构化日志"""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
        datefmt="%H:%M:%S",
    )
    return logging.getLogger("SX_DM")


logger = setup_logging()


# ============ WebSocket 连接管理器 ============

class ConnectionManager:
    """管理所有 WebSocket 连接"""

    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.metadata: Dict[str, Dict] = {}
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, client_id: str, meta: dict = None):
        await websocket.accept()
        async with self._lock:
            self.active_connections[client_id] = websocket
            self.metadata[client_id] = {
                "connected_at": datetime.now().isoformat(),
                "user_agent": websocket.headers.get("user-agent", "unknown"),
                **(meta or {})
            }
        logger.info(f"[WS] 连接已建立: {client_id} (共 {len(self.active_connections)} 个)")

    async def disconnect(self, client_id: str):
        async with self._lock:
            self.active_connections.pop(client_id, None)
            self.metadata.pop(client_id, None)
        logger.info(f"[WS] 连接已断开: {client_id} (剩余 {len(self.active_connections)} 个)")

    async def send(self, client_id: str, message: dict):
        async with self._lock:
            ws = self.active_connections.get(client_id)
        if ws:
            await ws.send_json(message)

    async def broadcast(self, message: dict):
        disconnected = []
        async with self._lock:
            connections = list(self.active_connections.items())
        for cid, ws in connections:
            try:
                await ws.send_json(message)
            except Exception:
                disconnected.append(cid)
        for cid in disconnected:
            await self.disconnect(cid)

    @property
    def connection_count(self) -> int:
        return len(self.active_connections)


# 全局连接管理器
manager = ConnectionManager()

# 获取预设管理器
def get_pm():
    return get_preset_manager()


# ============ FastAPI 应用 ============

app = FastAPI(
    title="Dreamina Toolkit - 预设管理服务",
    version="2.0.0",
    description="浏览器扩展端与本地预设/文件的 WebSocket 中转服务",
    docs_url=None,
    redoc_url=None,
)


# ---------- HTTP 端点 ----------

@app.get("/", tags=["health"])
async def root():
    """服务健康检查"""
    pm = get_pm()
    return JSONResponse({
        "service": "Dreamina Toolkit - Preset Manager",
        "version": "2.0.0",
        "status": "running",
        "connections": manager.connection_count,
        "presets_count": pm.count(),
        "timestamp": datetime.now().isoformat()
    })


@app.get("/health", tags=["health"])
async def health():
    """详细健康检查"""
    pm = get_pm()
    return JSONResponse({
        "status": "ok",
        "websocket_connections": manager.connection_count,
        "presets": {
            "count": pm.count(),
            "summary": pm.get_summary()
        }
    })


@app.get("/presets", tags=["presets"])
async def get_all_presets():
    """HTTP API：获取所有预设"""
    pm = get_pm()
    return JSONResponse({
        "presets": pm.get_all(),
        "count": pm.count()
    })


@app.delete("/presets/{preset_id}", tags=["presets"])
async def delete_preset(preset_id: str):
    """HTTP API：删除预设"""
    pm = get_pm()
    success = pm.delete(preset_id)
    return JSONResponse({"success": success, "preset_id": preset_id})


# ---------- WebSocket 端点 ----------

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket 端点 - 处理所有预设相关请求
    """
    import uuid
    client_id = str(uuid.uuid4())[:8]

    try:
        await manager.connect(websocket, client_id, {"remote_addr": websocket.client})

        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json({
                    "type": "ERROR",
                    "error": "Invalid JSON"
                })
                continue

            await handle_client_message(client_id, msg)

    except WebSocketDisconnect:
        logger.info(f"[WS] 客户端断开: {client_id}")
    except Exception as e:
        logger.error(f"[WS] 异常 [{client_id}]: {e}\n{traceback.format_exc()}")
    finally:
        await manager.disconnect(client_id)


async def handle_client_message(client_id: str, msg: dict):
    """
    处理客户端请求的核心调度函数
    """
    msg_type = msg.get("type", "")
    request_id = msg.get("id", "")
    pm = get_pm()

    # ---- 心跳 ----
    if msg_type == "PING":
        await manager.send(client_id, {"type": "PONG", "id": request_id})
        return

    # ---- 获取预设列表 ----
    if msg_type == "GET_PRESETS":
        logger.info(f"[GET_PRESETS] [{client_id}]")
        presets = pm.get_all()
        await manager.send(client_id, {
            "type": "PRESETS_LIST",
            "id": request_id,
            "presets": presets,
            "count": len(presets)
        })
        return

    # ---- 创建预设 ----
    if msg_type == "CREATE_PRESET":
        name = msg.get("name", "未命名预设")
        settings = msg.get("settings", {})
        text_content = msg.get("textContent", "")
        image_uris = msg.get("imageURIs", [])

        logger.info(f"[CREATE_PRESET] [{client_id}] {name}")

        # 弹出文件选择对话框
        file_path = None
        qt = qt_integrator
        if qt.get_qapp() is not None:
            file_path = await qt.open_file_dialog(
                title=f"选择【{name}】的素材文件",
                filters="视频文件 (*.mp4 *.avi *.mov *.mkv *.webm);;图片文件 (*.jpg *.jpeg *.png *.gif *.webp);;音频文件 (*.mp3 *.wav *.aac);;所有文件 (*.*)"
            )
        else:
            logger.warning("[CREATE_PRESET] QApplication 未注入，跳过文件选择")
            file_path = None

        try:
            preset = pm.create(
                name=name,
                settings=settings,
                text_content=text_content,
                image_uris=image_uris,
                file_path=file_path or ""
            )
            await manager.send(client_id, {
                "type": "PRESET_CREATED",
                "id": request_id,
                "preset": preset
            })
            logger.info(f"[CREATE_PRESET] 成功创建: {preset['id']}")
        except Exception as e:
            logger.error(f"[CREATE_PRESET] 创建失败: {e}")
            await manager.send(client_id, {
                "type": "ERROR",
                "id": request_id,
                "error": str(e)
            })
        return

    # ---- 应用预设 ----
    if msg_type == "APPLY_PRESET":
        preset_id = msg.get("preset_id", "")

        logger.info(f"[APPLY_PRESET] [{client_id}] {preset_id}")

        preset = pm.get_by_id(preset_id)
        if not preset:
            await manager.send(client_id, {
                "type": "ERROR",
                "id": request_id,
                "error": f"预设不存在: {preset_id}"
            })
            return

        file_path = preset.get("file_path", "")
        has_file = bool(file_path and os.path.isfile(file_path))

        # 发送预设数据头
        response_header = {
            "type": "PRESET_DATA",
            "id": request_id,
            "preset": {
                "id": preset["id"],
                "name": preset["name"],
                "settings": preset.get("settings", {}),
                "textContent": preset.get("textContent", ""),
                "imageURIs": preset.get("imageURIs", [])
            },
            "hasFile": has_file,
            "fileName": os.path.basename(file_path) if has_file else None,
            "fileSize": os.path.getsize(file_path) if has_file else None,
            "mime": mimetypes.guess_type(file_path)[0] if has_file else None
        }
        await manager.send(client_id, response_header)

        # 如果有文件，分块发送
        if has_file:
            try:
                await send_file_in_chunks(client_id, request_id, file_path)
            except Exception as e:
                logger.error(f"[APPLY_PRESET] 文件发送失败: {e}")
                await manager.send(client_id, {
                    "type": "FILE_ERROR",
                    "id": request_id,
                    "error": str(e)
                })
                return

        # 发送完成信号
        await manager.send(client_id, {
            "type": "PRESET_COMPLETE",
            "id": request_id,
            "preset_id": preset_id
        })
        logger.info(f"[APPLY_PRESET] 完成: {preset_id}")
        return

    # ---- 删除预设 ----
    if msg_type == "DELETE_PRESET":
        preset_id = msg.get("preset_id", "")

        logger.info(f"[DELETE_PRESET] [{client_id}] {preset_id}")

        success = pm.delete(preset_id)
        await manager.send(client_id, {
            "type": "PRESET_DELETED",
            "id": request_id,
            "preset_id": preset_id,
            "success": success
        })
        return

    # ---- 未知消息类型 ----
    await manager.send(client_id, {
        "type": "ERROR",
        "id": request_id,
        "error": f"Unknown message type: {msg_type}"
    })


async def send_file_in_chunks(client_id: str, request_id: str, file_path: str):
    """
    分块流式发送文件
    每块约 256KB，通过多个 WebSocket 消息发送
    """
    chunk_size = 256 * 1024  # 256KB
    file_size = os.path.getsize(file_path)

    offset = 0
    chunk_index = 0

    try:
        with open(file_path, "rb") as f:
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break

                is_last = (offset + len(chunk)) >= file_size
                data_b64 = base64.b64encode(chunk).decode("ascii")

                await manager.send(client_id, {
                    "type": "FILE_CHUNK",
                    "id": request_id,
                    "chunkIndex": chunk_index,
                    "data": data_b64,
                    "offset": offset,
                    "length": len(chunk),
                    "isLast": is_last
                })

                offset += len(chunk)
                chunk_index += 1

                # 防止发送过快（每 4 个分块暂停一下）
                if chunk_index % 4 == 0:
                    await asyncio.sleep(0.005)

        logger.info(f"[STREAM] [{client_id}] {os.path.basename(file_path)} 发送完成 ({chunk_index} chunks)")

    except Exception as e:
        logger.error(f"[STREAM] [{client_id}] {file_path} 失败: {e}")
        raise


# ============ 启动入口 ============

def run_server(host: str = "127.0.0.1", port: int = 8765, reload: bool = False):
    """通过 uvicorn 启动服务"""
    logger.info(f"{'=' * 50}")
    logger.info(f"  Dreamina Toolkit - 预设管理服务 v2.0")
    logger.info(f"  WS 端点: ws://{host}:{port}/ws")
    logger.info(f"  HTTP 端点: http://{host}:{port}")
    logger.info(f"{'=' * 50}")

    uvicorn.run(
        "server:app",
        host=host,
        port=port,
        reload=reload,
        log_level="info",
    )


if __name__ == "__main__":
    run_server()
