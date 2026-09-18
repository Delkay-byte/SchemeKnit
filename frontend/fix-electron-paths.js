const fs = require('fs');
const path = require('path');

const outDir = path.join(__dirname, 'out');

function fixPathsInFile(filePath) {
  let content = fs.readFileSync(filePath, 'utf8');
  
  // Replace absolute /_next/ paths with relative ./_next/
  content = content.replace(/href="\/_next\//g, 'href="./_next/');
  content = content.replace(/src="\/_next\//g, 'src="./_next/');
  content = content.replace(/href="\/_next\//g, 'href="./_next/');
  
  // Also fix the inline JSON data that contains asset paths
  content = content.replace(/"href":"\/_next\//g, '"href":"./_next/');
  content = content.replace(/"src":"\/_next\//g, '"src":"./_next/');
  content = content.replace(/"href": "\/_next\//g, '"href": "./_next/');
  content = content.replace(/"src": "\/_next\//g, '"src": "./_next/');
  
  // Fix the initialCanonicalUrl to be relative
  content = content.replace(/"initialCanonicalUrl":"\//g, '"initialCanonicalUrl":"./');
  
  fs.writeFileSync(filePath, content);
}

function walkDir(dir) {
  const files = fs.readdirSync(dir);
  for (const file of files) {
    const fullPath = path.join(dir, file);
    const stat = fs.statSync(fullPath);
    if (stat.isDirectory()) {
      walkDir(fullPath);
    } else if (file.endsWith('.html')) {
      fixPathsInFile(fullPath);
      console.log('Fixed:', fullPath);
    }
  }
}

console.log('Fixing asset paths for Electron file:// protocol...');
walkDir(outDir);
console.log('Done!');