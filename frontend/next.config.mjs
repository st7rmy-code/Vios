/** @type {import('next').NextConfig} */
const nextConfig = {
  // /api/v1/* проксирует route handler src/app/api/v1/[...path]: он добавляет токен из httpOnly cookie.
  output: "standalone",
};

export default nextConfig;
