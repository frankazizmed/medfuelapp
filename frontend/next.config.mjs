/** @type {import('next').NextConfig} */
const nextConfig = {
  async rewrites() {
    const backend = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000';
    return [
      {
        source: '/api/clinical-evidence/:path*',
        destination: `${backend}/clinical-evidence/:path*`,
      },
    ];
  },
};
export default nextConfig;
