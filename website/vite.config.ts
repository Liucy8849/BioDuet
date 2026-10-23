import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import { fileURLToPath } from "node:url";
export default defineConfig({
  plugins: [vue()],
  base: "./",
  build: {
    outDir: fileURLToPath(
      new URL("dist", import.meta.url),
    ),
    emptyOutDir: true,
    sourcemap: false,
  },
  server: { fs: { strict: true } },
});
