#!/usr/bin/env node
/**
 * ResonantOS Runtime Widget Builder
 * 
 * Builds a single obfuscated widget bundle that receives config at runtime.
 * This is served from our CDN - NOT distributed to customers.
 * 
 * Usage:
 *   node build-runtime-widget.js
 */

const fs = require('fs');
const path = require('path');
const JavaScriptObfuscator = require('javascript-obfuscator');

// Read source widget
const srcPath = path.join(__dirname, '..', 'widget-src', 'widget-runtime.js');
let source = fs.readFileSync(srcPath, 'utf8');

console.log('Building runtime widget...');
console.log('Source:', srcPath);

// Obfuscation settings - protect the widget code
const obfuscatorOptions = {
  // Compact output
  compact: true,
  
  // Control flow flattening - makes logic hard to follow
  controlFlowFlattening: true,
  controlFlowFlatteningThreshold: 0.5,
  
  // Dead code injection - adds fake code
  deadCodeInjection: true,
  deadCodeInjectionThreshold: 0.3,
  
  // Debug protection - breaks debugging tools
  debugProtection: false, // Disable for now - can break on some browsers
  
  // Disable console output (we keep some for debugging)
  disableConsoleOutput: false,
  
  // Identifier names generator
  identifierNamesGenerator: 'hexadecimal',
  
  // Identifiers prefix
  identifiersPrefix: '_ros',
  
  // Log calls - wraps console calls
  log: false,
  
  // Numbers to expressions
  numbersToExpressions: true,
  
  // Rename globals - keep public API accessible
  renameGlobals: false,
  
  // Reserved names - don't mangle the public API
  reservedNames: [
    'ROSWidget',
    '__ROS_CONFIG__',
    '__ROS_LICENSE__',
    '__ROS_INITIALIZED__',
    'open',
    'close', 
    'toggle',
    'send',
    'isOpen',
    'getSessionId'
  ],
  
  // Rotate string array
  rotateStringArray: true,
  
  // Self defending - crashes if code is modified
  selfDefending: true,
  
  // Shuffle string array
  shuffleStringArray: true,
  
  // Split strings
  splitStrings: true,
  splitStringsChunkLength: 8,
  
  // String array encoding
  stringArray: true,
  stringArrayCallsTransform: true,
  stringArrayCallsTransformThreshold: 0.5,
  stringArrayEncoding: ['base64'],
  stringArrayIndexShift: true,
  stringArrayRotate: true,
  stringArrayShuffle: true,
  stringArrayWrappersCount: 1,
  stringArrayWrappersChainedCalls: true,
  stringArrayWrappersParametersMaxCount: 2,
  stringArrayWrappersType: 'function',
  stringArrayThreshold: 0.75,
  
  // Transform object keys
  transformObjectKeys: true,
  
  // Unicode escape sequence
  unicodeEscapeSequence: false // Reduces size
};

try {
  const result = JavaScriptObfuscator.obfuscate(source, obfuscatorOptions);
  const obfuscatedCode = result.getObfuscatedCode();
  
  // Add header comment
  const header = `/**
 * ResonantOS Widget v${new Date().toISOString().slice(0,10).replace(/-/g,'')}
 * (c) ${new Date().getFullYear()} ResonantOS - All rights reserved
 * Unauthorized use, modification, or distribution is prohibited.
 */
`;
  const finalCode = header + obfuscatedCode;
  
  // Output path
  const outputDir = path.join(__dirname, '..', 'dist');
  if (!fs.existsSync(outputDir)) {
    fs.mkdirSync(outputDir, { recursive: true });
  }
  
  const outputPath = path.join(outputDir, 'widget-runtime.min.js');
  fs.writeFileSync(outputPath, finalCode);
  
  console.log('✅ Runtime widget built successfully!');
  console.log('   Output:', outputPath);
  console.log('   Original size:', (source.length / 1024).toFixed(2), 'KB');
  console.log('   Minified size:', (finalCode.length / 1024).toFixed(2), 'KB');
  console.log('   Compression:', ((1 - finalCode.length / source.length) * 100).toFixed(1) + '%');
  
  // Also output a version file
  const versionInfo = {
    version: 'v1.0.0',
    builtAt: new Date().toISOString(),
    sourceFile: 'widget-runtime.js',
    outputFile: 'widget-runtime.min.js',
    size: finalCode.length
  };
  
  fs.writeFileSync(
    path.join(outputDir, 'widget-runtime.version.json'),
    JSON.stringify(versionInfo, null, 2)
  );
  
} catch (error) {
  console.error('❌ Build failed:', error.message);
  process.exit(1);
}
