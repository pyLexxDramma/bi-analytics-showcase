import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  // Local `npm run build:check` uses a separate folder so it does not
  // corrupt the `.next` cache used by `npm run dev` (CSS/JS 404).
  distDir: process.env.NEXT_DIST_DIR || ".next",
  // Значок статуса роута в dev перекрывает нижнюю панель на телефоне
  devIndicators: { appIsrStatus: false },
};

export default nextConfig;
