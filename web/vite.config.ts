import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// 开发期把浏览器请求代理到本地 FastAPI 后端（8000），避免跨端口 CORS。
// /api   -> REST；/ws -> WebSocket 房态广播（ws:true 启用协议升级）。
export default defineConfig({
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
      "/ws": {
        target: "http://127.0.0.1:8000",
        ws: true,
        changeOrigin: true,
      },
    },
  },
});
