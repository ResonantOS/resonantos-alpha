#!/usr/bin/env node
/**
 * ResonantOS Widget Builder
 * 
 * Builds an obfuscated widget bundle with embedded license and config.
 * The output is unreadable to humans and AI assistants.
 * 
 * Usage:
 *   node build-widget.js --config widget-config.json --output dist/widget.min.js
 *   node build-widget.js --chatbot-id xxx --tier pro --domain example.com
 */

const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const JavaScriptObfuscator = require('javascript-obfuscator');

// Parse command line arguments
const args = process.argv.slice(2);
const options = {};
for (let i = 0; i < args.length; i += 2) {
  const key = args[i].replace(/^--/, '');
  options[key] = args[i + 1];
}

// Default configuration
const defaultConfig = {
  chatbotId: options['chatbot-id'] || 'demo',
  name: options.name || 'Chat Assistant',
  greeting: options.greeting || 'Hi! How can I help you today?',
  systemPrompt: options['system-prompt'] || 'You are a helpful assistant.',
  position: options.position || 'bottom-right',
  theme: options.theme || 'dark',
  primaryColor: options['primary-color'] || '#4ade80',
  bgColor: options['bg-color'] || '#1a1a1a',
  textColor: options['text-color'] || '#e0e0e0',
  apiEndpoint: options['api-endpoint'] || '',
  
  // License
  tier: options.tier || 'free',
  domain: options.domain || '*',
  expires: options.expires || '',
  features: options.features || '',
  
  // Feature flags based on tier
  showWatermark: options.tier !== 'pro' && options.tier !== 'enterprise',
  allowIcon: options.tier === 'pro' || options.tier === 'enterprise',
  iconUrl: options['icon-url'] || ''
};

// Load config from file if provided
let config = { ...defaultConfig };
if (options.config && fs.existsSync(options.config)) {
  const fileConfig = JSON.parse(fs.readFileSync(options.config, 'utf8'));
  config = { ...config, ...fileConfig };
}

// Generate license key
function generateLicenseKey(chatbotId, tier, domain) {
  const timestamp = Date.now().toString(36);
  const tierCode = { free: 'F', pro: 'P', enterprise: 'E' }[tier] || 'F';
  const payload = `ROS-${tierCode}-${timestamp}`;
  
  // Create checksum
  const hash = crypto.createHash('sha256')
    .update(payload + chatbotId)
    .digest('hex')
    .slice(0, 6);
  
  return `${payload}-${hash}`.toUpperCase();
}

// Simple hash matching the one in widget
function simpleHash(str) {
  let hash = 0;
  for (let i = 0; i < str.length; i++) {
    const char = str.charCodeAt(i);
    hash = ((hash << 5) - hash) + char;
    hash = hash & hash;
  }
  return Math.abs(hash).toString(36).slice(0, 6);
}

// Generate proper license key that validates
function generateValidLicenseKey(chatbotId, tier) {
  const timestamp = Date.now().toString(36);
  const tierCode = { free: 'F', pro: 'P', enterprise: 'E' }[tier] || 'F';
  const payload = `ROS-${tierCode}-${timestamp}`;
  const checksum = simpleHash(payload + chatbotId);
  return `${payload}-${checksum}`.toUpperCase();
}

// Read source widget
const srcPath = path.join(__dirname, '..', 'widget-src', 'widget.js');
let source = fs.readFileSync(srcPath, 'utf8');

// Generate license key
const licenseKey = generateValidLicenseKey(config.chatbotId, config.tier);
console.log('Generated license key:', licenseKey);

// Replace placeholders
const replacements = {
  '__LICENSE_KEY__': licenseKey,
  '__LICENSE_TIER__': config.tier,
  '__CHATBOT_ID__': config.chatbotId,
  '__DOMAIN__': config.domain,
  '__FEATURES__': config.features || (config.tier === 'pro' ? 'no_watermark,custom_icon' : ''),
  '__EXPIRES__': config.expires,
  '__WIDGET_NAME__': config.name,
  '__GREETING__': config.greeting,
  '__SYSTEM_PROMPT__': config.systemPrompt,
  '__POSITION__': config.position,
  '__THEME__': config.theme,
  '__PRIMARY_COLOR__': config.primaryColor,
  '__BG_COLOR__': config.bgColor,
  '__TEXT_COLOR__': config.textColor,
  '__API_ENDPOINT__': config.apiEndpoint,
  '__SHOW_WATERMARK__': String(config.showWatermark),
  '__ALLOW_ICON__': String(config.allowIcon),
  '__ICON_URL__': config.iconUrl
};

for (const [placeholder, value] of Object.entries(replacements)) {
  source = source.split(placeholder).join(value);
}

// Obfuscation settings - MAXIMUM protection
const obfuscatorOptions = {
  // Compact output
  compact: true,
  
  // Control flow flattening - makes logic hard to follow
  controlFlowFlattening: true,
  controlFlowFlatteningThreshold: 0.75,
  
  // Dead code injection - adds fake code
  deadCodeInjection: true,
  deadCodeInjectionThreshold: 0.4,
  
  // Debug protection - breaks debugging tools
  debugProtection: true,
  debugProtectionInterval: 2000,
  
  // Disable console output
  disableConsoleOutput: false, // Keep for debugging
  
  // Domain lock (optional)
  // domainLock: config.domain !== '*' ? [config.domain] : [],
  
  // Identifier names generator
  identifierNamesGenerator: 'hexadecimal',
  
  // Identifiers prefix
  identifiersPrefix: '_0x',
  
  // Log calls - wraps console calls
  log: false,
  
  // Numbers to expressions
  numbersToExpressions: true,
  
  // Rename globals
  renameGlobals: false, // Keep ROSWidget accessible
  
  // Reserved names - don't mangle these
  reservedNames: ['ROSWidget', 'open', 'close', 'toggle', 'send', 'getLicense'],
  
  // Rotate string array
  rotateStringArray: true,
  
  // Self defending - crashes if code is modified
  selfDefending: true,
  
  // Shuffle string array
  shuffleStringArray: true,
  
  // Split strings
  splitStrings: true,
  splitStringsChunkLength: 5,
  
  // String array encoding
  stringArray: true,
  stringArrayCallsTransform: true,
  stringArrayCallsTransformThreshold: 0.75,
  stringArrayEncoding: ['base64', 'rc4'],
  stringArrayIndexShift: true,
  stringArrayRotate: true,
  stringArrayShuffle: true,
  stringArrayWrappersCount: 2,
  stringArrayWrappersChainedCalls: true,
  stringArrayWrappersParametersMaxCount: 4,
  stringArrayWrappersType: 'function',
  stringArrayThreshold: 0.75,
  
  // Transform object keys
  transformObjectKeys: true,
  
  // Unicode escape sequence
  unicodeEscapeSequence: true
};

console.log('Obfuscating widget...');

try {
  const result = JavaScriptObfuscator.obfuscate(source, obfuscatorOptions);
  const obfuscatedCode = result.getObfuscatedCode();
  
  // Output path
  const outputDir = path.join(__dirname, '..', 'dist');
  if (!fs.existsSync(outputDir)) {
    fs.mkdirSync(outputDir, { recursive: true });
  }
  
  const outputPath = options.output || path.join(outputDir, `widget-${config.chatbotId}.min.js`);
  fs.writeFileSync(outputPath, obfuscatedCode);
  
  console.log('✅ Widget built successfully!');
  console.log('   Output:', outputPath);
  console.log('   Size:', (obfuscatedCode.length / 1024).toFixed(2), 'KB');
  console.log('   License:', licenseKey);
  console.log('   Tier:', config.tier);
  
  // Also output a manifest
  const manifest = {
    chatbotId: config.chatbotId,
    licenseKey: licenseKey,
    tier: config.tier,
    domain: config.domain,
    expires: config.expires,
    createdAt: new Date().toISOString(),
    file: path.basename(outputPath),
    size: obfuscatedCode.length
  };
  
  const manifestPath = outputPath.replace('.min.js', '.manifest.json');
  fs.writeFileSync(manifestPath, JSON.stringify(manifest, null, 2));
  console.log('   Manifest:', manifestPath);
  
} catch (error) {
  console.error('❌ Build failed:', error.message);
  process.exit(1);
}
