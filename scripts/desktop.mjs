// Launcher for the Electron desktop shell.
//
//   node scripts/desktop.mjs build                build the UI as a static export (.next-desktop/)
//   node scripts/desktop.mjs run                  open the app in a normal window
//   node scripts/desktop.mjs run --glass          see-through window; the compositor blurs the desktop
//   node scripts/desktop.mjs run --dev            load the dev server (npm run dev) instead of the export
//
// Any other flags are passed straight to Electron. The Python backend is not started here;
// run it as before (http://127.0.0.1:8000).
import { spawn, spawnSync } from 'node:child_process'
import fs from 'node:fs'
import { createRequire } from 'node:module'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const require = createRequire(import.meta.url)
const [command = 'run', ...flags] = process.argv.slice(2)
const launcherFlags = ['--glass', '--dev']

if (command === 'build') {
  // Next rewrites next-env.d.ts on every build; keep the committed version.
  const typesFile = path.join(root, 'next-env.d.ts')
  const committedTypes = fs.readFileSync(typesFile, 'utf8')
  const nextBin = path.join(path.dirname(require.resolve('next/package.json')), 'dist', 'bin', 'next')
  const result = spawnSync(process.execPath, [nextBin, 'build'], {
    cwd: root,
    stdio: 'inherit',
    env: { ...process.env, AERO_DESKTOP: '1' },
  })
  fs.writeFileSync(typesFile, committedTypes)
  process.exit(result.status ?? 1)
}

if (command !== 'run') {
  console.error(`Unknown command "${command}". Use "build" or "run".`)
  process.exit(1)
}

const electronArgs = ['.', `--aero-blur=${flags.includes('--glass') ? 'glass' : 'css'}`]
if (flags.includes('--dev')) electronArgs.push('--dev-url=http://localhost:3000')
// Electron only reads --ozone-platform from the command line: use native Wayland when the session has it.
if (process.platform === 'linux' && process.env.WAYLAND_DISPLAY) electronArgs.push('--ozone-platform=wayland')
electronArgs.push(...flags.filter((flag) => !launcherFlags.includes(flag)))

const child = spawn(require('electron'), electronArgs, { cwd: root, stdio: 'inherit' })
child.on('exit', (code, signal) => process.exit(code ?? (signal ? 1 : 0)))
