'use strict';
// Serves a built webinar: the landing page, the MP4 (with Range support so
// browsers can seek), and a /register endpoint that appends opt-ins to a
// JSONL file. Node stdlib only — no express, nothing to install.

const fs = require('fs');
const path = require('path');
const http = require('http');
const log = require('./log');

const TYPES = {
  '.html': 'text/html; charset=utf-8',
  '.mp4': 'video/mp4',
  '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
  '.png': 'image/png', '.webp': 'image/webp', '.svg': 'image/svg+xml',
  '.css': 'text/css; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.vtt': 'text/vtt; charset=utf-8',
  '.mp3': 'audio/mpeg', '.ico': 'image/x-icon',
};

function sendVideo(req, res, filePath, size) {
  const range = req.headers.range;
  const type = TYPES['.mp4'];

  if (!range) {
    res.writeHead(200, {
      'Content-Length': size,
      'Content-Type': type,
      'Accept-Ranges': 'bytes',
    });
    return fs.createReadStream(filePath).pipe(res);
  }

  const m = /bytes=(\d*)-(\d*)/.exec(range);
  let start = m && m[1] ? parseInt(m[1], 10) : 0;
  let end = m && m[2] ? parseInt(m[2], 10) : size - 1;

  if (Number.isNaN(start) || Number.isNaN(end) || start > end || start >= size) {
    res.writeHead(416, { 'Content-Range': `bytes */${size}` });
    return res.end();
  }
  end = Math.min(end, size - 1);

  res.writeHead(206, {
    'Content-Range': `bytes ${start}-${end}/${size}`,
    'Accept-Ranges': 'bytes',
    'Content-Length': end - start + 1,
    'Content-Type': type,
  });
  fs.createReadStream(filePath, { start, end }).pipe(res);
}

function readBody(req, limit = 64 * 1024) {
  return new Promise((resolve, reject) => {
    let size = 0;
    const chunks = [];
    req.on('data', (c) => {
      size += c.length;
      if (size > limit) {
        reject(new Error('payload too large'));
        req.destroy();
        return;
      }
      chunks.push(c);
    });
    req.on('end', () => resolve(Buffer.concat(chunks).toString('utf8')));
    req.on('error', reject);
  });
}

// Deliberately permissive: rejecting real addresses loses a lead, and this is
// a capture form, not an auth system.
const looksLikeEmail = (s) => typeof s === 'string' && /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(s) && s.length < 320;

function createServer({ dir, registrationsPath, videoName }) {
  return http.createServer(async (req, res) => {
    const url = new URL(req.url, `http://${req.headers.host || 'localhost'}`);

    if (req.method === 'POST' && url.pathname === '/register') {
      try {
        const body = JSON.parse((await readBody(req)) || '{}');
        if (!looksLikeEmail(body.email)) {
          res.writeHead(400, { 'Content-Type': TYPES['.json'] });
          return res.end(JSON.stringify({ ok: false, error: 'invalid email' }));
        }
        const row = {
          email: String(body.email).trim().toLowerCase(),
          page: String(body.page || '/').slice(0, 200),
          at: new Date().toISOString(),
          ip: req.headers['x-forwarded-for'] || req.socket.remoteAddress || null,
          ua: String(req.headers['user-agent'] || '').slice(0, 300),
        };
        fs.appendFileSync(registrationsPath, JSON.stringify(row) + '\n');
        log.ok(`registered ${row.email}`);
        res.writeHead(200, { 'Content-Type': TYPES['.json'] });
        return res.end(JSON.stringify({ ok: true }));
      } catch (e) {
        res.writeHead(400, { 'Content-Type': TYPES['.json'] });
        return res.end(JSON.stringify({ ok: false, error: 'bad request' }));
      }
    }

    if (req.method !== 'GET' && req.method !== 'HEAD') {
      res.writeHead(405, { Allow: 'GET, HEAD, POST' });
      return res.end('Method not allowed');
    }

    if (url.pathname === '/health') {
      res.writeHead(200, { 'Content-Type': TYPES['.json'] });
      return res.end(JSON.stringify({ ok: true }));
    }

    let rel = decodeURIComponent(url.pathname);
    if (rel === '/' || rel === '') rel = '/index.html';
    if (rel === '/watch' || rel === '/webinar') rel = '/index.html';

    // Contain every request inside dir — no traversal out of the served tree.
    const filePath = path.join(dir, path.normalize(rel).replace(/^(\.\.[/\\])+/, ''));
    if (!filePath.startsWith(path.resolve(dir))) {
      res.writeHead(403);
      return res.end('Forbidden');
    }

    fs.stat(filePath, (err, stat) => {
      if (err || !stat.isFile()) {
        res.writeHead(404, { 'Content-Type': 'text/plain; charset=utf-8' });
        return res.end('Not found');
      }

      if (path.extname(filePath).toLowerCase() === '.mp4') {
        if (req.method === 'HEAD') {
          res.writeHead(200, {
            'Content-Length': stat.size,
            'Content-Type': TYPES['.mp4'],
            'Accept-Ranges': 'bytes',
          });
          return res.end();
        }
        return sendVideo(req, res, filePath, stat.size);
      }

      const type = TYPES[path.extname(filePath).toLowerCase()] || 'application/octet-stream';
      const headers = { 'Content-Type': type, 'Content-Length': stat.size };
      // The page changes on every rebuild; the video does not.
      headers['Cache-Control'] = type.startsWith('text/html') ? 'no-cache' : 'public, max-age=3600';

      res.writeHead(200, headers);
      if (req.method === 'HEAD') return res.end();
      fs.createReadStream(filePath).pipe(res);
    });
  });
}

function serve({ dir, port = 8080, host = '0.0.0.0', registrationsPath, videoName }) {
  if (!fs.existsSync(path.join(dir, 'index.html'))) {
    throw new Error(
      `No index.html in ${dir}.\n` +
      `Build the landing page first:  node bin/webinar-forge landing <project.json>`
    );
  }
  fs.mkdirSync(path.dirname(registrationsPath), { recursive: true });

  const server = createServer({ dir, registrationsPath, videoName });
  server.listen(port, host, () => {
    log.ok(`serving ${dir}`);
    log.info(`  http://localhost:${port}`);
    log.info(`  registrations -> ${registrationsPath}`);
  });
  return server;
}

module.exports = { serve, createServer };
