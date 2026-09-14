/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  reactStrictMode: true,
  poweredByHeader: false,
  // La borne appelle l'API en relatif (/api/...) : même origine, pas de CORS, et
  // l'image ne dépend pas du nom de domaine. En Docker, API_INTERNAL_URL=http://api:8000.
  async rewrites() {
    const api = process.env.API_INTERNAL_URL || "http://localhost:8000";
    return [{ source: "/api/:path*", destination: `${api}/api/:path*` }];
  },
};

export default nextConfig;
