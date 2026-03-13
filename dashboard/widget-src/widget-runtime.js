/**
 * ResonantOS Chat Widget - Runtime Version
 * 
 * This widget receives its configuration from the server at runtime.
 * Feature flags are SERVER-ENFORCED - no client-side bypassing.
 * 
 * DO NOT DISTRIBUTE - Served minified from our CDN only.
 */
(function() {
  'use strict';

  // Get config from loader (server-provided)
  var CONFIG = window.__ROS_CONFIG__;
  var LICENSE = window.__ROS_LICENSE__;

  if (!CONFIG || !CONFIG.id) {
    console.error('[ResonantOS] Widget config not loaded. Use loader.js');
    return;
  }

  // State
  var isOpen = false;
  var messages = [];
  var sessionId = 'ros_' + Math.random().toString(36).substr(2, 9);
  var isTyping = false;

  // Watermark config - SERVER CONTROLLED
  var WATERMARK = {
    show: LICENSE.showWatermark !== false, // Default to true unless explicitly false
    text: 'Powered by ResonantOS',
    url: 'https://resonantos.com?ref=widget'
  };

  // Create widget DOM
  function createWidget() {
    // Container
    var container = document.createElement('div');
    container.id = 'ros-widget';
    container.className = 'ros-widget ros-' + CONFIG.position + ' ros-' + CONFIG.theme;

    // Floating button
    var button = document.createElement('button');
    button.className = 'ros-btn';
    button.style.backgroundColor = CONFIG.primaryColor;
    button.setAttribute('aria-label', 'Open chat');
    
    // Icon - only custom if server allows
    if (LICENSE.allowIcon && CONFIG.iconUrl) {
      button.innerHTML = '<img src="' + escapeHtml(CONFIG.iconUrl) + '" alt="Chat" style="width:28px;height:28px;border-radius:50%;object-fit:cover;">';
    } else {
      button.innerHTML = '<svg viewBox="0 0 24 24" width="28" height="28" fill="white"><path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2z"/></svg>';
    }
    button.onclick = toggleWidget;

    // Chat window
    var chat = document.createElement('div');
    chat.className = 'ros-chat';
    chat.innerHTML = buildChatHTML();

    container.appendChild(button);
    container.appendChild(chat);

    // Inject styles
    injectStyles();

    document.body.appendChild(container);

    // Show greeting after render
    if (CONFIG.greeting) {
      setTimeout(function() {
        addMessage('bot', CONFIG.greeting);
      }, 100);
    }

    // Add suggested prompts if available
    if (CONFIG.suggestedPrompts && CONFIG.suggestedPrompts.length > 0) {
      renderSuggestedPrompts(CONFIG.suggestedPrompts);
    }
  }

  function buildChatHTML() {
    var html = '<div class="ros-header" style="background:' + CONFIG.primaryColor + '">';
    html += '<span class="ros-title">' + escapeHtml(CONFIG.name || 'Chat') + '</span>';
    html += '<button class="ros-close" onclick="ROSWidget.close()" aria-label="Close chat">&times;</button>';
    html += '</div>';
    html += '<div class="ros-messages" id="ros-msg"></div>';
    html += '<div class="ros-suggestions" id="ros-suggestions"></div>';
    html += '<div class="ros-input-wrap">';
    html += '<input type="text" class="ros-input" id="ros-in" placeholder="Type a message..." onkeypress="if(event.key===\'Enter\')ROSWidget.send()">';
    html += '<button class="ros-send" onclick="ROSWidget.send()" style="background:' + CONFIG.primaryColor + '" aria-label="Send message">&#10148;</button>';
    html += '</div>';
    
    // Watermark - SERVER CONTROLLED, not CSS-hackable
    // The show flag comes from server based on license tier
    if (WATERMARK.show) {
      html += '<div class="ros-watermark"><a href="' + WATERMARK.url + '" target="_blank" rel="noopener sponsored">' + WATERMARK.text + '</a></div>';
    }
    
    return html;
  }

  function renderSuggestedPrompts(prompts) {
    var container = document.getElementById('ros-suggestions');
    if (!container || !prompts.length) return;
    
    container.innerHTML = '';
    prompts.slice(0, 3).forEach(function(prompt) {
      var btn = document.createElement('button');
      btn.className = 'ros-suggestion';
      btn.textContent = prompt;
      btn.onclick = function() {
        document.getElementById('ros-in').value = prompt;
        sendMessage();
        container.innerHTML = '';
      };
      container.appendChild(btn);
    });
  }

  function injectStyles() {
    if (document.getElementById('ros-styles')) return;
    
    var isDark = CONFIG.theme === 'dark';
    var bg = isDark ? (CONFIG.bgColor || '#1a1a2e') : '#ffffff';
    var text = isDark ? (CONFIG.textColor || '#e0e0e0') : '#333333';
    var inputBg = isDark ? 'rgba(255,255,255,0.1)' : 'rgba(0,0,0,0.05)';
    var borderColor = isDark ? 'rgba(255,255,255,0.1)' : 'rgba(0,0,0,0.1)';

    var css = document.createElement('style');
    css.id = 'ros-styles';
    css.textContent = [
      '.ros-widget{position:fixed;z-index:999999;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}',
      '.ros-bottom-right{bottom:20px;right:20px}',
      '.ros-bottom-left{bottom:20px;left:20px}',
      '.ros-top-right{top:20px;right:20px}',
      '.ros-top-left{top:20px;left:20px}',
      '.ros-btn{width:60px;height:60px;border-radius:50%;border:none;cursor:pointer;box-shadow:0 4px 20px rgba(0,0,0,0.3);transition:transform .2s,box-shadow .2s;display:flex;align-items:center;justify-content:center}',
      '.ros-btn:hover{transform:scale(1.1);box-shadow:0 6px 24px rgba(0,0,0,0.4)}',
      '.ros-btn:focus{outline:2px solid ' + CONFIG.primaryColor + ';outline-offset:2px}',
      '.ros-chat{position:absolute;bottom:80px;right:0;width:380px;max-width:calc(100vw - 40px);height:520px;max-height:calc(100vh - 120px);border-radius:16px;background:' + bg + ';color:' + text + ';box-shadow:0 10px 40px rgba(0,0,0,0.4);display:none;flex-direction:column;overflow:hidden}',
      '.ros-chat.open{display:flex}',
      '.ros-bottom-left .ros-chat{right:auto;left:0}',
      '.ros-top-right .ros-chat,.ros-top-left .ros-chat{bottom:auto;top:80px}',
      '.ros-header{padding:16px;display:flex;justify-content:space-between;align-items:center;color:#fff}',
      '.ros-title{font-weight:600;font-size:16px}',
      '.ros-close{background:none;border:none;color:#fff;font-size:24px;cursor:pointer;padding:0 4px;line-height:1;opacity:0.8;transition:opacity .2s}',
      '.ros-close:hover{opacity:1}',
      '.ros-messages{flex:1;overflow-y:auto;padding:16px}',
      '.ros-msg{margin:8px 0;padding:10px 14px;border-radius:12px;max-width:85%;word-wrap:break-word;line-height:1.5;animation:ros-fadein .2s}',
      '@keyframes ros-fadein{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:translateY(0)}}',
      '.ros-msg-bot{background:' + inputBg + '}',
      '.ros-msg-user{background:' + CONFIG.primaryColor + ';color:#fff;margin-left:auto}',
      '.ros-msg-typing{opacity:0.6}',
      '.ros-msg-typing::after{content:"";display:inline-block;animation:ros-dots 1.4s infinite}',
      '@keyframes ros-dots{0%,20%{content:""}40%{content:"."}60%{content:".."}80%,100%{content:"..."}}',
      '.ros-suggestions{display:flex;gap:8px;padding:8px 16px;flex-wrap:wrap}',
      '.ros-suggestion{background:' + inputBg + ';border:1px solid ' + borderColor + ';border-radius:16px;padding:6px 12px;font-size:13px;cursor:pointer;transition:background .2s}',
      '.ros-suggestion:hover{background:' + CONFIG.primaryColor + '22}',
      '.ros-input-wrap{display:flex;padding:12px;border-top:1px solid ' + borderColor + '}',
      '.ros-input{flex:1;padding:12px;border:none;border-radius:24px;background:' + inputBg + ';color:inherit;font-size:14px;outline:none}',
      '.ros-input:focus{box-shadow:0 0 0 2px ' + CONFIG.primaryColor + '40}',
      '.ros-input::placeholder{color:' + (isDark ? 'rgba(255,255,255,0.5)' : 'rgba(0,0,0,0.5)') + '}',
      '.ros-send{width:44px;height:44px;border-radius:50%;border:none;color:#fff;cursor:pointer;margin-left:8px;font-size:18px;transition:transform .2s}',
      '.ros-send:hover{transform:scale(1.1)}',
      '.ros-send:disabled{opacity:0.5;cursor:not-allowed;transform:none}',
      // Watermark styles - intentionally subtle but present
      '.ros-watermark{text-align:center;padding:8px;font-size:11px;opacity:0.6}',
      '.ros-watermark a{color:inherit;text-decoration:none}',
      '.ros-watermark a:hover{text-decoration:underline}',
      // Mobile responsive
      '@media (max-width:440px){.ros-chat{width:calc(100vw - 20px);height:calc(100vh - 100px);bottom:70px;right:-10px}.ros-bottom-left .ros-chat{left:-10px}}'
    ].join('\n');
    document.head.appendChild(css);
  }

  function toggleWidget() {
    var chat = document.querySelector('.ros-chat');
    if (chat) {
      isOpen = !isOpen;
      chat.classList.toggle('open', isOpen);
      if (isOpen) {
        var input = document.getElementById('ros-in');
        if (input) input.focus();
        // Track widget open if analytics enabled
        if (LICENSE.analyticsEnabled) {
          trackEvent('widget_opened');
        }
      }
    }
  }

  function addMessage(role, content) {
    var container = document.getElementById('ros-msg');
    if (!container) return;
    
    var msg = document.createElement('div');
    msg.className = 'ros-msg ros-msg-' + role;
    
    // Simple markdown-ish formatting
    if (role === 'bot') {
      msg.innerHTML = formatMessage(content);
    } else {
      msg.textContent = content;
    }
    
    container.appendChild(msg);
    container.scrollTop = container.scrollHeight;
    
    messages.push({ role: role, content: content, timestamp: Date.now() });
  }

  function formatMessage(text) {
    // Basic safe formatting
    return escapeHtml(text)
      .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
      .replace(/\*(.+?)\*/g, '<em>$1</em>')
      .replace(/\n/g, '<br>');
  }

  function showTyping() {
    if (isTyping) return;
    isTyping = true;
    
    var container = document.getElementById('ros-msg');
    if (!container) return;
    
    var typing = document.createElement('div');
    typing.id = 'ros-typing';
    typing.className = 'ros-msg ros-msg-bot ros-msg-typing';
    typing.textContent = '';
    container.appendChild(typing);
    container.scrollTop = container.scrollHeight;
  }

  function hideTyping() {
    isTyping = false;
    var el = document.getElementById('ros-typing');
    if (el) el.remove();
  }

  function sendMessage() {
    var input = document.getElementById('ros-in');
    if (!input) return;
    
    var text = input.value.trim();
    if (!text || isTyping) return;
    
    input.value = '';
    addMessage('user', text);
    showTyping();

    // Clear suggestions after first message
    var suggestions = document.getElementById('ros-suggestions');
    if (suggestions) suggestions.innerHTML = '';

    // Send to API - endpoint from server config
    var endpoint = CONFIG.apiEndpoint || '';
    if (!endpoint) {
      hideTyping();
      addMessage('bot', 'Chat not configured. Please contact support.');
      return;
    }

    fetch(endpoint + '/chat/' + CONFIG.id, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ 
        message: text, 
        sessionId: sessionId,
        // Include session token for rate limiting
        token: LICENSE.sessionToken
      })
    })
    .then(function(r) { return r.json(); })
    .then(function(data) {
      hideTyping();
      if (data.error) {
        addMessage('bot', data.error);
      } else {
        addMessage('bot', data.response || 'I could not process that request.');
      }
    })
    .catch(function(err) {
      hideTyping();
      addMessage('bot', 'Connection error. Please try again.');
      console.error('[ResonantOS]', err);
    });
  }

  function trackEvent(eventName, data) {
    if (!LICENSE.analyticsEnabled) return;
    
    fetch(CONFIG.apiEndpoint + '/analytics/event', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        chatbotId: CONFIG.id,
        sessionId: sessionId,
        event: eventName,
        data: data || {}
      })
    }).catch(function() {}); // Silent fail for analytics
  }

  function escapeHtml(text) {
    var div = document.createElement('div');
    div.textContent = text || '';
    return div.innerHTML;
  }

  // Public API
  window.ROSWidget = {
    open: function() { 
      var chat = document.querySelector('.ros-chat');
      if (chat && !isOpen) { 
        chat.classList.add('open'); 
        isOpen = true;
        var input = document.getElementById('ros-in');
        if (input) input.focus();
      }
    },
    close: function() { 
      var chat = document.querySelector('.ros-chat');
      if (chat) { 
        chat.classList.remove('open'); 
        isOpen = false; 
      }
    },
    toggle: toggleWidget,
    send: sendMessage,
    isOpen: function() { return isOpen; },
    getSessionId: function() { return sessionId; }
  };

  // Initialize
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', createWidget);
  } else {
    createWidget();
  }
})();
