// Electron shell for the Aero Media Player.
// Serves the static export from `npm run desktop:build` (.next-desktop/), or the dev server with --dev-url.
// It does not start the Python backend: that still runs separately on http://127.0.0.1:8000.
'use strict'

const fs = require('node:fs')
const path = require('node:path')
const { pathToFileURL } = require('node:url')
const { app, BrowserWindow, Menu, net, protocol, session } = require('electron')

const projectRoot = path.join(__dirname, '..')
const exportDir = path.join(projectRoot, '.next-desktop')
const iconPath = path.join(projectRoot, 'public', 'apple-icon.png')

// Sizes are for the player area itself (useContentSize below). The player needs 820px of height;
// the minimum leaves room for a native title bar (about 40px) when the compositor draws one.
const WINDOW_SIZE = { width: 1024, height: 840, minWidth: 900, minHeight: 860 }

const APP_ORIGIN = 'app://app'

// Flags from scripts/desktop.mjs: --aero-blur=glass|css and --dev-url=<url>.
function flagValue(name) {
  const prefix = `--${name}=`
  const hit = process.argv.find((arg) => arg.startsWith(prefix))
  return hit ? hit.slice(prefix.length) : null
}
const devUrl = flagValue('dev-url')
const blurMode = flagValue('aero-blur') === 'glass' ? 'glass' : 'css'

// Must be called before the app is ready.
protocol.registerSchemesAsPrivileged([
  { scheme: 'app', privileges: { standard: true, secure: true, supportFetchAPI: true } },
])
// Wayland app ID / desktop file name, so window managers such as niri can target the window.
app.setDesktopName('aero-media-player.desktop')

function isAppUrl(url) {
  const base = devUrl ? new URL(devUrl).origin : APP_ORIGIN
  return url === base || url.startsWith(`${base}/`)
}

// Serves the static export under app://app/.
function serveExport() {
  protocol.handle('app', (request) => {
    const requested = decodeURIComponent(new URL(request.url).pathname)
    const file = path.normalize(path.join(exportDir, requested === '/' ? 'index.html' : requested))
    if (!file.startsWith(exportDir + path.sep)) return new Response('Forbidden', { status: 403 })
    return net.fetch(pathToFileURL(file).toString())
  })
}

// Browser shortcuts for reload, DevTools, zoom, print and save. Blocked in the app build only.
function isBrowserShortcut(input) {
  if (input.type !== 'keyDown') return false
  const key = input.key.toLowerCase()
  if (key === 'f5' || key === 'f12') return true
  if (!(input.control || input.meta)) return false
  if (['r', '=', '+', '-', '0', 'p', 's'].includes(key)) return true
  return Boolean(input.shift) && ['i', 'j', 'c'].includes(key)
}

function createWindow() {
  const glass = blurMode === 'glass'
  const win = new BrowserWindow({
    ...WINDOW_SIZE,
    useContentSize: true,
    title: 'Aero Media Player',
    icon: iconPath,
    // The native title bar (title, minimize, maximize, close) belongs to the window, not the page.
    frame: true,
    transparent: glass,
    hasShadow: false,
    backgroundColor: glass ? '#00000000' : '#e2f1f8',
    show: false,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      sandbox: true,
      nodeIntegration: false,
      spellcheck: false,
      additionalArguments: [`--aero-blur=${blurMode}`],
    },
  })

  win.once('ready-to-show', () => win.show())

  // Browser behaviour that does not belong in an app window.
  win.webContents.setWindowOpenHandler(() => ({ action: 'deny' }))
  win.webContents.on('will-navigate', (event, url) => {
    if (!isAppUrl(url)) event.preventDefault()
  })
  win.webContents.setVisualZoomLevelLimits(1, 1)
  win.webContents.on('zoom-changed', () => win.webContents.setZoomLevel(0))
  if (!devUrl) {
    win.webContents.on('before-input-event', (event, input) => {
      if (isBrowserShortcut(input)) event.preventDefault()
    })
  }

  win.loadURL(devUrl ?? `${APP_ORIGIN}/`).catch((error) => console.error('Failed to load the UI:', error.message))
  return win
}

app.whenReady().then(() => {
  if (!devUrl) {
    if (!fs.existsSync(path.join(exportDir, 'index.html'))) {
      console.error('No UI build found in .next-desktop/. Run "npm run desktop:build" first.')
      app.exit(1)
      return
    }
    serveExport()
  }
  // Browser permission prompts (camera, notifications, ...) are never needed here.
  session.defaultSession.setPermissionRequestHandler((_webContents, _permission, callback) => callback(false))
  Menu.setApplicationMenu(null)
  createWindow()
})

app.on('window-all-closed', () => app.quit())
