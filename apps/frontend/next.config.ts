import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Standalone output for the production image (infra/k8s deploys this,
  // not the dev server the compose Dockerfile runs).
  output: "standalone",
};

export default nextConfig;
