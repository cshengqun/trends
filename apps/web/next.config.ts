import type { NextConfig } from "next";

const config: NextConfig = {
  output: "standalone",
  poweredByHeader: false,
  devIndicators: false,
  basePath: process.env.NEXT_PUBLIC_BASE_PATH || "",
};
export default config;
