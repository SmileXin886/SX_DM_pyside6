// webchannel.js - WebChannel 通信桥接
// 用于 Qt WebEngineView 与网页之间的双向通信

(function() {
    'use strict';
    
    // 等待 Qt WebChannel 注入
    function initQtBridge() {
        if (typeof qt !== 'undefined' && qt.webChannelTransport) {
            // Qt WebChannel 已可用
            window.QtBridge = {
                send: function(action, data) {
                    if (qt && qt.webChannelTransport) {
                        qt.receiveMessage({ action: action, data: data });
                    }
                }
            };
            
            // 监听页面消息并发送给 Qt
            window.addEventListener('qt-message', function(e) {
                window.QtBridge.send(e.detail.action, e.detail.data);
            });
            
            console.log('[WebChannel] Qt bridge initialized');
            return true;
        }
        return false;
    }
    
    // 轮询等待 Qt WebChannel
    let attempts = 0;
    function waitForQt() {
        if (initQtBridge()) return;
        
        attempts++;
        if (attempts < 50) { // 最多等待 5 秒
            setTimeout(waitForQt, 100);
        } else {
            console.warn('[WebChannel] Qt bridge not found, using fallback');
            // 使用 localStorage 作为后备通信方式
            window.QtBridge = {
                send: function(action, data) {
                    localStorage.setItem('qt-message', JSON.stringify({ action: action, data: data }));
                    localStorage.removeItem('qt-message');
                }
            };
        }
    }
    
    // 初始化
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', waitForQt);
    } else {
        waitForQt();
    }
    
    // 提供接收 Qt 消息的接口
    window.onQtMessage = function(action, data) {
        const event = new CustomEvent('qt-reply', {
            detail: { action: action, data: data }
        });
        window.dispatchEvent(event);
    };
    
})();
