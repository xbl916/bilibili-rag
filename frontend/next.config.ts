import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // 静态导出模式，便于 Docker 单镜像部署 (nginx 直接服务静态文件)
  output: 'export',
  // 静态导出基础路径
  basePath: '',
  // 禁用图片优化 (导出模式不需要) + 允许加载外部图片
  images: {
    unoptimized: true,
    remotePatterns: [
      {
        protocol: "https",
        hostname: "**.hdslb.com",
      },
      {
        protocol: "https",
        hostname: "**.bilivideo.com",
      },
      {
        protocol: "http",
        hostname: "localhost",
      },
    ],
  },
  // 环境变量
  env: {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL || "/api",
  },
  // 开发环境 API 代理 (本地开发时代理到后端)
  async rewrites() {
    return [
      {
        source: '/api/:path*',
        destination: 'http://localhost:8000/:path*',
      },
    ];
  },
};

export default nextConfig;