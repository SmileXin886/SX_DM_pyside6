/**
 * 中央通信层 (api.js)
 * ==================
 * 统一管理所有与 pyBridge 的交互
 * 采用中央转发器模式：所有 pyBridge 信号监听在此集中，通过事件总线分发
 */

(function() {
    'use strict';

    console.log('[api.js] 通信层加载中...');

    // ===== 事件总线 =====
    const EventBus = {
        _listeners: {},

        /**
         * 订阅事件
         * @param {string} event - 事件名称
         * @param {function} callback - 回调函数
         */
        on: function(event, callback) {
            if (!this._listeners[event]) {
                this._listeners[event] = [];
            }
            this._listeners[event].push(callback);
            console.log(`[EventBus] 订阅事件: ${event} (总计 ${this._listeners[event].length} 个监听器)`);
        },

        /**
         * 取消订阅
         * @param {string} event - 事件名称
         * @param {function} callback - 回调函数
         */
        off: function(event, callback) {
            if (!this._listeners[event]) return;
            this._listeners[event] = this._listeners[event].filter(cb => cb !== callback);
        },

        /**
         * 触发事件
         * @param {string} event - 事件名称
         * @param {*} data - 事件数据
         */
        emit: function(event, data) {
            if (!this._listeners[event]) return;
            console.log(`[EventBus] 触发事件: ${event}`, data);
            this._listeners[event].forEach(callback => {
                try {
                    callback(data);
                } catch (e) {
                    console.error(`[EventBus] 事件 ${event} 处理出错:`, e);
                }
            });
        }
    };

    // 导出到全局
    window.EventBus = EventBus;


    // ===== API 核心对象 =====

    const API = {
        _bridgeReady: false,

        /**
         * 初始化 pyBridge 连接
         * 由 app.js 在 DOMContentLoaded 后调用
         */
        init: function() {
            this._waitForBridge();
        },

        /**
         * 轮询等待 pyBridge 就绪
         */
        _waitForBridge: function() {
            let attempts = 0;
            const maxAttempts = 50;

            const checkBridge = () => {
                attempts++;
                if (window.pyBridge) {
                    console.log('[API] pyBridge 已就绪，开始绑定信号...');
                    this._bindSignals();
                    this._bridgeReady = true;
                    EventBus.emit('bridge:ready');
                    return;
                }

                if (attempts < maxAttempts) {
                    setTimeout(checkBridge, 100);
                } else {
                    console.error('[API] pyBridge 连接超时');
                    EventBus.emit('bridge:error', { message: 'Bridge 连接超时' });
                }
            };

            checkBridge();
        },

        /**
         * 绑定 Python 信号（中央转发器）
         */
        _bindSignals: function() {
            if (!window.pyBridge) return;

            // signal_result: 任务结果
            window.pyBridge.signal_result.connect(function(taskId, result) {
                console.log(`[API] signal_result: ${taskId}`, result);
                let parsedResult = result;
                try {
                    parsedResult = JSON.parse(result);
                } catch (e) {}

                // 根据 taskId 路由分发
                if (taskId === 'start_server') {
                    EventBus.emit('server:start', parsedResult);
                } else if (taskId === 'stop_server') {
                    EventBus.emit('server:stop', parsedResult);
                } else if (taskId === 'get_presets') {
                    EventBus.emit('presets:loaded', parsedResult);
                } else if (taskId === 'create_preset') {
                    EventBus.emit('preset:created', parsedResult);
                } else if (taskId === 'apply_preset') {
                    EventBus.emit('preset:applied', parsedResult);
                } else if (taskId === 'delete_preset') {
                    EventBus.emit('preset:deleted', parsedResult);
                } else {
                    EventBus.emit('result:default', { taskId, result: parsedResult });
                }
            });

            // signal_progress: 任务进度
            window.pyBridge.signal_progress.connect(function(taskId, percent, msg) {
                console.log(`[API] signal_progress: ${taskId} - ${percent}% - ${msg}`);
                EventBus.emit('progress:' + taskId, { percent, message: msg });
                EventBus.emit('progress:any', { taskId, percent, message: msg });
            });

            // signal_error: 错误信息
            window.pyBridge.signal_error.connect(function(taskId, error) {
                console.error(`[API] signal_error: ${taskId} - ${error}`);
                EventBus.emit('error:' + taskId, { error });
                EventBus.emit('error:any', { taskId, error });
            });

            // signal_message: 通用消息
            window.pyBridge.signal_message.connect(function(action, data) {
                console.log(`[API] signal_message: ${action}`, data);
                let parsedData = data;
                try {
                    parsedData = JSON.parse(data);
                } catch (e) {}

                // 根据 action 分发
                if (action === 'log') {
                    EventBus.emit('log', parsedData);
                } else if (action === 'files_updated') {
                    EventBus.emit('files:updated', parsedData);
                } else if (action === 'files_dropped') {
                    EventBus.emit('files:dropped', parsedData);
                } else if (action === 'toast') {
                    EventBus.emit('toast', parsedData);
                } else {
                    EventBus.emit('message:default', { action, data: parsedData });
                }
            });

            // signal_files_updated: 文件列表更新
            window.pyBridge.signal_files_updated.connect(function(filesJson) {
                console.log('[API] signal_files_updated:', filesJson);
                try {
                    const files = JSON.parse(filesJson);
                    EventBus.emit('files:listUpdated', files);
                } catch (e) {
                    console.error('[API] 解析文件列表失败:', e);
                }
            });

            // signal_editor_dropped: 编辑区拖拽
            window.pyBridge.signal_editor_dropped.connect(function(dataJson) {
                console.log('[API] signal_editor_dropped:', dataJson);
                try {
                    const data = JSON.parse(dataJson);
                    EventBus.emit('editor:dropped', data);
                } catch (e) {
                    console.error('[API] 解析拖拽数据失败:', e);
                }
            });

            // signal_file_removed: 文件删除（触发编辑区标签同步）
            window.pyBridge.signal_file_removed.connect(function(deletedFileJson) {
                console.log('[API] signal_file_removed:', deletedFileJson);
                try {
                    const deletedFile = JSON.parse(deletedFileJson);
                    EventBus.emit('file:removed', deletedFile);
                } catch (e) {
                    console.error('[API] 解析删除文件数据失败:', e);
                }
            });

            console.log('[API] 所有信号已绑定到 EventBus');
        },

        /**
         * 调用 Python 后端
         * @param {string} action - 操作名称
         * @param {object} params - 参数对象
         */
        call: function(action, params) {
            console.log(`[API] qtCall: ${action}`, params);
            if (window.pyBridge) {
                window.pyBridge.receiveMessage(action, JSON.stringify(params || {}));
            } else {
                console.error('[API] pyBridge 不可用');
            }
        },

        /**
         * 检查 Bridge 是否就绪
         */
        isReady: function() {
            return this._bridgeReady;
        }
    };

    // 导出到全局
    window.API = API;

    console.log('[api.js] 通信层已加载 (中央转发器模式)');

})();
