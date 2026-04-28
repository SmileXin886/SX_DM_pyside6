/**
 * Bridge 通信模块 - 固定通信宪法
 * ================================
 * 本模块是前后端通信的唯一标准实现，严禁任何修改！
 */

(function(global) {
    'use strict';

    console.log('[bridge.js] 加载中...');

    // ===== 固定回调函数 =====
    window.onQtResult = window.onQtResult || function(taskId, result) {
        console.log('[Bridge] onQtResult:', taskId, result);
    };

    window.onQtProgress = window.onQtProgress || function(taskId, percent, msg) {
        console.log('[Bridge] onQtProgress:', taskId, percent, msg);
    };

    window.onQtError = window.onQtError || function(taskId, error) {
        console.error('[Bridge] onQtError:', taskId, error);
    };

    window.onQtMessage = window.onQtMessage || function(action, data) {
        console.log('[Bridge] onQtMessage:', action, data);
    };

    // ===== pyBridge 接口（固定不变）=====
    // pyBridge 由 main.py 的 QWebChannel 初始化时设置
    // 这里只做检查
    window.pyBridge = window.pyBridge || null;

    console.log('[bridge.js] 通信模块已加载');

})(typeof window !== 'undefined' ? window : this);
