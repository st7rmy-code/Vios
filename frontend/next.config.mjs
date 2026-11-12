/** @type {import('next').NextConfig} */
const backend = process.env.SVERKA_BACKEND_URL ?? "http://localhost:8000";

const nextConfig = {
  output: "standalone",
  async rewrites() {
    // Браузер ходит на тот же origin, Next проксирует в FastAPI: CORS не нужен.
    return [{ source: "/api/v1/:path*", destination: `${backend}/api/v1/:path*` }];
  },
};

export default nextConfig;
