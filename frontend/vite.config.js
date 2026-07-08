import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  optimizeDeps: {
    include: [
      'react',
      'react-dom',
      'axios',
      'lucide-react',
      'react-markdown',
    ],
    exclude: [],
  },
  server: {
    warmup: {
      clientFiles: ['./src/App.jsx', './src/components/*.jsx'],
    }
  }
})
