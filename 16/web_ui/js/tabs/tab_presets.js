/**
 * 预设管理模块 (tab_presets.js)
 * ==============================
 * 负责 page-presets 的所有 UI 交互和状态同步
 * 通过 EventBus 订阅/发布事件，不直接操作 pyBridge
 */

/**
 * 渲染预设列表到 DOM
 * @param {Array} presets - 预设数据数组
 */
function renderPresets(presets) {
    const list = document.getElementById('presetsList');
    if (!list) return;

    if (!presets || presets.length === 0) {
        list.innerHTML = `
            <div style="text-align: center; padding: 40px 20px; color: #6e7681;">
                <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" style="opacity: 0.5; margin-bottom: 16px;">
                    <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
                </svg>
                <p>暂无预设</p>
                <p style="font-size: 12px; margin-top: 8px;">点击上方按钮创建新预设</p>
            </div>
        `;
        return;
    }

    list.innerHTML = presets.map(p => `
        <div class="preset-card" data-id="${p.id}">
            <div class="preset-name">${p.name}</div>
            <div class="preset-meta">${p.settings?.type || '通用'} · ${p.created || '未知时间'}</div>
            <div class="preset-actions">
                <button class="action-btn primary apply-preset-btn" data-id="${p.id}">应用</button>
                <button class="action-btn danger delete-preset-btn" data-id="${p.id}">删除</button>
            </div>
        </div>
    `).join('');
}

/**
 * 初始化预设管理模块
 */
function initPresets() {
    // 绑定新建预设按钮
    const createBtn = document.querySelector('[data-action="create-preset"]');
    if (createBtn) {
        createBtn.addEventListener('click', createPreset);
    }

    // 预设列表区域（事件委托）
    const list = document.getElementById('presetsList');
    if (list) {
        list.addEventListener('click', (e) => {
            const applyBtn = e.target.closest('.apply-preset-btn');
            if (applyBtn) {
                const id = applyBtn.dataset.id;
                applyPreset(id);
                return;
            }

            const deleteBtn = e.target.closest('.delete-preset-btn');
            if (deleteBtn) {
                const id = deleteBtn.dataset.id;
                deletePreset(id);
                return;
            }
        });
    }

    // 订阅 EventBus 事件
    EventBus.on('presets:loaded', (result) => {
        console.log('[TabPresets] 收到 presets:loaded', result);
        if (result.success && result.presets) {
            AppState.setPresets(result.presets);
            renderPresets(result.presets);
        }
    });

    EventBus.on('preset:created', (result) => {
        console.log('[TabPresets] 收到 preset:created', result);
        if (result.success) {
            window.showToast('预设创建成功');
            loadPresets();
        } else {
            window.showToast('预设创建失败');
        }
    });

    EventBus.on('preset:applied', (result) => {
        console.log('[TabPresets] 收到 preset:applied', result);
        if (result.success && result.preset) {
            window.showToast(`已应用预设: ${result.preset.name}`);
            const editor = document.getElementById('dreaminaPrompt');
            if (result.preset.textContent && editor) {
                editor.textContent = result.preset.textContent;
                if (typeof state !== 'undefined') {
                    state.prompt = result.preset.textContent;
                }
            }
        }
    });

    EventBus.on('preset:deleted', (result) => {
        console.log('[TabPresets] 收到 preset:deleted', result);
        if (result.success) {
            window.showToast('预设已删除');
            loadPresets();
        }
    });

    // 首次初始化时加载预设列表
    loadPresets();

    console.log('[tab_presets.js] 模块初始化完成');
}

/**
 * 加载预设列表
 */
function loadPresets() {
    API.call('get_presets', {});
}

/**
 * 创建新预设
 */
function createPreset() {
    const name = prompt('请输入预设名称：');
    if (name && name.trim()) {
        const config = {
            name: name.trim(),
            prompt: typeof state !== 'undefined' ? state.prompt : '',
            settings: {
                type: typeof state !== 'undefined' ? state.type : 'AI Video',
                model: typeof state !== 'undefined' ? state.model : 'Dreamina Seedance 2.0 Fast',
                mode: typeof state !== 'undefined' ? state.mode : 'first-last',
                aspect: typeof state !== 'undefined' ? state.aspect : '16:9',
                duration: typeof state !== 'undefined' ? state.duration : '10s',
                intensity: typeof state !== 'undefined' ? state.intensity : 70
            }
        };

        API.call('create_preset', config);
    }
}

/**
 * 应用预设
 */
function applyPreset(id) {
    API.call('apply_preset', { id });
}

/**
 * 删除预设
 */
function deletePreset(id) {
    if (confirm('确定要删除此预设吗？')) {
        API.call('delete_preset', { id });
    }
}

export { initPresets, renderPresets };
