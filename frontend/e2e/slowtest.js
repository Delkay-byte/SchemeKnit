// Launch a tiny server that delays 50s then serves a real PDF; fetch it from Chrome page context
const http = require('http');
const fs = require('fs');
const { chromium } = require('playwright');

const PDF = fs.readFileSync('C:/Users/SAVIOUR/Documents/TeachFlow/backend/temp/ba/downloads/api-direct.pdf');
const server = http.createServer((req, res) => {
  res.setHeader('Access-Control-Allow-Origin', 'http://localhost:3000');
  if (req.method === 'OPTIONS') { res.end(); return; }
  setTimeout(() => {
    res.setHeader('Content-Type', 'application/pdf');
    res.setHeader('Content-Length', PDF.length);
    res.end(PDF);
  }, 50000);
});
server.listen(8123, async () => {
  const b = await chromium.launch({ channel: 'chrome' });
  const p = await (await b.newContext()).newPage();
  await p.goto('http://localhost:3000/login/', { waitUntil: 'domcontentloaded' });
  try {
    const r = await p.evaluate(async () => {
      const t0 = Date.now();
      const res = await fetch('http://127.0.0.1:8123/x', { method: 'GET' });
      const buf = await res.arrayBuffer();
      return { status: res.status, ms: Date.now() - t0, bytes: buf.byteLength };
    });
    console.log('Chrome 50s-delay PDF fetch:', JSON.stringify(r));
  } catch (e) {
    console.log('Chrome 50s-delay PDF fetch FAILED:', e.message);
  }
  server.close();
  await b.close();
});
