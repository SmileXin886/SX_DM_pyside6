/**
 * 服务控制台模块 (tab_service.js)
 * ==============================
 * 负责 page-service 的所有 UI 交互和状态同步
 * 通过 EventBus 订阅/发布事件，不直接操作 pyBridge
 */

const TabService = {
    _initialized: false,

    /**
     * 初始化模块
     */
    init: function() {
        if (this._initialized) return;
        this._initialized = true;

        // 绑定 UI 事件
        this._bindEvents();

        // 订阅 EventBus 事件
        this._subscribeEvents();

        console.log('[tab_service.js] 模块初始化完成');
    },

    /**
     * 绑定 UI 交互事件
     */
    _bindEvents: function() {
        // 启动/停止按钮
        const startBtn = document.getElementById('startBtn');
        if (startBtn) {
            startBtn.addEventListener('click', () => this.toggleServer());
        }

        // 清空日志按钮
        const clearBtn = document.getElementById('clearLogsBtn');
        if (clearBtn) {
            clearBtn.addEventListener('click', () => this.clearLogs());
        }

        console.log('[tab_service.js] UI 事件已绑定');
    },

    /**
     * 订阅 EventBus 事件
     */
    _subscribeEvents: function() {
        // 服务器启动成功
        EventBus.on('server:start', (result) => {
            console.log('[TabService] 收到 server:start', result);
            if (result.success) {
                AppState.setServerRunning(true);
                AppState.setWsUrl(result.ws_url);
                this.updateServerUI(true);
                this.addLog(`服务已启动: ${result.ws_url}`, 'success');
                document.getElementById('wsUrl').textContent = result.ws_url;
            } else {
                this.addLog('服务启动失败: ' + (result.error || '未知错误'), 'error');
                this.updateServerUI(false);
            }
        });

        // 服务器停止
        EventBus.on('server:stop', (result) => {
            console.log('[TabService] 收到 server:stop', result);
            AppState.setServerRunning(false);
            this.updateServerUI(false);
            this.addLog('服务已停止', 'info');
        });

        // 服务器启动进度
        EventBus.on('progress:start_server', (data) => {
            console.log('[TabService] 收到启动进度', data);
            this._showStartingState(data.message);
        });

        // 服务器启动错误
        EventBus.on('error:start_server', (data) => {
            console.error('[TabService] 收到启动错误', data);
            this.addLog(`启动失败: ${data.error}`, 'error');
            this._resetStartButton();
        });

        // 通用日志
        EventBus.on('log', (data) => {
            this.addLog(data.message, data.type || 'info');
        });

        console.log('[tab_service.js] EventBus 事件已订阅');
    },

    /**
     * 切换服务状态
     */
    toggleServer: function() {
        const btn = document.getElementById('startBtn');
        const isRunning = btn.classList.contains('running');

        if (isRunning) {
            // 停止服务
            API.call('stop_server', {});
        } else {
            // 启动服务
            this._showStartingState('启动中...');
            const host = document.getElementById('hostInput').value || '127.0.0.1';
            const port = parseInt(document.getElementById('portInput').value) || 8765;
            AppState.addPendingTask('start_server');
            API.call('start_server', { host, port });
        }
    },

    /**
     * 显示启动中状态
     */
    _showStartingState: function(message) {
        const btn = document.getElementById('startBtn');
        btn.disabled = true;
        btn.innerHTML = `
            <svg class="animate-spin" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <circle cx="12" cy="12" r="10" stroke-opacity="0.25"/>
                <path d="M12 2a10 10 0 0 1 10 10"/>
            </svg>
            ${message || '启动中...'}
        `;
    },

    /**
     * 重置启动按钮
     */
    _resetStartButton: function() {
        const btn = document.getElementById('startBtn');
        btn.disabled = false;
        btn.innerHTML = `
            <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
                <polygon points="5 3 19 12 5 21 5 3"/>
            </svg>
            启动服务
        `;
        AppState.removePendingTask('start_server');
    },

    /**
     * 更新服务 UI 状态
     */
    updateServerUI: function(running) {
        const btn = document.getElementById('startBtn');
        const dot = document.getElementById('statusDot');
        const text = document.getElementById('statusText');

        btn.disabled = false;

        if (running) {
            btn.innerHTML = `
                <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
                    <rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/>
                </svg>
                停止服务
            `;
            btn.classList.add('running');
            dot.classList.add('online');
            text.textContent = '在线';
            text.style.color = '#3fb950';
        } else {
            btn.innerHTML = `
                <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
                    <polygon points="5 3 19 12 5 21 5 3"/>
                </svg>
                启动服务
            `;
            btn.classList.remove('running');
            dot.classList.remove('online');
            text.textContent = '离线';
            text.style.color = '#8b949e';
        }

        AppState.removePendingTask('start_server');
    },

    /**
     * 添加日志条目
     */
    addLog: function(message, type = 'info') {
        const panel = document.getElementById('logPanel');
        if (!panel) return;

        const time = new Date().toLocaleTimeString('zh-CN', { hour12: false });
        const div = document.createElement('div');
        div.className = `log-line log-${type}`;
        div.textContent = `${time}  ${message}`;
        panel.appendChild(div);
        panel.scrollTop = panel.scrollHeight;
    },

    /**
     * 清空日志
     */
    clearLogs: function() {
        const panel = document.getElementById('logPanel');
        if (panel) {
            panel.innerHTML = '';
        }
    },

    /**
     * 获取服务运行状态
     */
    isServerRunning: function() {
        return AppState.serverRunning;
    }
};

export default TabService;
