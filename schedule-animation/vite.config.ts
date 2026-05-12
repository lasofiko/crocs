import fs from 'node:fs'
import type { IncomingMessage, ServerResponse } from 'node:http'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import type { Plugin } from 'vite'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
/** Репозиторий crocs: родитель каталога schedule-animation */
const ARTIFACTS_DIR = path.resolve(__dirname, '..', 'artifacts')
const ARTIFACT_BASENAMES = new Set(['schedule.xlsx', 'staffing_requirements.xlsx', 'forecast.xlsx'])

function serveArtifactsFromRepoRoot(): Plugin {
  const middleware = (req: IncomingMessage, res: ServerResponse, next: () => void) => {
    const raw = (req.url ?? '').split('?')[0] ?? ''
    if (!raw.startsWith('/crocs-artifacts/')) {
      next()
      return
    }
    const name = path.basename(decodeURIComponent(raw))
    if (!ARTIFACT_BASENAMES.has(name)) {
      next()
      return
    }
    const filePath = path.join(ARTIFACTS_DIR, name)
    if (!fs.existsSync(filePath)) {
      next()
      return
    }
    res.setHeader(
      'Content-Type',
      'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    const stream = fs.createReadStream(filePath)
    stream.on('error', () => {
      if (!res.headersSent) {
        res.statusCode = 500
      }
      res.end()
    })
    stream.pipe(res)
  }

  return {
    name: 'serve-crocs-artifacts',
    enforce: 'pre',
    configureServer(server) {
      server.middlewares.use(middleware)
    },
    configurePreviewServer(server) {
      server.middlewares.use(middleware)
    },
  }
}

// https://vite.dev/config/
const apiProxy = {
  '/api': {
    target: 'http://127.0.0.1:8000',
    changeOrigin: true,
  },
} as const

// https://vite.dev/config/
export default defineConfig({
  plugins: [serveArtifactsFromRepoRoot(), react()],
  server: {
    proxy: { ...apiProxy },
    fs: {
      allow: [path.resolve(__dirname, '..')],
    },
  },
  preview: {
    proxy: { ...apiProxy },
  },
})
