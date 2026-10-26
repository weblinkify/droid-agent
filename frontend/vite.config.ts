import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// The web demo runs entirely in the browser on mock data; the real tools live in the Python MCP server.
export default defineConfig({
  plugins: [react()],
  server: { port: 5173 },
});
