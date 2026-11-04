import http from 'node:http';
import { spawn } from 'node:child_process';
import fs from 'node:fs';

const CHROME_PATHS = [
  'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
  'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
];

function findBrowserBinary() {
  for (const p of CHROME_PATHS) {
    if (fs.existsSync(p)) return p;
  }
  return null;
}

const browserBin = findBrowserBinary();
if (!browserBin) {
  console.error('No supported Chromium browser found (checked Chrome and Edge).');
  process.exit(1);
}

const VITE_PORT = 5198;
const PROXY_PORT = 5199;

console.log(`Using Chromium browser: ${browserBin}`);
console.log('Starting Vite server for browser IndexedDB testing...');

// 1. Spawn Vite
const viteProc = spawn('cmd.exe', ['/c', 'npm', 'run', 'dev', '--', '--port', String(VITE_PORT)], {
  cwd: process.cwd().includes('frontend') ? process.cwd() : `${process.cwd()}\\frontend`,
  stdio: 'pipe',
  detached: false,
});

let viteCleanedUp = false;
function cleanup() {
  if (!viteCleanedUp) {
    viteCleanedUp = true;
    try {
      spawn('taskkill', ['/pid', String(viteProc.pid), '/f', '/t']);
    } catch {}
  }
}

process.on('exit', cleanup);
process.on('SIGINT', cleanup);
process.on('SIGTERM', cleanup);

// Wait for Vite to be ready
async function waitForVite(port, retries = 30) {
  for (let i = 0; i < retries; i++) {
    try {
      await new Promise((resolve, reject) => {
        const req = http.get(`http://localhost:${port}/`, (res) => {
          resolve(res.statusCode);
        });
        req.on('error', reject);
        req.setTimeout(500, () => {
          req.destroy();
          reject(new Error('timeout'));
        });
      });
      return true;
    } catch {
      await new Promise((r) => setTimeout(r, 200));
    }
  }
  return false;
}

const isReady = await waitForVite(VITE_PORT);
if (!isReady) {
  console.error('Vite server failed to start within 6 seconds.');
  cleanup();
  process.exit(1);
}
console.log(`Vite server ready on port ${VITE_PORT}. Setting up test reporter proxy...`);

// 2. Setup HTTP Proxy and Test Result Collector
let browserProc = null;

const resultPromise = new Promise((resolve, reject) => {
  const server = http.createServer((req, res) => {
    if (req.method === 'POST' && req.url === '/__test_results') {
      let body = '';
      req.on('data', (chunk) => {
        body += chunk;
      });
      req.on('end', () => {
        try {
          const data = JSON.parse(body);
          res.writeHead(200, { 'Content-Type': 'application/json' });
          res.end(JSON.stringify({ ok: true }));
          server.close();
          resolve(data);
        } catch (e) {
          reject(e);
        }
      });
      return;
    }

    // Proxy request to Vite
    const proxyReq = http.request(
      {
        hostname: 'localhost',
        port: VITE_PORT,
        path: req.url,
        method: req.method,
        headers: req.headers,
      },
      (proxyRes) => {
        res.writeHead(proxyRes.statusCode, proxyRes.headers);
        proxyRes.pipe(res);
      }
    );

    req.pipe(proxyReq);
    proxyReq.on('error', (err) => {
      res.writeHead(502);
      res.end('Proxy error: ' + err.message);
    });
  });

  server.listen(PROXY_PORT, () => {
    // 3. Launch Headless Browser
    console.log(`Launching headless Chromium at http://localhost:${PROXY_PORT}/test-indexeddb.html ...`);
    browserProc = spawn(browserBin, [
      '--headless=new',
      '--disable-gpu',
      '--no-sandbox',
      '--disable-dev-shm-usage',
      `http://localhost:${PROXY_PORT}/test-indexeddb.html`,
    ]);

    browserProc.on('error', (err) => {
      reject(new Error(`Failed to launch browser: ${err.message}`));
    });
  });

  setTimeout(() => {
    reject(new Error('Browser IndexedDB test suite timed out after 20 seconds'));
  }, 20000);
});

try {
  const result = await resultPromise;
  if (browserProc) {
    try {
      spawn('taskkill', ['/pid', String(browserProc.pid), '/f', '/t']);
    } catch {}
  }
  cleanup();

  console.log('\n--- REAL BROWSER INDEXEDDB TEST RESULTS ---');
  for (const t of result.results) {
    if (t.passed) {
      console.log(`✔ ${t.name}`);
    } else {
      console.log(`✖ ${t.name}`);
      console.error(`  Error: ${t.error}`);
    }
  }

  const passCount = result.results.filter((r) => r.passed).length;
  const totalCount = result.results.length;
  console.log(`\nTests: ${passCount} passed, ${totalCount - passCount} failed, ${totalCount} total`);

  if (!result.allPassed) {
    process.exit(1);
  }
  process.exit(0);
} catch (err) {
  console.error('\nBrowser test execution error:', err.message);
  if (browserProc) {
    try {
      spawn('taskkill', ['/pid', String(browserProc.pid), '/f', '/t']);
    } catch {}
  }
  cleanup();
  process.exit(1);
}
