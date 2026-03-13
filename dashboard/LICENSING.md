# ResonantOS Widget Licensing & Code Protection

## Overview

ResonantOS uses a **SaaS-first** code protection model. Users consume the **service**, they don't own the **code**.

## Pricing Tiers

| Tier | Chatbots | Custom Icon | Watermark | Analytics |
|------|----------|-------------|-----------|-----------|
| Free | 1 | ❌ | Shown | Basic |
| Essential | 3 | ✅ | Removable | Full |
| Pro | 3 | ✅ | Removable | Full |
| Professional | 5 | ✅ | Removable | Full |
| Business | 10 | ✅ | Removable | Full |
| Enterprise | 100 | ✅ | Removable | Full |

## Architecture

### 1. Thin Loader (Customer Gets This Only)

```html
<script src="https://resonantos.com/widget/loader.js" data-chatbot-id="xxx"></script>
```

This is the **ONLY** code customers embed on their sites:
- No business logic
- No feature flags
- Just a loader that fetches config from our server

**File:** `static/loader.js`

### 2. Server-Side Feature Gating

When the widget loads, the loader calls:

```
GET /api/widget/init/:chatbotId
```

**Returns:**
```json
{
  "success": true,
  "widgetVersion": "v1.0.0",
  "config": {
    "id": "abc123",
    "name": "Support Chat",
    "greeting": "Hi! How can I help?",
    "primaryColor": "#4ade80",
    "iconUrl": "",  // Only set if license allows
    "apiEndpoint": "https://resonantos.com/api"
  },
  "license": {
    "tier": "free",
    "showWatermark": true,
    "allowIcon": false,
    "analyticsEnabled": false,
    "sessionToken": "abc123..."
  }
}
```

**ALL feature decisions happen here, server-side.**

### 3. Widget Code (Never Distributed)

The actual widget JavaScript is served from:
```
/widget/v/{version}/widget.min.js
```

- Served minified + obfuscated from our server
- NOT included in embed code
- Updates apply instantly to all customers
- No way to modify or bypass

**Source:** `widget-src/widget-runtime.js`
**Built:** `dist/widget-runtime.min.js`

## License Enforcement Points

### On Widget Load (Every Page View)
- `/api/widget/init/:chatbotId` checks license tier
- Returns appropriate feature flags
- Watermark shown unless license explicitly allows removal
- Custom icon only if license permits

### On Chatbot Creation
- `/api/chatbots` (POST) checks chatbot limit
- Returns 403 if limit exceeded
- Shows upgrade message with current tier info

### On Settings Page
- `/api/chatbots/check-limit` validates before UI allows creation
- Displays remaining chatbot slots

## Watermark Protection

The "Powered by ResonantOS" watermark:
- Links to https://resonantos.com?ref=widget
- **Server-controlled** - not removable by CSS
- `showWatermark` flag comes from server based on license
- Widget code doesn't contain any bypass logic

## Security Features

1. **Obfuscation**
   - Widget code is obfuscated using javascript-obfuscator
   - Self-defending code (crashes if modified)
   - String array encryption
   - Control flow flattening

2. **Rate Limiting**
   - Session tokens for per-widget rate limiting
   - Configurable rate limits per chatbot

3. **Domain Validation** (Future)
   - CORS restrictions to registered domains
   - `allowed_domains` field in database

## API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/widget/loader.js` | GET | Thin loader script |
| `/api/widget/init/:chatbotId` | GET | Get config + license flags |
| `/widget/v/:version/widget.min.js` | GET | Serve widget code |
| `/api/chatbots/check-limit` | POST | Check if user can create more |
| `/api/license/check` | POST | Check license status |
| `/api/license/grant` | POST | Grant license (admin) |

## Database Tables

### `chatbots`
- `user_id` - Links chatbot to owner
- `icon_url` - Custom icon (only shown if licensed)
- `show_watermark` - User preference (still controlled by license)

### `licenses`
- `user_id` - License owner
- `tier` - 'free', 'essential', 'pro', 'professional', 'business', 'enterprise'
- `features` - JSON array of enabled features
- `expires_at` - License expiration timestamp
- `stripe_subscription_id` - Payment tracking

## Build Process

```bash
# Build runtime widget (production)
node scripts/build-runtime-widget.js

# Full build (dashboard + widget)
./build.sh
```

## Testing

1. Create a free account (no license record = free tier)
2. Create one chatbot ✓
3. Try to create second chatbot → 403 error
4. Grant pro license: `POST /api/license/grant`
5. Create more chatbots ✓
6. Watermark should be removable

## Files Modified

- `static/loader.js` - Thin SaaS loader
- `widget-src/widget-runtime.js` - Runtime widget source
- `scripts/build-runtime-widget.js` - Build script
- `server.py` - Added endpoints:
  - `/api/widget/init/:chatbotId`
  - `/widget/v/:version/widget.min.js`
  - `/api/chatbots/check-limit`
  - License enforcement in chatbot creation
