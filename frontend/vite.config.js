import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 3000,
    // ngrok (dev) ชี้มาที่ frontend → proxy /api + /webhook ไป backend ให้ domain เดียวครบ
    // (LIFF form เสิร์ฟจาก frontend, LINE webhook + REST API วิ่งผ่าน proxy ไป backend)
    allowedHosts: true,
    // กันไฟล์ metadata หลุดผ่าน dev server (ZAP เจอ /Dockerfile, /package.json)
    fs: {
      deny: [
        ".env*",
        "Dockerfile*",
        "package.json",
        "package-lock.json",
        "*.config.js",
      ],
    },
    headers: {
      "X-Frame-Options": "DENY",
      "X-Content-Type-Options": "nosniff",
      "Referrer-Policy": "strict-origin-when-cross-origin",
      "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
      "Cross-Origin-Resource-Policy": "same-origin",
    },
    proxy: {
      // ใน docker dev ตั้ง VITE_API_PROXY=http://backend:8000 (ดู .env.dev)
      "/api": {
        target: process.env.VITE_API_PROXY || "http://localhost:8000",
        changeOrigin: true,
      },
      "/webhook": {
        target: process.env.VITE_API_PROXY || "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
});
