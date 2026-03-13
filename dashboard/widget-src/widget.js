/**
 * ResonantOS Chat Widget - Source
 * DO NOT DISTRIBUTE - This file is obfuscated before distribution
 * 
 * License tiers:
 * - free: 1 chatbot, watermark shown, no custom icon
 * - pro: 3 chatbots, no watermark, custom icon allowed
 * - enterprise: 10 chatbots, white-label, custom branding
 */
(function() {
  'use strict';

  // License configuration - embedded at build time
  const LICENSE = {
    key: '__LICENSE_KEY__',
    tier: '__LICENSE_TIER__',
    chatbotId: '__CHATBOT_ID__',
    domain: '__DOMAIN__',
    features: '__FEATURES__'.split(','),
    expires: '__EXPIRES__'
  };

  // Widget configuration - embedded at build time  
  const CONFIG = {
    id: '__CHATBOT_ID__',
    name: '__WIDGET_NAME__',
    greeting: '__GREETING__',
    systemPrompt: '__SYSTEM_PROMPT__',
    position: '__POSITION__',
    theme: '__THEME__',
    primaryColor: '__PRIMARY_COLOR__',
    bgColor: '__BG_COLOR__',
    textColor: '__TEXT_COLOR__',
    apiEndpoint: '__API_ENDPOINT__',
    showWatermark: '__SHOW_WATERMARK__' === 'true',
    allowIcon: '__ALLOW_ICON__' === 'true',
    iconUrl: '__ICON_URL__'
  };

  // Watermark text (obfuscated in build)
  const WATERMARK_TEXT = 'Powered by ResonantOS';
  const WATERMARK_URL = 'https://resonantos.com';

  // License validation
  function validateLicense() {
    // Check expiration
    if (LICENSE.expires && LICENSE.expires !== '__EXPIRES__') {
      const expiryDate = new Date(parseInt(LICENSE.expires));
      if (new Date() > expiryDate) {
        console.warn('ResonantOS: License expired');
        return { valid: false, tier: 'free', reason: 'expired' };
      }
    }

    // Check domain (if specified)
    if (LICENSE.domain && LICENSE.domain !== '__DOMAIN__' && LICENSE.domain !== '*') {
      const currentDomain = window.location.hostname;
      const allowedDomains = LICENSE.domain.split(',').map(d => d.trim());
      const domainMatch = allowedDomains.some(d => {
        if (d.startsWith('*.')) {
          return currentDomain.endsWith(d.slice(1)) || currentDomain === d.slice(2);
        }
        return currentDomain === d || currentDomain === 'www.' + d;
      });
      if (!domainMatch) {
        console.warn('ResonantOS: Domain not licensed');
        return { valid: false, tier: 'free', reason: 'domain' };
      }
    }

    // Validate key format (simple checksum)
    if (LICENSE.key && LICENSE.key !== '__LICENSE_KEY__') {
      const keyParts = LICENSE.key.split('-');
      if (keyParts.length >= 3) {
        const checksum = keyParts[keyParts.length - 1];
        const payload = keyParts.slice(0, -1).join('-');
        const computed = simpleHash(payload + LICENSE.chatbotId);
        if (checksum !== computed) {
          console.warn('ResonantOS: Invalid license key');
          return { valid: false, tier: 'free', reason: 'invalid' };
        }
      }
    }

    return { 
      valid: true, 
      tier: LICENSE.tier || 'free',
      features: LICENSE.features || []
    };
  }

  // Simple hash for checksum (not cryptographic - just deterrent)
  function simpleHash(str) {
    let hash = 0;
    for (let i = 0; i < str.length; i++) {
      const char = str.charCodeAt(i);
      hash = ((hash << 5) - hash) + char;
      hash = hash & hash;
    }
    return Math.abs(hash).toString(36).slice(0, 6);
  }

  // Check if feature is allowed
  function hasFeature(feature) {
    const license = validateLicense();
    if (license.tier === 'enterprise') return true;
    if (license.tier === 'pro') {
      return ['no_watermark', 'custom_icon', 'analytics'].includes(feature);
    }
    return false;
  }

  // State
  let isOpen = false;
  let messages = [];
  let sessionId = 'ros_' + Math.random().toString(36).substr(2, 9);

  // Create widget DOM
  function createWidget() {
    const license = validateLicense();
    const showWatermark = !hasFeature('no_watermark') || CONFIG.showWatermark;
    const canShowIcon = hasFeature('custom_icon') && CONFIG.allowIcon && CONFIG.iconUrl;

    // Container
    const container = document.createElement('div');
    container.id = 'ros-widget';
    container.className = 'ros-widget ros-' + CONFIG.position + ' ros-' + CONFIG.theme;

    // Floating button
    const button = document.createElement('button');
    button.className = 'ros-btn';
    button.style.backgroundColor = CONFIG.primaryColor;
    if (canShowIcon && CONFIG.iconUrl && CONFIG.iconUrl !== '__ICON_URL__') {
      button.innerHTML = '<img src="' + CONFIG.iconUrl + '" alt="Chat" style="width:28px;height:28px;border-radius:50%;">';
    } else {
      button.innerHTML = '<svg viewBox="0 0 24 24" width="28" height="28" fill="white"><path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2z"/></svg>';
    }
    button.onclick = toggleWidget;

    // Chat window
    const chat = document.createElement('div');
    chat.className = 'ros-chat';
    chat.innerHTML = buildChatHTML(showWatermark);

    container.appendChild(button);
    container.appendChild(chat);

    // Inject styles
    injectStyles();

    document.body.appendChild(container);

    // Show greeting
    if (CONFIG.greeting && CONFIG.greeting !== '__GREETING__') {
      addMessage('bot', CONFIG.greeting);
    }
  }

  function buildChatHTML(showWatermark) {
    let html = '<div class="ros-header" style="background:' + CONFIG.primaryColor + '">';
    html += '<span class="ros-title">' + escapeHtml(CONFIG.name || 'Chat') + '</span>';
    html += '<button class="ros-close" onclick="ROSWidget.close()">&times;</button>';
    html += '</div>';
    html += '<div class="ros-messages" id="ros-msg"></div>';
    html += '<div class="ros-input-wrap">';
    html += '<input type="text" class="ros-input" id="ros-in" placeholder="Type a message..." onkeypress="if(event.key===\'Enter\')ROSWidget.send()">';
    html += '<button class="ros-send" onclick="ROSWidget.send()" style="background:' + CONFIG.primaryColor + '">&#10148;</button>';
    html += '</div>';
    
    if (showWatermark) {
      html += '<div class="ros-watermark"><a href="' + WATERMARK_URL + '" target="_blank" rel="noopener">' + WATERMARK_TEXT + '</a></div>';
    }
    
    return html;
  }

  function injectStyles() {
    if (document.getElementById('ros-styles')) return;
    
    const isDark = CONFIG.theme === 'dark';
    const bg = isDark ? (CONFIG.bgColor || '#1a1a2e') : '#ffffff';
    const text = isDark ? (CONFIG.textColor || '#e0e0e0') : '#333333';
    const inputBg = isDark ? 'rgba(255,255,255,0.1)' : 'rgba(0,0,0,0.05)';

    const css = document.createElement('style');
    css.id = 'ros-styles';
    css.textContent = `
      .ros-widget{position:fixed;z-index:999999;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif}
      .ros-bottom-right{bottom:20px;right:20px}
      .ros-bottom-left{bottom:20px;left:20px}
      .ros-btn{width:60px;height:60px;border-radius:50%;border:none;cursor:pointer;box-shadow:0 4px 20px rgba(0,0,0,0.3);transition:transform .2s;display:flex;align-items:center;justify-content:center}
      .ros-btn:hover{transform:scale(1.1)}
      .ros-chat{position:absolute;bottom:80px;right:0;width:380px;max-width:calc(100vw - 40px);height:520px;max-height:calc(100vh - 120px);border-radius:16px;background:${bg};color:${text};box-shadow:0 10px 40px rgba(0,0,0,0.4);display:none;flex-direction:column;overflow:hidden}
      .ros-chat.open{display:flex}
      .ros-bottom-left .ros-chat{right:auto;left:0}
      .ros-header{padding:16px;display:flex;justify-content:space-between;align-items:center;color:#fff}
      .ros-title{font-weight:600;font-size:16px}
      .ros-close{background:none;border:none;color:#fff;font-size:24px;cursor:pointer;padding:0;line-height:1}
      .ros-messages{flex:1;overflow-y:auto;padding:16px}
      .ros-msg{margin:8px 0;padding:10px 14px;border-radius:12px;max-width:85%;word-wrap:break-word;line-height:1.5}
      .ros-msg-bot{background:${inputBg}}
      .ros-msg-user{background:${CONFIG.primaryColor};color:#fff;margin-left:auto}
      .ros-msg-typing{opacity:0.7}
      .ros-input-wrap{display:flex;padding:12px;border-top:1px solid ${isDark ? 'rgba(255,255,255,0.1)' : 'rgba(0,0,0,0.1)'}}
      .ros-input{flex:1;padding:12px;border:none;border-radius:24px;background:${inputBg};color:inherit;font-size:14px;outline:none}
      .ros-input:focus{box-shadow:0 0 0 2px ${CONFIG.primaryColor}40}
      .ros-send{width:44px;height:44px;border-radius:50%;border:none;color:#fff;cursor:pointer;margin-left:8px;font-size:18px}
      .ros-watermark{text-align:center;padding:8px;font-size:11px;opacity:0.6}
      .ros-watermark a{color:inherit;text-decoration:none}
      .ros-watermark a:hover{text-decoration:underline}
    `;
    document.head.appendChild(css);
  }

  function toggleWidget() {
    const chat = document.querySelector('.ros-chat');
    if (chat) {
      isOpen = !isOpen;
      chat.classList.toggle('open', isOpen);
      if (isOpen) {
        document.getElementById('ros-in').focus();
      }
    }
  }

  function addMessage(role, content) {
    const container = document.getElementById('ros-msg');
    if (!container) return;
    
    const msg = document.createElement('div');
    msg.className = 'ros-msg ros-msg-' + role;
    msg.textContent = content;
    container.appendChild(msg);
    container.scrollTop = container.scrollHeight;
    
    messages.push({ role, content, timestamp: Date.now() });
  }

  function sendMessage() {
    const input = document.getElementById('ros-in');
    if (!input) return;
    
    const text = input.value.trim();
    if (!text) return;
    
    input.value = '';
    addMessage('user', text);

    // Show typing indicator
    const typingId = 'typing-' + Date.now();
    const container = document.getElementById('ros-msg');
    const typing = document.createElement('div');
    typing.id = typingId;
    typing.className = 'ros-msg ros-msg-bot ros-msg-typing';
    typing.textContent = '...';
    container.appendChild(typing);
    container.scrollTop = container.scrollHeight;

    // Send to API
    const endpoint = CONFIG.apiEndpoint || '';
    if (endpoint && endpoint !== '__API_ENDPOINT__') {
      fetch(endpoint + '/chat/' + CONFIG.id, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
          message: text, 
          sessionId: sessionId,
          licenseKey: LICENSE.key
        })
      })
      .then(r => r.json())
      .then(data => {
        const el = document.getElementById(typingId);
        if (el) el.remove();
        addMessage('bot', data.response || 'Sorry, I could not process that.');
      })
      .catch(err => {
        const el = document.getElementById(typingId);
        if (el) el.remove();
        addMessage('bot', 'Connection error. Please try again.');
      });
    } else {
      // Demo mode - no API configured
      setTimeout(() => {
        const el = document.getElementById(typingId);
        if (el) el.remove();
        const responses = [
          "Thanks for your message! I'm here to help.",
          "I understand. Let me assist you with that.",
          "Great question! Here's what I know...",
        ];
        addMessage('bot', responses[Math.floor(Math.random() * responses.length)]);
      }, 800);
    }
  }

  function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text || '';
    return div.innerHTML;
  }

  // Public API
  window.ROSWidget = {
    open: function() { 
      const chat = document.querySelector('.ros-chat');
      if (chat) { chat.classList.add('open'); isOpen = true; }
    },
    close: function() { 
      const chat = document.querySelector('.ros-chat');
      if (chat) { chat.classList.remove('open'); isOpen = false; }
    },
    toggle: toggleWidget,
    send: sendMessage,
    getLicense: function() { return validateLicense(); }
  };

  // Initialize
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', createWidget);
  } else {
    createWidget();
  }
})();
