# -*- coding: utf-8 -*-
"""
Dreamina Toolkit - 本地文件处理模块
负责遍历目录、读取文件、生成文件元数据等 IO 操作

职责：
1. 扫描指定素材目录，递归/非递归列出文件
2. 按扩展名过滤（图片、视频、音频）
3. 将文件读取为 Base64
4. 搜索文件（按名称关键字）
5. 计算文件哈希（用于去重）
"""

import base64
import hashlib
import logging
import mimetypes
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger("SX_DM.file_handler")


class FileHandler:
    """
    本地文件处理器。

    Attributes:
        media_dir: 当前配置的素材根目录。
        max_file_size_mb: 单文件最大体积（MB），超出则拒绝读取。
        supported_extensions: 支持的文件扩展名集合。
    """

    # 默认支持的素材扩展名（不区分大小写）
    DEFAULT_EXTENSIONS = {
        # 图片
        ".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".svg", ".ico",
        ".tiff", ".tif", ".heic", ".avif",
        # 视频
        ".mp4", ".mov", ".avi", ".mkv", ".webm", ".flv", ".wmv",
        ".m4v", ".mpg", ".mpeg", ".3gp", ".ts",
        # 音频
        ".mp3", ".wav", ".aac", ".flac", ".ogg", ".m4a", ".wma",
        ".aiff", ".opus",
    }

    def __init__(
        self,
        media_dir: str = "",
        max_file_size_mb: int = 500,
        supported_extensions: set = None,
    ):
        self.media_dir = self._resolve_home(media_dir) if media_dir else ""
        self.max_file_size_mb = max_file_size_mb
        self.supported_extensions = supported_extensions or self.DEFAULT_EXTENSIONS

        # 预热 mimetypes
        mimetypes.init()

    # ---- 公共 API ----

    def set_media_dir(self, path: str) -> bool:
        """
        设置素材目录。
        验证路径是否存在且可访问。
        Returns:
            True if valid, False otherwise.
        """
        resolved = self._resolve_home(path)
        if os.path.isdir(resolved):
            self.media_dir = resolved
            logger.info(f"[FileHandler] 素材目录已设置: {resolved}")
            return True
        logger.warning(f"[FileHandler] 目录无效: {resolved}")
        return False

    def list_directory(
        self,
        path: str = None,
        recursive: bool = False,
        max_results: int = 500,
    ) -> list[dict]:
        """
        列出目录中的文件。

        Args:
            path: 目标目录（默认为 media_dir）。
            recursive: 是否递归扫描子目录。
            max_results: 最大返回条数（防止超长列表）。

        Returns:
            文件对象列表，每个对象包含:
            { name, path, size, mime, ext, modified, is_dir }
        """
        target = self._resolve_path(path) or self.media_dir
        if not os.path.isdir(target):
            logger.warning(f"[FileHandler] 目录不存在: {target}")
            return []

        results = []
        count = 0

        try:
            if recursive:
                for root, dirs, files in os.walk(target):
                    for fname in files:
                        if count >= max_results:
                            break
                        fpath = os.path.join(root, fname)
                        info = self._file_info(fpath)
                        if info:
                            results.append(info)
                            count += 1
                    if count >= max_results:
                        break
            else:
                with os.scandir(target) as it:
                    for entry in it:
                        if count >= max_results:
                            break
                        if entry.is_file():
                            info = self._file_info(entry.path)
                            if info:
                                results.append(info)
                                count += 1
        except PermissionError:
            logger.warning(f"[FileHandler] 无权限访问: {target}")
        except Exception as e:
            logger.error(f"[FileHandler] 扫描失败: {e}")

        logger.info(f"[FileHandler] 列出 {target}: {len(results)} 个文件")
        return results

    def search_files(
        self,
        path: str = None,
        keyword: str = "",
        max_results: int = 200,
    ) -> list[dict]:
        """
        在目录中搜索文件名包含关键字的文件。

        Args:
            path: 搜索目录（默认为 media_dir）。
            keyword: 文件名关键字（不区分大小写）。
            max_results: 最大返回条数。

        Returns:
            匹配的文件对象列表。
        """
        if not keyword:
            return []

        target = self._resolve_path(path) or self.media_dir
        if not os.path.isdir(target):
            return []

        keyword_lower = keyword.lower()
        results = []
        count = 0

        try:
            for root, dirs, files in os.walk(target):
                for fname in files:
                    if keyword_lower not in fname.lower():
                        continue
                    fpath = os.path.join(root, fname)
                    info = self._file_info(fpath)
                    if info:
                        results.append(info)
                        count += 1
                        if count >= max_results:
                            break
                if count >= max_results:
                    break
        except PermissionError:
            pass
        except Exception as e:
            logger.error(f"[FileHandler] 搜索失败: {e}")

        return results

    def read_file_as_base64(self, file_path: str) -> str:
        """
        将文件读取为 Base64 字符串。
        自动检查文件大小限制。

        Args:
            file_path: 文件绝对路径。

        Returns:
            Base64 编码字符串（不含 data URI 前缀）。

        Raises:
            FileNotFoundError: 文件不存在。
            PermissionError: 无读取权限。
            ValueError: 文件过大。
        """
        fpath = os.path.abspath(file_path)
        if not os.path.isfile(fpath):
            raise FileNotFoundError(f"文件不存在: {fpath}")

        size = os.path.getsize(fpath)
        max_bytes = self.max_file_size_mb * 1024 * 1024
        if size > max_bytes:
            raise ValueError(
                f"文件过大 ({size / 1024 / 1024:.1f}MB > {self.max_file_size_mb}MB)"
            )

        with open(fpath, "rb") as f:
            return base64.b64encode(f.read()).decode("ascii")

    def get_file_info(self, file_path: str) -> Optional[dict]:
        """
        获取单个文件的元信息。

        Args:
            file_path: 文件路径。

        Returns:
            文件信息 dict，失败返回 None。
        """
        return self._file_info(file_path)

    def compute_file_hash(self, file_path: str, algorithm: str = "md5") -> Optional[str]:
        """
        计算文件哈希（用于去重）。

        Args:
            file_path: 文件路径。
            algorithm: 哈希算法 ("md5", "sha1", "sha256")。

        Returns:
            十六进制哈希字符串，失败返回 None。
        """
        try:
            h = hashlib.new(algorithm)
            with open(file_path, "rb") as f:
                # 分块读取，防止大文件内存爆炸
                for chunk in iter(lambda: f.read(8192), b""):
                    h.update(chunk)
            return h.hexdigest()
        except Exception as e:
            logger.error(f"[FileHandler] 哈希计算失败 {file_path}: {e}")
            return None

    # ---- 内部工具 ----

    def _file_info(self, file_path: str) -> Optional[dict]:
        """
        生成单个文件的元信息字典。
        仅返回支持的扩展名文件。
        """
        try:
            stat = os.stat(file_path)
            ext = os.path.splitext(file_path)[1].lower()

            # 过滤不支持的扩展名
            if ext not in self.supported_extensions:
                return None

            mime = mimetypes.guess_type(file_path)[0] or "application/octet-stream"

            return {
                "name": os.path.basename(file_path),
                "path": file_path,
                "size": stat.st_size,
                "size_human": self._human_size(stat.st_size),
                "mime": mime,
                "ext": ext,
                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                "is_dir": False,
            }
        except (OSError, PermissionError):
            return None

    def _resolve_path(self, path: str = None) -> Optional[str]:
        """将相对路径或 ~ 路径转换为绝对路径"""
        if not path:
            return None
        return self._resolve_home(path)

    @staticmethod
    def _resolve_home(path: str) -> str:
        """将 ~ 展开为用户主目录"""
        return os.path.abspath(os.path.expanduser(path))

    @staticmethod
    def _human_size(size_bytes: int) -> str:
        """字节数 → 人类可读字符串"""
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if size_bytes < 1024:
                return f"{size_bytes:.1f}{unit}"
            size_bytes /= 1024
        return f"{size_bytes:.1f}PB"
