"use strict";

const express = require("express");
const { createProxyMiddleware } = require("http-proxy-middleware");

const API_URL = process.env.STAY_API_INTERNAL_URL || "http://stay_django:8000";
const PORT = Number(process.env.PORT || 3000);
const APP_NAME = process.env.STAY_WEB_APP || "reception";

const app = express();

function forwardHostHeader(proxyReq, req) {
  const host = req.headers["x-forwarded-host"] || req.headers.host;
  if (host) {
    proxyReq.setHeader("Host", String(host).split(":")[0]);
  }
}

app.get("/health", (_req, res) => {
  res.json({ status: "ok", app: APP_NAME });
});

app.use(
  createProxyMiddleware({
    target: API_URL,
    pathFilter: "/api",
    changeOrigin: false,
    on: {
      proxyReq: (proxyReq, req) => {
        forwardHostHeader(proxyReq, req);
      },
    },
  }),
);

app.get("*", (req, res) => {
  const host = req.headers.host || "unknown";
  res.status(200).type("html").send(`<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><title>Stay.hr Reception</title></head>
<body>
  <h1>Stay.hr Reception</h1>
  <p>Host: <code>${host}</code></p>
  <p>Edge service is running. Reception UI will be served here.</p>
</body>
</html>`);
});

app.listen(PORT, () => {
  console.log(`${APP_NAME} listening on ${PORT}, API=${API_URL}`);
});
