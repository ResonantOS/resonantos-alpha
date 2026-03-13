#!/usr/bin/env node
/**
 * ResonantOS Dashboard Build Script
 * 
 * Protects the entire Chatbot Manager dashboard:
 * - Bundles all JavaScript into single obfuscated file
 * - Minifies CSS
 * - Minifies HTML templates
 * - Outputs to dist/ folder ready for production
 * 
 * Usage:
 *   node scripts/build-dashboard.js
 *   node scripts/build-dashboard.js --dev  (skip obfuscation for testing)
 */

const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');
const JavaScriptObfuscator = require('javascript-obfuscator');

const ROOT = path.join(__dirname, '..');
const DIST = path.join(ROOT, 'dist-dashboard');
const SRC_STATIC = path.join(ROOT, 'static');
const SRC_TEMPLATES = path.join(ROOT, 'templates');

const isDev = process.argv.includes('--dev');

console.log('🔨 Building ResonantOS Dashboard...');
console.log(`   Mode: ${isDev ? 'DEVELOPMENT (no obfuscation)' : 'PRODUCTION (obfuscated)'}`);

// Create dist directories
function ensureDir(dir) {
  if (!fs.existsSync(dir)) {
    fs.mkdirSync(dir, { recursive: true });
  }
}

ensureDir(DIST);
ensureDir(path.join(DIST, 'static'));
ensureDir(path.join(DIST, 'static', 'js'));
ensureDir(path.join(DIST, 'static', 'css'));
ensureDir(path.join(DIST, 'static', 'img'));
ensureDir(path.join(DIST, 'templates'));

// Step 1: Bundle all JS files
console.log('\n📦 Step 1: Bundling JavaScript...');

const jsFiles = [
  'dashboard.js',
  'chatbot-preview.js',
  'crypto-payment.js'
  // widget.js is handled separately
];

let bundledJS = `/**
 * ResonantOS Dashboard - Protected Bundle
 * Copyright ${new Date().getFullYear()} ResonantOS. All rights reserved.
 * 
 * This code is protected intellectual property.
 * Unauthorized copying, modification, or distribution is prohibited.
 */
(function() {
'use strict';
`;

// Add each JS file
for (const file of jsFiles) {
  const filePath = path.join(SRC_STATIC, 'js', file);
  if (fs.existsSync(filePath)) {
    const content = fs.readFileSync(filePath, 'utf8');
    bundledJS += `\n// === ${file} ===\n`;
    bundledJS += content;
    console.log(`   ✓ Added ${file}`);
  }
}

bundledJS += '\n})();\n';

// Step 2: Obfuscate the bundle
console.log('\n🔒 Step 2: Obfuscating JavaScript...');

let finalJS;
if (isDev) {
  finalJS = bundledJS;
  console.log('   Skipped (dev mode)');
} else {
  const obfuscatorOptions = {
    compact: true,
    controlFlowFlattening: true,
    controlFlowFlatteningThreshold: 0.7,
    deadCodeInjection: true,
    deadCodeInjectionThreshold: 0.4,
    debugProtection: true,
    debugProtectionInterval: 2000,
    disableConsoleOutput: false,
    identifierNamesGenerator: 'hexadecimal',
    identifiersPrefix: '_ros',
    log: false,
    numbersToExpressions: true,
    renameGlobals: false,
    reservedNames: [
      'loadChatbots', 'loadConversations', 'createNewChatbot', 'editChatbot',
      'generateWidget', 'downloadPackage', 'switchTab', 'switchBuilderTab',
      'ChatbotPreview', 'ROSWidget', 'CryptoPayment', 'showToast',
      'updatePreview', 'handleApiTypeChange', 'testApiConnection'
    ],
    rotateStringArray: true,
    selfDefending: true,
    shuffleStringArray: true,
    splitStrings: true,
    splitStringsChunkLength: 5,
    stringArray: true,
    stringArrayCallsTransform: true,
    stringArrayCallsTransformThreshold: 0.7,
    stringArrayEncoding: ['base64', 'rc4'],
    stringArrayIndexShift: true,
    stringArrayRotate: true,
    stringArrayShuffle: true,
    stringArrayWrappersCount: 2,
    stringArrayWrappersChainedCalls: true,
    stringArrayWrappersParametersMaxCount: 4,
    stringArrayWrappersType: 'function',
    stringArrayThreshold: 0.75,
    transformObjectKeys: true,
    unicodeEscapeSequence: true
  };

  try {
    const result = JavaScriptObfuscator.obfuscate(bundledJS, obfuscatorOptions);
    finalJS = result.getObfuscatedCode();
    console.log(`   ✓ Obfuscated (${(finalJS.length / 1024).toFixed(1)} KB)`);
  } catch (err) {
    console.error('   ✗ Obfuscation failed:', err.message);
    process.exit(1);
  }
}

// Write bundled JS
fs.writeFileSync(path.join(DIST, 'static', 'js', 'app.min.js'), finalJS);
console.log(`   ✓ Written to static/js/app.min.js`);

// Step 3: Minify CSS
console.log('\n🎨 Step 3: Minifying CSS...');

const cssPath = path.join(SRC_STATIC, 'css', 'dashboard.css');
if (fs.existsSync(cssPath)) {
  const CleanCSS = require('clean-css');
  const cssContent = fs.readFileSync(cssPath, 'utf8');
  const minified = new CleanCSS({
    level: 2,
    compatibility: '*'
  }).minify(cssContent);
  
  fs.writeFileSync(path.join(DIST, 'static', 'css', 'dashboard.min.css'), minified.styles);
  console.log(`   ✓ Minified CSS (${(minified.styles.length / 1024).toFixed(1)} KB)`);
}

// Step 4: Copy images
console.log('\n🖼️  Step 4: Copying images...');
const imgSrc = path.join(SRC_STATIC, 'img');
if (fs.existsSync(imgSrc)) {
  const files = fs.readdirSync(imgSrc);
  for (const file of files) {
    fs.copyFileSync(path.join(imgSrc, file), path.join(DIST, 'static', 'img', file));
    console.log(`   ✓ Copied ${file}`);
  }
}

// Step 5: Process templates
console.log('\n📄 Step 5: Processing templates...');

// Function to extract and replace inline JS
function processTemplate(templatePath, outputPath) {
  let content = fs.readFileSync(templatePath, 'utf8');
  
  // Replace references to individual JS files with bundled file
  content = content.replace(
    /<script src="\/static\/js\/(dashboard|chatbot-preview|crypto-payment)\.js"><\/script>/g,
    ''
  );
  
  // Replace CSS reference
  content = content.replace(
    /<link rel="stylesheet" href="\/static\/css\/dashboard\.css">/g,
    '<link rel="stylesheet" href="/static/css/dashboard.min.css">'
  );
  
  // Add bundled JS in base.html only
  if (templatePath.includes('base.html')) {
    content = content.replace(
      '</body>',
      '<script src="/static/js/app.min.js"></script>\n</body>'
    );
  }
  
  // Minify inline scripts in templates
  const inlineScriptRegex = /<script>([\s\S]*?)<\/script>/g;
  let match;
  let inlineScripts = [];
  
  while ((match = inlineScriptRegex.exec(content)) !== null) {
    // Don't process scripts that are just variable declarations or short
    if (match[1].trim().length > 100) {
      inlineScripts.push({
        original: match[0],
        content: match[1]
      });
    }
  }
  
  // Obfuscate inline scripts (only in production)
  if (!isDev && inlineScripts.length > 0) {
    for (const script of inlineScripts) {
      try {
        const obfuscated = JavaScriptObfuscator.obfuscate(script.content, {
          compact: true,
          controlFlowFlattening: true,
          controlFlowFlatteningThreshold: 0.5,
          deadCodeInjection: false,
          identifierNamesGenerator: 'hexadecimal',
          stringArray: true,
          stringArrayEncoding: ['base64'],
          stringArrayThreshold: 0.5
        });
        content = content.replace(
          script.original,
          `<script>${obfuscated.getObfuscatedCode()}</script>`
        );
      } catch (e) {
        // Skip if obfuscation fails for this script
        console.log(`   ⚠ Skipped inline script obfuscation in ${path.basename(templatePath)}`);
      }
    }
  }
  
  // Minify HTML (remove extra whitespace, comments)
  content = content
    .replace(/<!--[\s\S]*?-->/g, '') // Remove HTML comments
    .replace(/>\s+</g, '><') // Remove whitespace between tags
    .replace(/\s{2,}/g, ' ') // Collapse multiple spaces
    .trim();
  
  fs.writeFileSync(outputPath, content);
}

const templates = fs.readdirSync(SRC_TEMPLATES).filter(f => f.endsWith('.html'));
for (const template of templates) {
  const srcPath = path.join(SRC_TEMPLATES, template);
  const destPath = path.join(DIST, 'templates', template);
  processTemplate(srcPath, destPath);
  console.log(`   ✓ Processed ${template}`);
}

// Step 6: Create production server wrapper
console.log('\n🚀 Step 6: Creating production config...');

const prodConfig = `# Production Configuration
# Copy dist-dashboard/ contents to your production server

TEMPLATES_FOLDER = 'dist-dashboard/templates'
STATIC_FOLDER = 'dist-dashboard/static'

# In server.py, update:
# app = Flask(__name__, 
#             static_folder='dist-dashboard/static',
#             template_folder='dist-dashboard/templates')
`;

fs.writeFileSync(path.join(DIST, 'PRODUCTION.md'), prodConfig);

// Summary
console.log('\n' + '='.repeat(50));
console.log('✅ Build complete!');
console.log('='.repeat(50));
console.log(`\nOutput directory: ${DIST}`);
console.log('\nGenerated files:');
console.log(`  - static/js/app.min.js (${(finalJS.length / 1024).toFixed(1)} KB)`);

const cssOutput = path.join(DIST, 'static', 'css', 'dashboard.min.css');
if (fs.existsSync(cssOutput)) {
  const cssSize = fs.statSync(cssOutput).size;
  console.log(`  - static/css/dashboard.min.css (${(cssSize / 1024).toFixed(1)} KB)`);
}

console.log(`  - ${templates.length} processed templates`);

console.log('\n📋 To use in production:');
console.log('   1. Copy dist-dashboard/ to server');
console.log('   2. Update Flask paths in server.py');
console.log('   3. Or use: python server.py --dist');

if (!isDev) {
  console.log('\n🔒 Protection applied:');
  console.log('   ✓ JavaScript obfuscated (unreadable in dev tools)');
  console.log('   ✓ CSS minified');
  console.log('   ✓ HTML minified');
  console.log('   ✓ Inline scripts obfuscated');
}
