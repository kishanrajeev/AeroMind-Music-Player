// Runs before the page, in a sandboxed context (see electron/main.js).
'use strict'

const { contextBridge } = require('electron')

const blurMode = process.argv.includes('--aero-blur=glass') ? 'glass' : 'css'

// lib/desktop.ts reads this. It is absent in a normal browser.
contextBridge.exposeInMainWorld('aeroDesktop', { blurMode })

// CSS hooks (see app/globals.css). The native window draws the title bar, so the page drops its own.
window.addEventListener('DOMContentLoaded', () => {
  document.documentElement.dataset.aeroShell = 'desktop'
  document.documentElement.dataset.aeroBlur = blurMode
})
