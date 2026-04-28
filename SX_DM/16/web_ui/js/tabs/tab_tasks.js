/**
 * 任务控制台模块 (tab_tasks.js)
 * ==============================
 * 负责 page-dreamina 的所有 UI 交互和状态同步
 * 通过 EventBus 订阅/发布事件，不直接操作 pyBridge
 *
 * 【数据流】
 * Python 后端 -> api.js (接收信号) -> EventBus.emit (广播)
 * -> TabTasks (监听并更新 UI) -> AppState (更新状态)
 */

const TabTasks = {
    _initialized: false,

    // ============ 本地状态（与 AppState 同步） ============
    _state: {
        type: 'AI Video',
        model: 'Dreamina Seedance 2.0 Fast',
        mode: 'first-last',
        aspect: '16:9',
        resolution: '720P',
        duration: '10s',
        intensity: 70,
        prompt: '',
        files: [],
        presets: []
    },

    // ============ @ 提及相关状态 ============
    _mentionState: {
        active: false,
        searchText: '',
        startOffset: 0,
        selectedIndex: 0,
        items: []
    },

    // ============ 素材管理常量 ============
    MAX_IMAGES: 12,
    MAX_VIDEOS: 3,
    MAX_AUDIOS: 3,
    MAX_TOTAL: 12,
    MAX_VIDEO_DURATION: 15,
    MAX_AUDIO_DURATION: 15,

    STACK_ANGLES: ['-rotate-12', 'rotate-12', '-rotate-8', 'rotate-8', '-rotate-4', 'rotate-4'],

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

        // 同步状态到 AppState
        this._syncStateToAppState();

        console.log('[tab_tasks.js] 模块初始化完成');
    },

    /**
     * 同步本地状态到 AppState
     */
    _syncStateToAppState: function() {
        Object.keys(this._state).forEach(key => {
            if (AppState.hasOwnProperty(key)) {
                AppState[key] = this._state[key];
            }
        });
    },

    /**
     * 绑定 UI 交互事件
     */
    _bindEvents: function() {
        // ============ ⚠️ 下拉菜单事件已被移除 ⚠️ ============
        // 这里的 addEventListener 已删除，因为 index.html 中已经有了 onclick="..."
        // 避免重复触发导致"瞬间打开又关闭"的问题。

        // ============ 强度滑块 ============
        const intensitySlider = document.getElementById('intensity-slider');
        if (intensitySlider) {
            intensitySlider.addEventListener('input', (e) => this._onIntensityChange(e));
        }

        // ============ Prompt 输入框 ============
        const promptEl = document.getElementById('dreaminaPrompt');
        if (promptEl) {
            promptEl.addEventListener('input', (e) => this._onPromptInput(e));
            promptEl.addEventListener('keydown', (e) => this._onPromptKeydown(e));
            promptEl.addEventListener('focus', () => this._onPromptFocus());
            promptEl.addEventListener('dragover', (e) => this._onPromptDragover(e));
            promptEl.addEventListener('drop', (e) => this._onPromptDrop(e));
        }

        // ============ 工具栏按钮 ============
        document.querySelectorAll('.tag-btn[data-group]').forEach(btn => {
            btn.addEventListener('click', () => {
                const group = btn.dataset.group;
                document.querySelectorAll(`.tag-btn[data-group="${group}"]`).forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                this._state[group] = btn.dataset.value;
                AppState[group] = btn.dataset.value;
            });
        });

        // ============ 生成按钮 ============
        const generateBtn = document.getElementById('generateBtn');
        if (generateBtn) {
            generateBtn.addEventListener('click', () => this.handleGenerate());
        }

        // ============ 查看器关闭 ============
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                this.closeViewer();
            }
        });

        // ============ 通用下拉关闭逻辑 ============
        document.addEventListener('click', (e) => {
            const containers = [
                { id: 'video-selector-container', menu: 'videoDropdown' },
                { id: 'model-selector-container', menu: 'model-dropdown-menu' },
                { id: 'omni-selector-container', menu: 'omni-dropdown-menu' },
                { id: 'ratio-selector-container', menu: 'ratio-dropdown-menu' },
                { id: 'duration-selector-container', menu: 'duration-dropdown-menu' }
            ];

            containers.forEach(({ id, menu }) => {
                if (!e.target.closest('#' + id)) {
                    const menuEl = document.getElementById(menu);
                    if (menuEl) {
                        menuEl.classList.add('hidden');
                        menuEl.classList.remove('block');
                    }
                }
            });
        });

        console.log('[tab_tasks.js] UI 事件已绑定');
    },

    /**
     * 订阅 EventBus 事件
     */
    _subscribeEvents: function() {
        // 任务进度更新
        EventBus.on('progress:any', (data) => {
            console.log('[TabTasks] 收到任务进度', data);
            this._updateTaskProgress(data.taskId, data.percent, data.message);
        });

        // 任务完成
        EventBus.on('result:default', (data) => {
            console.log('[TabTasks] 收到任务结果', data);
            this._onTaskComplete(data.taskId, data.result);
        });

        // 任务错误
        EventBus.on('error:any', (data) => {
            console.error('[TabTasks] 收到任务错误', data);
            this._onTaskError(data.taskId, data.error);
        });

        // 文件列表更新（由 Python 推送的素材列表）
        EventBus.on('files:listUpdated', (files) => {
            console.log('[TabTasks] 收到文件列表更新', files);
            AppState.setUploadedFiles(files);
            this._renderPreviews();
        });

        // 文件更新消息
        EventBus.on('files:updated', (data) => {
            console.log('[TabTasks] 收到文件更新', data);
            if (data.files) {
                AppState.setUploadedFiles(data.files);
                this._renderPreviews();
            }
        });

        // 编辑区拖拽完成（在光标位置插入标签）
        EventBus.on('editor:dropped', (data) => {
            console.log('[TabTasks] 收到编辑区拖拽事件', data);
            if (data.files && data.files.length > 0) {
                // 调用插入标签函数，在 drop 位置插入标签
                this._insertRefTagsAtCursor(data.files, data.drop_pos);
            }
        });

        console.log('[tab_tasks.js] EventBus 事件已订阅');
    },

    // ============================================================
    // 下拉菜单控制方法
    // ============================================================

    /**
     * 切换下拉菜单
     */
    _toggleDropdown: function(dropdownId, event) {
        if (event) event.stopPropagation();
        const dropdown = document.getElementById(dropdownId);
        if (!dropdown) return;

        const isHidden = dropdown.classList.contains('hidden');
        this._closeAllDropdowns();
        if (isHidden) {
            dropdown.classList.remove('hidden');
            dropdown.classList.add('block');
        }
    },

    /**
     * 关闭所有下拉菜单
     */
    _closeAllDropdowns: function() {
        const dropdowns = ['videoDropdown', 'model-dropdown-menu', 'omni-dropdown-menu', 'ratio-dropdown-menu', 'duration-dropdown-menu'];
        dropdowns.forEach(id => {
            const dropdown = document.getElementById(id);
            if (dropdown) {
                dropdown.classList.add('hidden');
                dropdown.classList.remove('block');
            }
        });
    },

    /**
     * 选择视频类型
     */
    selectVideo: function(type, element) {
        this._state.type = type;
        AppState.type = type;

        const btn = document.getElementById('aiVideoBtn');
        if (btn) {
            btn.innerHTML = `
                <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><path d="M10 8l6 4-6 4V8z"/></svg>
                ${type}
                <svg class="w-3 h-3" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M19 9l-7 7-7-7"/></svg>
            `;
        }
        this._closeAllDropdowns();

        if (element) {
            const menu = document.getElementById('videoDropdown');
            if (menu) {
                menu.querySelectorAll('.rounded-xl').forEach(el => {
                    el.classList.remove('bg-[#2a2a2d]');
                    el.classList.add('bg-transparent');
                });
                const parent = element.closest('.rounded-xl');
                if (parent) {
                    parent.classList.remove('bg-transparent');
                    parent.classList.add('bg-[#2a2a2d]');
                }
            }
        }
    },

    /**
     * 选择模型
     */
    selectModel: function(model, element) {
        this._state.model = model;
        AppState.model = model;

        const btn = document.getElementById('model-dropdown-btn');
        if (btn) {
            btn.innerHTML = `
                <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4"/>
                </svg>
                ${model} <span class="text-[#00cae0]">✦</span>
            `;
        }
        this._closeAllDropdowns();

        // 控制画质选项的显示与隐藏
        const resSection = document.getElementById('resolution-section');
        if (resSection) {
            if (model === 'Dreamina Seedance 2.0') {
                resSection.classList.remove('hidden');
            } else {
                resSection.classList.add('hidden');
            }
        }
        this._updateRatioButtonUI();

        if (element) {
            const menu = document.getElementById('model-dropdown-menu');
            if (menu) {
                menu.querySelectorAll('.rounded-xl').forEach(el => {
                    el.classList.remove('bg-[#2a2a2d]');
                    el.classList.add('bg-transparent');
                });
                const parent = element.closest('.rounded-xl');
                if (parent) {
                    parent.classList.remove('bg-transparent');
                    parent.classList.add('bg-[#2a2a2d]');
                }
            }
        }
    },

    /**
     * 选择画质
     */
    selectResolution: function(res, element) {
        this._state.resolution = res;
        AppState.resolution = res;

        if (element) {
            const container = element.closest('.flex-row');
            if (container) {
                container.querySelectorAll('.res-option').forEach(el => {
                    el.classList.remove('bg-[#38383a]', 'text-gray-200', 'shadow-sm');
                    el.classList.add('bg-transparent', 'text-gray-400');
                });
            }
            element.classList.remove('bg-transparent', 'text-gray-400');
            element.classList.add('bg-[#38383a]', 'text-gray-200', 'shadow-sm');
        }

        this._updateRatioButtonUI();
    },

    /**
     * 选择比例
     */
    selectRatio: function(ratio, element) {
        this._state.aspect = ratio;
        AppState.aspect = ratio;
        this._updateRatioButtonUI();
        this._closeAllDropdowns();

        if (element) {
            const container = element.closest('.bg-\\[\\#262629\\]');
            if (container) {
                container.querySelectorAll('.rounded-lg').forEach(el => {
                    el.classList.remove('bg-[#38383a]', 'text-gray-200', 'shadow-sm');
                    el.classList.add('text-gray-400');
                });
            }
            element.classList.remove('text-gray-400');
            element.classList.add('bg-[#38383a]', 'text-gray-200', 'shadow-sm');
        }
    },

    /**
     * 选择时长
     */
    selectDuration: function(duration, element) {
        this._state.duration = duration;
        AppState.duration = duration;

        const btn = document.getElementById('duration-dropdown-btn');
        if (btn) {
            btn.innerHTML = `
                <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <circle cx="12" cy="12" r="9" stroke-width="1.5"/>
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M12 7v5l3 3"/>
                </svg>
                ${duration}
            `;
        }
        this._closeAllDropdowns();

        const menu = document.getElementById('duration-dropdown-menu');
        if (menu) {
            menu.querySelectorAll('.rounded-xl').forEach(el => {
                el.classList.remove('bg-[#2a2a2d]');
                el.classList.add('hover:bg-[#323235]');
                const check = el.querySelector('.check-icon');
                if (check) check.remove();
            });
        }

        if (element) {
            element.classList.remove('hover:bg-[#323235]');
            element.classList.add('bg-[#2a2a2d]');
            const checkSvg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
            checkSvg.setAttribute('class', 'w-4 h-4 text-white check-icon');
            checkSvg.setAttribute('fill', 'none');
            checkSvg.setAttribute('stroke', 'currentColor');
            checkSvg.setAttribute('viewBox', '0 0 24 24');
            checkSvg.innerHTML = '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M5 13l4 4L19 7"></path>';
            element.appendChild(checkSvg);
        }
    },

    /**
     * 更新比例/画质按钮的显示文本
     */
    _updateRatioButtonUI: function() {
        const btnEl = document.getElementById('ratio-dropdown-btn');
        if (!btnEl) return;

        const isStandardModel = this._state.model === 'Dreamina Seedance 2.0';
        let btnText = this._state.aspect;
        if (isStandardModel) {
            btnText += `&nbsp;&nbsp;&nbsp;${this._state.resolution}`;
        }

        btnEl.innerHTML = `
            <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <rect x="3" y="6" width="18" height="12" rx="1.5" stroke-width="1.5"/>
            </svg>
            ${btnText}
        `;
    },

    // ============================================================
    // 强度滑块
    // ============================================================

    _onIntensityChange: function(e) {
        const value = parseInt(e.target.value);
        this._state.intensity = value;
        AppState.intensity = value;

        // 更新数字显示
        const valueDisplay = document.getElementById('intensity-value');
        if (valueDisplay) {
            valueDisplay.textContent = value;
        }

        // 更新滑块背景填充
        const percent = value + '%';
        e.target.style.setProperty('--value', percent);
        e.target.style.background = `linear-gradient(to right, rgb(0, 202, 224) 0%, rgb(0, 202, 224) ${percent}, #3a3a3c ${percent}, #3a3a3c 100%)`;
    },

    // ============================================================
    // Prompt 输入框
    // ============================================================

    _onPromptInput: function(e) {
        this._state.prompt = e.target.textContent;
        AppState.prompt = e.target.textContent;

        // 检测 @ 提及
        const selection = window.getSelection();
        if (!selection.rangeCount) {
            this._hideMentionDropdown();
            return;
        }

        const range = selection.getRangeAt(0);
        const node = range.endContainer;

        if (node.nodeType !== Node.TEXT_NODE) {
            this._hideMentionDropdown();
            return;
        }

        const text = node.textContent || '';
        const localOffset = range.endOffset;
        const globalOffset = this._getTextOffset(e.target, node) + localOffset;

        // 查找最后一个 @ 符号
        let atLocalIndex = -1;
        for (let i = localOffset - 1; i >= 0; i--) {
            if (text[i] === '@') {
                atLocalIndex = i;
                break;
            }
            if (text[i] === ' ' || text[i] === '\n') {
                break;
            }
        }

        if (atLocalIndex >= 0) {
            const afterAt = text.substring(atLocalIndex + 1, localOffset);
            if (!afterAt.includes(' ')) {
                const atGlobalOffset = this._getTextOffset(e.target, node) + atLocalIndex;
                this._mentionState.active = true;
                this._mentionState.startOffset = atGlobalOffset;
                this._mentionState.searchText = afterAt;
                this._mentionState.selectedIndex = -1;
                this._renderMentionDropdown();
                return;
            }
        }

        this._hideMentionDropdown();
    },

    _onPromptKeydown: function(e) {
        const dropdown = document.getElementById('mentionDropdown');

        // @ 提及导航
        if (this._mentionState.active && dropdown?.style.display !== 'none') {
            if (e.key === 'ArrowDown') {
                e.preventDefault();
                e.stopPropagation();
                this._mentionState.selectedIndex = (this._mentionState.selectedIndex + 1) % this._mentionState.items.length;
                this._renderMentionDropdown();
                return;
            }
            if (e.key === 'ArrowUp') {
                e.preventDefault();
                e.stopPropagation();
                this._mentionState.selectedIndex = (this._mentionState.selectedIndex - 1 + this._mentionState.items.length) % this._mentionState.items.length;
                this._renderMentionDropdown();
                return;
            }
            if (e.key === 'Enter' || e.key === 'Tab') {
                e.preventDefault();
                e.stopPropagation();
                this._selectMentionItem(this._mentionState.selectedIndex);
                return;
            }
            if (e.key === 'Escape') {
                e.preventDefault();
                e.stopPropagation();
                this._hideMentionDropdown();
                return;
            }
        }

        // 阻止换行
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
        }

        // 退格键删除标签
        if (e.key === 'Backspace') {
            const selection = window.getSelection();
            if (!selection.rangeCount) return;
            const range = selection.getRangeAt(0);
            const node = range.endContainer;

            if (this._mentionState.active) {
                const text = node.textContent || '';
                const offset = range.endOffset;
                const afterAt = text.substring(this._mentionState.startOffset + 1, offset);
                if (afterAt.length <= 1) {
                    this._hideMentionDropdown();
                }
                return;
            }

            if (node.nodeType === Node.TEXT_NODE) {
                const parent = node.parentElement;
                if (parent && parent.classList.contains('ref-tag')) {
                    e.preventDefault();
                    const idx = parseInt(parent.dataset.index);
                    if (!isNaN(idx)) {
                        this._removeFile(idx);
                    }
                    parent.remove();
                } else if (node.textContent === '' && parent && parent.classList.contains('ref-tag')) {
                    e.preventDefault();
                    const idx = parseInt(parent.dataset.index);
                    if (!isNaN(idx)) {
                        this._removeFile(idx);
                    }
                    parent.remove();
                }
            }
        }
    },

    _onPromptFocus: function() {
        if (!window.getSelection().rangeCount) {
            const editor = document.getElementById('dreaminaPrompt');
            if (editor) {
                const range = document.createRange();
                range.selectNodeContents(editor);
                range.collapse(false);
                const sel = window.getSelection();
                sel.removeAllRanges();
                sel.addRange(range);
            }
        }
    },

    _onPromptDragover: function(e) {
        e.preventDefault();
        e.stopPropagation();

        // 检查鼠标是否在素材标签上
        const elementUnderMouse = document.elementFromPoint(e.clientX, e.clientY);
        if (elementUnderMouse && elementUnderMouse.closest('.ref-tag')) {
            // 在标签上，禁止放置
            e.dataTransfer.dropEffect = 'none';
        } else {
            // 在文字或空白处，允许放置
            e.dataTransfer.dropEffect = 'copy';
        }
    },

    _onPromptDrop: function(e) {
        e.preventDefault();
        e.stopPropagation();
        const files = e.dataTransfer?.files;
        if (files && files.length > 0) {
            const paths = [];
            for (let i = 0; i < files.length; i++) {
                paths.push(files[i].path || files[i].name);
            }
            // 获取 drop 位置（相对于浏览器视口）
            const dropPos = { x: e.clientX, y: e.clientY };
            
            if (window.pyBridge && window.pyBridge.on_editor_drop) {
                // 传递路径数组和 drop 位置
                const payload = JSON.stringify({ paths: paths, drop_pos: dropPos });
                window.pyBridge.on_editor_drop(payload);
            }
        }
    },

    // ============================================================
    // @ 提及相关
    // ============================================================

    _getTextOffset: function(root, targetNode) {
        let offset = 0;
        const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, null);
        while (walker.nextNode()) {
            if (walker.currentNode === targetNode) {
                return offset;
            }
            offset += walker.currentNode.textContent.length;
        }
        return offset;
    },

    _updateMentionDropdownPosition: function() {
        const dropdown = document.getElementById('mentionDropdown');
        if (!dropdown || !this._mentionState.active) return;

        const editor = document.getElementById('dreaminaPrompt');
        if (!editor) return;

        let atRect = null;
        const walker = document.createTreeWalker(editor, NodeFilter.SHOW_TEXT, null);
        let accumulatedOffset = 0;

        while (walker.nextNode()) {
            const node = walker.currentNode;
            const nodeText = node.textContent;
            const nodeLength = nodeText.length;

            if (accumulatedOffset + nodeLength > this._mentionState.startOffset) {
                const offsetInNode = this._mentionState.startOffset - accumulatedOffset;
                try {
                    const range = document.createRange();
                    range.setStart(node, offsetInNode);
                    range.setEnd(node, offsetInNode + 1);
                    const rects = range.getClientRects();
                    if (rects.length > 0) {
                        atRect = rects[0];
                    }
                } catch (e) {}
                break;
            }
            accumulatedOffset += nodeLength;
        }

        if (atRect) {
            dropdown.style.left = (atRect.left + window.scrollX) + 'px';
            dropdown.style.top = (atRect.bottom + 4 + window.scrollY) + 'px';
        } else {
            const selection = window.getSelection();
            if (selection.rangeCount > 0) {
                const range = selection.getRangeAt(0);
                const cursorRect = range.getBoundingClientRect();
                dropdown.style.left = (cursorRect.left + window.scrollX) + 'px';
                dropdown.style.top = (cursorRect.bottom + 4 + window.scrollY) + 'px';
            }
        }
    },

    _renderMentionDropdown: function() {
        const dropdown = document.getElementById('mentionDropdown');
        const list = document.getElementById('mentionList');
        const empty = document.getElementById('mentionEmpty');

        if (!dropdown || !list) return;

        const searchText = this._mentionState.searchText.toLowerCase();
        const uploadedFiles = AppState.uploadedFiles || [];

        this._mentionState.items = uploadedFiles.filter(file => {
            if (!searchText) return true;
            const name = (file.name || '').toLowerCase();
            return name.includes(searchText);
        });

        if (this._mentionState.items.length === 0) {
            list.innerHTML = '';
            empty?.classList.remove('hidden');
            dropdown.style.display = 'block';
            dropdown.classList.remove('hidden');
            dropdown.classList.add('block');
            this._mentionState.selectedIndex = -1;
            this._updateMentionDropdownPosition();
            return;
        }

        empty?.classList.add('hidden');

        const typeCounts = { image: 0, video: 0, audio: 0 };
        list.innerHTML = this._mentionState.items.map((file, idx) => {
            const type = file.type || 'file';
            typeCounts[type] = (typeCounts[type] || 0) + 1;
            const serialNum = typeCounts[type];
            const isSelected = idx === this._mentionState.selectedIndex;

            const thumbHtml = type === 'audio'
                ? '<svg width="18" height="18" fill="none" stroke="rgb(0, 202, 224)" stroke-width="2" viewBox="0 0 24 24"><path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/></svg>'
                : `<img src="${file.thumbnail_base64 || file.url || ''}" alt="">`;

            return `
                <div class="mention-item ${isSelected ? 'selected' : ''}" data-index="${idx}" onclick="TabTasks._selectMentionItem(${idx})">
                    <div class="mention-item-thumb">${thumbHtml}</div>
                    <span class="mention-item-badge ${type}">${type.charAt(0).toUpperCase() + type.slice(1)}${serialNum}</span>
                </div>
            `;
        }).join('');

        dropdown.style.display = 'block';
        dropdown.classList.remove('hidden');
        dropdown.classList.add('block');
        this._updateMentionDropdownPosition();
    },

    _hideMentionDropdown: function() {
        const dropdown = document.getElementById('mentionDropdown');
        if (dropdown) {
            dropdown.style.display = 'none';
            dropdown.classList.add('hidden');
            dropdown.classList.remove('block');
        }
        this._mentionState.active = false;
        this._mentionState.searchText = '';
        this._mentionState.items = [];
    },

    _selectMentionItem: function(idx) {
        if (idx < 0 || idx >= this._mentionState.items.length) return;

        const file = this._mentionState.items[idx];
        const editor = document.getElementById('dreaminaPrompt');
        if (!editor) return;

        // 【核心修复1】：不再依赖容易丢失焦点的 window.getSelection()
        // 而是通过全局文本偏移量来精准计算需要删除的 @ 及搜索词范围
        const startGlobalOffset = this._mentionState.startOffset;
        const endGlobalOffset = startGlobalOffset + 1 + this._mentionState.searchText.length;

        let atNode = null;
        let atNodeOffset = 0;
        let endNode = null;
        let endNodeOffset = 0;
        let accOffset = 0;

        const walker = document.createTreeWalker(editor, NodeFilter.SHOW_TEXT, null);

        while (walker.nextNode()) {
            const node = walker.currentNode;
            const nodeLen = node.textContent.length;

            // 寻找起始的 @ 节点
            if (!atNode && accOffset + nodeLen > startGlobalOffset) {
                atNode = node;
                atNodeOffset = startGlobalOffset - accOffset;
            }

            // 寻找搜索词结束的节点
            if (accOffset + nodeLen >= endGlobalOffset) {
                endNode = node;
                endNodeOffset = endGlobalOffset - accOffset;
                break;
            }
            accOffset += nodeLen;
        }

        // 防御性判断
        if (!atNode || !endNode) {
            this._hideMentionDropdown();
            return;
        }

        // 仅删除准确计算出来的 @ 和搜索词
        const deleteRange = document.createRange();
        deleteRange.setStart(atNode, atNodeOffset);
        deleteRange.setEnd(endNode, endNodeOffset);
        deleteRange.deleteContents();

        const type = file.type || 'file';
        const tag = document.createElement('span');
        tag.className = 'ref-tag ' + type;
        tag.contentEditable = 'false';
        tag.dataset.index = AppState.uploadedFiles.indexOf(file);
        tag.dataset.type = type;

        if (type === 'audio') {
            tag.innerHTML = '<svg width="16" height="16" fill="none" stroke="rgb(0, 202, 224)" stroke-width="2" viewBox="0 0 24 24"><path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/></svg>';
        } else {
            const thumbSrc = file.thumbnail_base64 || file.url || '';
            if (thumbSrc) {
                tag.innerHTML = '<img src="' + thumbSrc + '" alt="">';
            }
        }

        const nameSpan = document.createElement('span');
        nameSpan.className = 'ref-name';
        nameSpan.textContent = type.charAt(0).toUpperCase() + type.slice(1) + (AppState.uploadedFiles.indexOf(file) + 1);
        tag.appendChild(nameSpan);

        tag.addEventListener('click', function(e) {
            e.preventDefault();
            e.stopPropagation();
            const idx = parseInt(this.dataset.index);
            const t = this.dataset.type;
            if (t === 'image') {
                const f = AppState.uploadedFiles[idx];
                if (f) TabTasks.openViewer(f);
            } else {
                if (window.pyBridge && window.pyBridge.request_native_preview) {
                    window.pyBridge.request_native_preview(idx);
                }
            }
        });

        // 在删除了旧字符的位置插入新标签
        const insertRange = document.createRange();
        insertRange.setStart(atNode, atNodeOffset);
        insertRange.collapse(true);
        insertRange.insertNode(tag);

        // 【核心修复2】：在不可编辑的标签后插入一个零宽空格，防止光标丢失基线跑到左上角
        const spaceNode = document.createTextNode('\u200B');
        tag.parentNode.insertBefore(spaceNode, tag.nextSibling);

        editor.focus();
        const newSel = window.getSelection();
        const afterTagRange = document.createRange();

        // 将光标定位在零宽空格之后
        afterTagRange.setStartAfter(spaceNode);
        afterTagRange.collapse(true);
        newSel.removeAllRanges();
        newSel.addRange(afterTagRange);

        this._hideMentionDropdown();
        editor.dispatchEvent(new Event('input', { bubbles: true }));
    },

    // ============================================================
    // 生成任务
    // ============================================================

    handleGenerate: function() {
        if (!AppState.serverRunning) {
            EventBus.emit('toast', { message: '请先启动服务' });
            return;
        }

        const prompt = document.getElementById('dreaminaPrompt')?.textContent?.trim() || '';

        if (!prompt) {
            EventBus.emit('toast', { message: '请输入描述词' });
            return;
        }

        const params = {
            type: this._state.type,
            model: this._state.model,
            mode: this._state.mode,
            aspect: this._state.aspect,
            resolution: this._state.resolution,
            duration: this._state.duration,
            intensity: this._state.intensity,
            prompt: this._state.prompt,
            files: (AppState.uploadedFiles || []).map(f => ({ name: f.name, path: f.path, type: f.type }))
        };

        console.log('[TabTasks] 发起生成任务', params);
        AppState.addPendingTask('generate');
        API.call('generate_task', params);

        EventBus.emit('toast', { message: '生成请求已发送' });
        this._showGeneratingState();
    },

    _showGeneratingState: function() {
        const btn = document.getElementById('generateBtn');
        if (!btn) return;

        btn.disabled = true;
        btn.innerHTML = `
            <svg class="animate-spin" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <circle cx="12" cy="12" r="10" stroke-opacity="0.25"/>
                <path d="M12 2a10 10 0 0 1 10 10"/>
            </svg>
            生成中...
        `;
    },

    _resetGenerateButton: function() {
        const btn = document.getElementById('generateBtn');
        if (!btn) return;

        btn.disabled = false;
        btn.innerHTML = `
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z"/>
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/>
            </svg>
            Generate
        `;

        AppState.removePendingTask('generate');
    },

    _updateTaskProgress: function(taskId, percent, message) {
        console.log(`[TabTasks] 任务 ${taskId} 进度: ${percent}% - ${message}`);
    },

    _onTaskComplete: function(taskId, result) {
        console.log(`[TabTasks] 任务 ${taskId} 完成`, result);
        this._resetGenerateButton();

        if (result.success) {
            EventBus.emit('toast', { message: result.message || '生成成功' });
        } else {
            EventBus.emit('toast', { message: result.error || '生成失败' });
        }
    },

    _onTaskError: function(taskId, error) {
        console.error(`[TabTasks] 任务 ${taskId} 错误:`, error);
        this._resetGenerateButton();
        EventBus.emit('toast', { message: `错误: ${error}` });
    },

    // ============================================================
    // 素材预览卡片
    // ============================================================

    _renderPreviews: function() {
        const container = document.getElementById('reference-preview-container');
        if (!container) return;

        const uploadedFiles = AppState.uploadedFiles || [];

        if (uploadedFiles.length === 0) {
            container.innerHTML = `
                <div class="placeholder-card absolute inset-0 bg-[#2a2a2d] rounded-lg transform -rotate-3 flex flex-col items-center justify-center text-gray-500 text-[11px] group-hover:bg-[#323235] group-hover:scale-105 transition-all duration-200 border border-dashed border-gray-600/50">
                    <svg class="w-4 h-4 mb-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4"></path>
                    </svg>
                    <span>Referenc</span>
                </div>
            `;
            return;
        }

        container.innerHTML = '';
        const totalCount = uploadedFiles.length;

        let imgCount = 0, vidCount = 0, audCount = 0;

        try {
            uploadedFiles.forEach((file, index) => {
                try {
                    const isTopCard = index === totalCount - 1;
                    const angleClass = isTopCard ? 'rotate-0' : this.STACK_ANGLES[index % this.STACK_ANGLES.length];
                    const zIndex = 10 + index;

                    const expandX = index * 80;
                    const expandRot = (index % 2 === 0 ? '-2deg' : '2deg');

                    let cardContent = '';
                    let bgClass = 'bg-[#1c1c1e]';
                    let typeLabel = '';
                    const fileType = file.type || 'unknown';

                    if (fileType === 'image') {
                        imgCount++;
                        typeLabel = 'Image' + imgCount;
                        const imgSrc = file.thumbnail_base64 || file.path || file.url || '';
                        cardContent = '<img src="' + imgSrc + '" class="w-full h-full object-cover rounded-md" />';
                    } else if (fileType === 'video') {
                        vidCount++;
                        typeLabel = 'Video' + vidCount;
                        const imgSrc = file.thumbnail_base64 || '';
                        cardContent = '<img src="' + imgSrc + '" class="w-full h-full object-cover rounded-md" />' +
                            '<div class="absolute bottom-1 left-1 bg-black/60 px-1 rounded text-white text-[8px] font-bold">' + (file.duration || '00:00') + '</div>';
                    } else if (fileType === 'audio') {
                        audCount++;
                        typeLabel = 'Audio' + audCount;
                        bgClass = 'bg-[#5a6b82]';
                        cardContent = '<div class="flex flex-col items-center justify-center h-full w-full">' +
                            '<svg class="w-6 h-6 text-white mb-1" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 19V6l12-3v13M9 19c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zm12-3c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zM9 10l12-3"/></svg>' +
                            '<span class="text-white text-[10px] font-medium leading-none">' + typeLabel + '</span>' +
                            '</div>';
                    } else {
                        typeLabel = 'File';
                        bgClass = 'bg-[#3a3a3a]';
                        cardContent = '<div class="flex flex-col items-center justify-center h-full w-full">' +
                            '<svg class="w-6 h-6 text-gray-400 mb-1" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z"/></svg>' +
                            '<span class="text-gray-400 text-[10px] font-medium leading-none">' + typeLabel + '</span>' +
                            '</div>';
                    }

                    const cardHtml = '<div class="preview-card group absolute inset-0 ' + bgClass + ' rounded-lg border-2 border-white shadow-lg transform ' + angleClass + ' cursor-pointer" ' +
                        'style="z-index: ' + zIndex + '; --expand-x: ' + expandX + 'px; --expand-rot: ' + expandRot + ';" ' +
                        'onclick="event.stopPropagation(); window.pyBridge.request_native_preview(' + index + ');">' +

                        '<div class="absolute -top-8 left-1/2 transform -translate-x-1/2 bg-[#2a2a2d] border border-[#3c3c3e] text-gray-200 text-[10px] px-2 py-0.5 rounded opacity-0 group-hover:opacity-100 transition-opacity whitespace-nowrap shadow-lg pointer-events-none z-50">' +
                        typeLabel +
                        '</div>' +

                        '<div onclick="event.stopPropagation(); TabTasks._removeFile(' + index + ');" ' +
                        'class="absolute -top-1.5 -right-1.5 w-4 h-4 bg-[#1c1c1e] border border-gray-500 rounded-full flex items-center justify-center text-gray-300 opacity-0 group-hover:opacity-100 hover:bg-red-500 hover:text-white hover:border-red-500 transition-all z-50" title="Remove">' +
                        '<svg class="w-2.5 h-2.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M6 18L18 6M6 6l12 12"></path></svg>' +
                        '</div>' +

                        cardContent +

                        (isTopCard && totalCount < this.MAX_TOTAL ?
                            '<div onclick="event.stopPropagation(); window.pyBridge.open_file_dialog();" ' +
                            'class="absolute -bottom-2 -right-2 w-7 h-7 bg-[#38383a] border-[3px] border-[#1c1c1e] rounded-full flex items-center justify-center text-white shadow-xl hover:bg-[#48484a] transition-colors cursor-pointer z-50" title="Add more">' +
                            '<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M12 4v16m8-8H4"></path></svg>' +
                            '</div>' : '') +
                        '</div>';

                    container.insertAdjacentHTML('beforeend', cardHtml);
                } catch (err) {
                    console.error('[TabTasks] 渲染单个卡片失败:', index, err);
                }
            });
        } catch (err) {
            console.error('[TabTasks] 渲染卡片列表失败:', err);
        }

        // 重新应用拖拽状态
        var dropzone = document.getElementById('reference-dropzone');
        if (dropzone && window.__isDragging) {
            dropzone.classList.add('drag-active');
        }
    },

    _removeFile: function(index) {
        console.log('[TabTasks] 请求删除文件: index=', index);

        // 在删除前获取被删除文件的信息（用于同步编辑区标签）
        const uploadedFiles = window.AppState ? window.AppState.uploadedFiles : [];
        const deletedFileInfo = uploadedFiles[index] || { index: index };

        if (window.pyBridge && window.pyBridge.remove_file) {
            window.pyBridge.remove_file(index);
        } else {
            console.error('[TabTasks] pyBridge.remove_file 不可用');
            return;
        }

        // 触发编辑区标签同步事件
        if (window.EventBus) {
            window.EventBus.emit('file:removed', deletedFileInfo);
            console.log('[TabTasks] 已触发 file:removed 事件', deletedFileInfo);
        }
    },

    // ============================================================
    // 查看器
    // ============================================================

    openViewer: function(file) {
        const overlay = document.getElementById('viewerOverlay');
        const imgEl = document.getElementById('viewerImage');
        const videoEl = document.getElementById('viewerVideo');
        const audioEl = document.getElementById('viewerAudio');
        const infoEl = document.getElementById('viewerInfo');

        if (!overlay) return;

        videoEl.pause();
        videoEl.style.display = 'none';
        audioEl.pause();
        audioEl.style.display = 'none';
        imgEl.style.display = 'none';

        const type = file.type || 'image';
        const src = file.thumbnail_base64 || file.path || file.url || '';

        if (type === 'video' && file.path) {
            videoEl.src = file.path;
            videoEl.style.display = 'block';
            infoEl.textContent = (file.name || 'Video') + (file.duration ? ' · ' + file.duration : '');
        } else if (type === 'audio' && file.path) {
            audioEl.src = file.path;
            audioEl.style.display = 'block';
            infoEl.textContent = (file.name || 'Audio') + (file.duration ? ' · ' + file.duration : '');
        } else if (src) {
            imgEl.src = src;
            imgEl.style.display = 'block';
            infoEl.textContent = file.name || 'Image';
        } else {
            return;
        }

        overlay.classList.add('show');
    },

    closeViewer: function(e) {
        if (e && e.target !== e.currentTarget) return;
        const overlay = document.getElementById('viewerOverlay');
        if (overlay) {
            overlay.classList.remove('show');
        }
        const videoEl = document.getElementById('viewerVideo');
        const audioEl = document.getElementById('viewerAudio');
        if (videoEl) videoEl.pause();
        if (audioEl) audioEl.pause();
    },

    // ============================================================
    // 素材标签插入
    // ============================================================

    _insertRefTag: function(file, index, atCursor = false) {
        const editor = document.getElementById('dreaminaPrompt');
        if (!editor) return;

        const type = file.type || 'file';
        const uploadedFiles = AppState.uploadedFiles || [];

        let typeCount = 1;
        for (let i = 0; i < uploadedFiles.length; i++) {
            if (i >= index) break;
            if (uploadedFiles[i].type === type) typeCount++;
        }

        const tag = document.createElement('span');
        tag.className = 'ref-tag ' + type;
        tag.contentEditable = 'false';
        tag.dataset.index = index;
        tag.dataset.type = type;

        if (type === 'audio') {
            tag.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="rgb(0, 202, 224)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/></svg>';
        } else {
            const thumbSrc = file.thumbnail_base64 || file.url || '';
            if (thumbSrc) {
                tag.innerHTML = '<img src="' + thumbSrc + '" alt="">';
            }
        }

        const nameSpan = document.createElement('span');
        nameSpan.className = 'ref-name';
        nameSpan.textContent = type.charAt(0).toUpperCase() + type.slice(1) + typeCount;
        tag.appendChild(nameSpan);

        tag.addEventListener('click', function(e) {
            e.preventDefault();
            e.stopPropagation();
            const idx = parseInt(this.dataset.index);
            const t = this.dataset.type;
            if (t === 'image') {
                const f = AppState.uploadedFiles[idx];
                if (f) TabTasks.openViewer(f);
            } else {
                if (window.pyBridge && window.pyBridge.request_native_preview) {
                    window.pyBridge.request_native_preview(idx);
                }
            }
        });

        if (atCursor && window.getSelection) {
            const sel = window.getSelection();
            if (sel.rangeCount > 0) {
                const range = sel.getRangeAt(0);
                if (editor.contains(range.startContainer) || editor === range.startContainer) {
                    range.deleteContents();
                    range.insertNode(tag);
                    range.setStartAfter(tag);
                    range.collapse(true);
                    sel.removeAllRanges();
                    sel.addRange(range);
                } else {
                    editor.appendChild(tag);
                }
            } else {
                editor.appendChild(tag);
            }
        } else {
            if (window.getSelection) {
                const sel = window.getSelection();
                if (sel.rangeCount > 0) {
                    sel.collapse(editor, editor.childNodes.length);
                }
            }
            editor.appendChild(tag);
        }

        editor.dispatchEvent(new Event('input', { bubbles: true }));
    },

    _ensureCursorOutsideTags: function(editor, cursorRange) {
        if (!cursorRange) return cursorRange;

        const container = cursorRange.startContainer;
        let tagAncestor = null;
        let currentNode = container;

        while (currentNode && currentNode !== editor) {
            if (currentNode.classList && currentNode.classList.contains('ref-tag')) {
                tagAncestor = currentNode;
                break;
            }
            currentNode = currentNode.parentNode;
        }

        if (tagAncestor) {
            const newRange = document.createRange();
            newRange.setStartAfter(tagAncestor);
            newRange.collapse(true);
            console.log('[TabTasks] 光标在标签内，已移到标签之后');
            return newRange;
        }

        return cursorRange;
    },

    _insertRefTagsAtCursor: function(files, dropPos) {
        if (!files || files.length === 0) return;

        const editor = document.getElementById('dreaminaPrompt');
        if (!editor) return;

        editor.focus();

        let cursorRange = null;
        if (dropPos && dropPos.x !== undefined && dropPos.y !== undefined) {
            if (document.caretRangeFromPoint) {
                cursorRange = document.caretRangeFromPoint(dropPos.x, dropPos.y);
            } else if (document.caretPositionFromPoint) {
                const pos = document.caretPositionFromPoint(dropPos.x, dropPos.y);
                if (pos) {
                    cursorRange = document.createRange();
                    cursorRange.setStart(pos.offsetNode, pos.offset);
                    cursorRange.collapse(true);
                }
            }

            if (cursorRange) {
                if (!editor.contains(cursorRange.startContainer) && editor !== cursorRange.startContainer) {
                    cursorRange = document.createRange();
                    cursorRange.selectNodeContents(editor);
                    cursorRange.collapse(false);
                }
            }
        }

        if (cursorRange) {
            cursorRange = this._ensureCursorOutsideTags(editor, cursorRange);
        }

        if (!cursorRange) {
            cursorRange = document.createRange();
            cursorRange.selectNodeContents(editor);
            cursorRange.collapse(false);
        }

        const selection = window.getSelection();
        selection.removeAllRanges();
        selection.addRange(cursorRange);

        const uploadedFiles = AppState.uploadedFiles || [];

        for (let i = 0; i < files.length; i++) {
            const file = files[i];
            const index = file.insert_index !== undefined ? file.insert_index : uploadedFiles.length;

            const tag = document.createElement('span');
            tag.className = 'ref-tag ' + (file.type || 'file');
            tag.contentEditable = 'false';
            tag.dataset.index = index;
            tag.dataset.type = file.type || 'file';
            tag.dataset.path = file.path || '';      // 用于删除时匹配
            tag.dataset.name = file.name || '';     // 用于删除时匹配
            tag.dataset.url = file.url || '';       // 用于删除时匹配

            const type = file.type || 'file';
            if (type === 'audio') {
                tag.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="rgb(0, 202, 224)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/></svg>';
            } else {
                const thumbSrc = file.thumbnail_base64 || file.url || '';
                if (thumbSrc) {
                    tag.innerHTML = '<img src="' + thumbSrc + '" alt="">';
                }
            }

            let typeCount = 1;
            for (let j = 0; j < uploadedFiles.length; j++) {
                if (j >= index) break;
                if (uploadedFiles[j].type === type) typeCount++;
            }

            const nameSpan = document.createElement('span');
            nameSpan.className = 'ref-name';
            nameSpan.textContent = type.charAt(0).toUpperCase() + type.slice(1) + typeCount;
            tag.appendChild(nameSpan);

            tag.addEventListener('click', function(e) {
                e.preventDefault();
                e.stopPropagation();
                const idx = parseInt(this.dataset.index);
                const t = this.dataset.type;
                if (t === 'image') {
                    const f = AppState.uploadedFiles[idx];
                    if (f) TabTasks.openViewer(f);
                } else {
                    if (window.pyBridge && window.pyBridge.request_native_preview) {
                        window.pyBridge.request_native_preview(idx);
                    }
                }
            });

            const currentRange = selection.getRangeAt(0);
            currentRange.deleteContents();
            currentRange.insertNode(tag);
            currentRange.setStartAfter(tag);
            currentRange.collapse(true);
            selection.removeAllRanges();
            selection.addRange(currentRange);
        }

        editor.dispatchEvent(new Event('input', { bubbles: true }));
        console.log('[TabTasks] 已插入', files.length, '个标签到光标位置 (dropPos:', dropPos, ')');
    }
};

// ============================================================
// 挂载到 window 以便 HTML onclick 调用
// ============================================================
window.TabTasks = TabTasks;

// 兼容 HTML 中的全局函数（移除无效的全局 event 传参）
window.toggleVideoDropdown = function() {
    TabTasks._toggleDropdown('videoDropdown');
};
window.selectVideo = function(type, el) {
    TabTasks.selectVideo(type, el);
};
window.toggleModelDropdown = function() {
    TabTasks._toggleDropdown('model-dropdown-menu');
};
window.selectModel = function(model, el) {
    TabTasks.selectModel(model, el);
};
window.toggleOmniDropdown = function() {
    TabTasks._toggleDropdown('omni-dropdown-menu');
};
window.toggleRatioDropdown = function() {
    TabTasks._toggleDropdown('ratio-dropdown-menu');
};
window.selectRatio = function(ratio, el) {
    TabTasks.selectRatio(ratio, el);
};
window.selectResolution = function(res, el) {
    TabTasks.selectResolution(res, el);
};
window.toggleDurationDropdown = function() {
    TabTasks._toggleDropdown('duration-dropdown-menu');
};
window.selectDuration = function(duration, el) {
    TabTasks.selectDuration(duration, el);
};
window.selectMentionItem = function(idx) {
    TabTasks._selectMentionItem(idx);
};
window.removeFile = function(idx) {
    TabTasks._removeFile(idx);
};
window.openViewer = function(file) {
    TabTasks.openViewer(file);
};
window.closeViewer = function(e) {
    TabTasks.closeViewer(e);
};

export default TabTasks;
