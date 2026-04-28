/**
 * 编辑器标签同步模块
 *
 * 职责：监听上传区文件删除事件，自动移除编辑区（#dreaminaPrompt）中对应的素材标签
 *
 * 联动逻辑：
 * 1. 监听 'file:removed' 事件，获取被删除的文件信息
 * 2. 在编辑区内查找匹配的标签节点（通过 dataset.index）
 * 3. 移除匹配节点后，派发 'input' 事件通知框架更新状态
 */

(function() {
    'use strict';

    // 素材标签的选择器
    const TAG_SELECTOR = '.ref-tag';

    // 标记是否已初始化
    var _initialized = false;

    // 初始化
    function init() {
        if (_initialized) return;
        _initialized = true;

        console.log('[EditorTagSync] 初始化编辑器标签同步模块');

        // 监听文件删除事件
        if (window.EventBus) {
            window.EventBus.on('file:removed', handleFileRemoved);
            _listeningToFileRemoved = true;
            console.log('[EditorTagSync] 已订阅 file:removed 事件');
        } else {
            console.warn('[EditorTagSync] EventBus 未就绪，等待...');
            // 如果 EventBus 还未就绪，等待它就绪
            document.addEventListener('bridge-ready', function onBridgeReady() {
                document.removeEventListener('bridge-ready', onBridgeReady);
                if (window.EventBus) {
                    window.EventBus.on('file:removed', handleFileRemoved);
                    console.log('[EditorTagSync] EventBus 就绪后，已订阅 file:removed 事件');
                }
            });
            // 备用：也监听 api.js 中定义的 bridge-ready 事件
            window.addEventListener('load', function() {
                setTimeout(function() {
                    if (window.EventBus && !_listeningToFileRemoved) {
                        window.EventBus.on('file:removed', handleFileRemoved);
                        console.log('[EditorTagSync] (备用) 已订阅 file:removed 事件');
                    }
                }, 500);
            });
        }
    }

    // 用于追踪是否已订阅
    var _listeningToFileRemoved = false;

    /**
     * 处理文件删除事件
     * @param {Object} deletedFileInfo - 被删除文件的信息，包含 path、name 等标识
     */
    function handleFileRemoved(deletedFileInfo) {
        console.log('[EditorTagSync] 收到文件删除事件', deletedFileInfo);

        const editor = document.getElementById('dreaminaPrompt');
        if (!editor) {
            console.warn('[EditorTagSync] 编辑区 #dreaminaPrompt 不存在');
            return;
        }

        // 获取编辑区内所有素材标签
        const tags = editor.querySelectorAll(TAG_SELECTOR);
        if (tags.length === 0) {
            console.log('[EditorTagSync] 编辑区内没有素材标签');
            return;
        }

        console.log('[EditorTagSync] 扫描', tags.length, '个素材标签，查找匹配项...');

        // 收集待删除的标签
        const tagsToRemove = [];

        tags.forEach(function(tag) {
            const tagIndex = parseInt(tag.dataset.index, 10);
            const tagPath = tag.dataset.path || '';
            const tagName = tag.dataset.name || '';
            const tagUrl = tag.dataset.url || '';

            // 通过路径匹配（最可靠）
            const deletedPath = deletedFileInfo.path || '';
            if (deletedPath && tagPath && tagPath === deletedPath) {
                tagsToRemove.push(tag);
                console.log('[EditorTagSync] 路径匹配，移除标签 (path=' + tagPath + ')');
                return;
            }

            // 通过文件名匹配（备选）
            const deletedName = deletedFileInfo.name || '';
            if (deletedName && tagName && tagName === deletedName) {
                tagsToRemove.push(tag);
                console.log('[EditorTagSync] 文件名匹配，移除标签 (name=' + tagName + ')');
                return;
            }

            // 通过 URL 匹配（备选）
            if (deletedFileInfo.url && tagUrl && tagUrl === deletedFileInfo.url) {
                tagsToRemove.push(tag);
                console.log('[EditorTagSync] URL匹配，移除标签 (url=' + tagUrl + ')');
                return;
            }
        });

        // 执行删除
        if (tagsToRemove.length > 0) {
            tagsToRemove.forEach(function(tag) {
                // 将光标移到标签之前（如果光标恰好在标签内）
                const selection = window.getSelection();
                if (selection.rangeCount > 0) {
                    const range = selection.getRangeAt(0);
                    if (tag.contains(range.startContainer)) {
                        const newRange = document.createRange();
                        newRange.setStartBefore(tag);
                        newRange.collapse(true);
                        selection.removeAllRanges();
                        selection.addRange(newRange);
                    }
                }

                tag.remove();
            });

            console.log('[EditorTagSync] 已移除', tagsToRemove.length, '个标签');

            // 派发 input 事件，通知框架更新状态
            editor.dispatchEvent(new Event('input', { bubbles: true }));
            console.log('[EditorTagSync] 已派发 input 事件');
        } else {
            console.log('[EditorTagSync] 没有找到匹配的标签');
        }
    }

    /**
     * 手动同步：根据当前文件列表清理编辑区中的过期标签
     * 当文件列表被更新时调用，移除所有不在列表中的标签
     * @param {Array} currentFiles - 当前文件列表
     */
    function syncWithFileList(currentFiles) {
        const editor = document.getElementById('dreaminaPrompt');
        if (!editor) return;

        const tags = editor.querySelectorAll(TAG_SELECTOR);
        if (tags.length === 0) return;

        const validIndices = new Set();
        if (currentFiles) {
            currentFiles.forEach(function(file, idx) {
                validIndices.add(idx);
            });
        }

        const tagsToRemove = [];
        tags.forEach(function(tag) {
            const tagIndex = parseInt(tag.dataset.index, 10);
            if (!validIndices.has(tagIndex)) {
                tagsToRemove.push(tag);
            }
        });

        if (tagsToRemove.length > 0) {
            tagsToRemove.forEach(function(tag) {
                tag.remove();
            });
            editor.dispatchEvent(new Event('input', { bubbles: true }));
            console.log('[EditorTagSync] 同步清理，移除', tagsToRemove.length, '个过期标签');
        }
    }

    // 挂载到 window 以便外部调用
    window.EditorTagSync = {
        handleFileRemoved: handleFileRemoved,
        syncWithFileList: syncWithFileList
    };

    // 页面加载完成后初始化
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

})();
