const http = require('http');
const https = require('https');
const { URL } = require('url');

const TARGET = process.env.API_TARGET || 'https://studentroadmap-api-m5hqauiyxa-nw.a.run.app';
const PORT = Number(process.env.PORT || 8081);

const allowedHeaders = 'Content-Type, Authorization';
const allowedMethods = 'GET, POST, PUT, PATCH, DELETE, OPTIONS';

function setCorsHeaders(res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', allowedMethods);
  res.setHeader('Access-Control-Allow-Headers', allowedHeaders);
}

const server = http.createServer((req, res) => {
  setCorsHeaders(res);

  if (req.method === 'OPTIONS') {
    res.writeHead(204);
    res.end();
    return;
  }

  const targetUrl = new URL(req.url, TARGET);
  const isHttps = targetUrl.protocol === 'https:';
  const transport = isHttps ? https : http;

  const proxyReq = transport.request(
    targetUrl,
    {
      method: req.method,
      headers: {
        ...req.headers,
        host: targetUrl.host,
        origin: targetUrl.origin
      }
    },
    (proxyRes) => {
      setCorsHeaders(res);
      res.writeHead(proxyRes.statusCode || 500, proxyRes.headers);
      proxyRes.pipe(res, { end: true });
    }
  );

  proxyReq.on('error', (err) => {
    res.writeHead(502, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ error: 'Proxy error', details: err.message }));
  });

  req.pipe(proxyReq, { end: true });
});

server.listen(PORT, () => {
  console.log(`CORS proxy running on http://127.0.0.1:${PORT}`);
  console.log(`Forwarding to ${TARGET}`);
});
