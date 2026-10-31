import type { NextConfig } from "next";

// Backend origin that /api/* is proxied to. Proxying keeps the session cookie first-party.
const apiProxyTarget = (
  process.env.API_PROXY_URL ||
  (process.env.NODE_ENV === "development" ? "http://localhost:8000" : "https://nimbus-api-l32h.onrender.com")
).replace(/\/$/, "");

const nextConfig: NextConfig = {
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${apiProxyTarget}/api/:path*` }];
  },
};

export default nextConfig;
