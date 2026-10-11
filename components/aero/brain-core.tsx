'use client'

import { useEffect, useRef } from 'react'
import { KC_COUNT } from '@/lib/brain'

/*
 * Canvas centrepiece of the Mushroom Body view.
 *
 * Every dot is one Kenyon cell, fixed to the same point on a slow-turning sphere:
 *   - glow    → how hard the cell fires for the current song
 *   - colour  → the learned weight (cyan liked, amber avoided)
 *   - lines   → cells that fire together are wired together
 *   - cursor  → tilts the sphere, pushes nearby cells aside and lights their wires
 *
 * The faint drifting grid behind it samples the full 50×40 weight matrix, so the
 * learned state is always on screen even where the sphere hides it.
 *
 * The component reads only the numbers /brain_state returns (`kc_activity`,
 * `weights`) plus the feedback pulse from lib/brain.ts, so it stays a dumb view
 * over the live backend state.
 */

const TAU = Math.PI * 2
const GOLDEN_ANGLE = Math.PI * (3 - Math.sqrt(5))

/** The full weight matrix is 50 × 40; the background field samples it coarsely. */
const MATRIX_COLUMNS = 50
const MATRIX_ROWS = 40
const FIELD_COLUMNS = 26
const FIELD_ROWS = 15

/** Cells closer than this on the sphere get a wire (≈ two dot spacings). */
const WIRE_DISTANCE_SQUARED = 0.16 * 0.16
const WIRES_PER_CELL = 3
const MAX_WIRES = 1600

/** Deterministic unit-sphere positions: cell i is always the same dot. */
const BASE = (() => {
  const positions = new Float32Array(KC_COUNT * 3)
  for (let i = 0; i < KC_COUNT; i++) {
    const y = 1 - (i / (KC_COUNT - 1)) * 2
    const ring = Math.sqrt(Math.max(0, 1 - y * y))
    const theta = i * GOLDEN_ANGLE
    positions[i * 3] = Math.cos(theta) * ring
    positions[i * 3 + 1] = y
    positions[i * 3 + 2] = Math.sin(theta) * ring
  }
  return positions
})()

function rgba(hex: string, alpha: number): string {
  const value = Number.parseInt(hex.slice(1), 16)
  return `rgba(${(value >> 16) & 255}, ${(value >> 8) & 255}, ${value & 255}, ${alpha})`
}

/** Pre-rendered glow so each cell is one drawImage instead of a gradient per frame. */
function makeSprite(hex: string): HTMLCanvasElement {
  const size = 64
  const sprite = document.createElement('canvas')
  sprite.width = size
  sprite.height = size
  const ctx = sprite.getContext('2d')
  if (ctx) {
    const gradient = ctx.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2)
    gradient.addColorStop(0, rgba(hex, 1))
    gradient.addColorStop(0.3, rgba(hex, 0.6))
    gradient.addColorStop(0.65, rgba(hex, 0.14))
    gradient.addColorStop(1, rgba(hex, 0))
    ctx.fillStyle = gradient
    ctx.fillRect(0, 0, size, size)
  }
  return sprite
}

export type BrainCoreProps = {
  /** KC_COUNT firing strengths for the current song; 0 = silent. */
  activity: number[]
  /** KC_COUNT learned weights, negative (avoided) … positive (liked). */
  weights: number[]
  /** Largest |weight| in `weights`; real weights start tiny, so visuals scale to this. */
  weightScale: number
  /** Newest learning event; `id` bumps once per skip or listen-through. */
  pulse: { id: number; changed: number[] } | null
  /** Predicted enjoyment, 0…1, drawn as the ring around the sphere. */
  enjoyment: number
  /** Screen-reader description of what the canvas currently shows. */
  label: string
  className?: string
}

export function BrainCore({ activity, weights, weightScale, pulse, enjoyment, label, className }: BrainCoreProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const dataRef = useRef({ activity, weights, weightScale, enjoyment })
  const activeRef = useRef<number[]>([])
  const wiresRef = useRef(new Int32Array(0))
  const flashRef = useRef(new Float32Array(KC_COUNT))
  const seenPulseRef = useRef(0)
  const waveRef = useRef(-1e9)

  // Keep the newest brain state for the animation loop without restarting it,
  // and turn every new feedback event into a wave + a flash on the changed cells.
  useEffect(() => {
    dataRef.current = { activity, weights, weightScale, enjoyment }
    if (pulse && pulse.id !== seenPulseRef.current) {
      seenPulseRef.current = pulse.id
      waveRef.current = performance.now()
      for (const cell of pulse.changed) {
        if (cell >= 0 && cell < KC_COUNT) flashRef.current[cell] = 1
      }
    }
  }, [activity, weights, weightScale, enjoyment, pulse])

  // Wire together the cells firing for this song: the nearest neighbours on the
  // sphere within a threshold, up to three per cell.
  useEffect(() => {
    const active: number[] = []
    for (let i = 0; i < activity.length && i < KC_COUNT; i++) {
      if (activity[i] > 0) active.push(i)
    }
    activeRef.current = active

    const pairs: number[] = []
    for (let a = 0; a < active.length; a++) {
      const i = active[a] * 3
      const candidates: { cell: number; distance: number }[] = []
      for (let b = a + 1; b < active.length; b++) {
        const j = active[b] * 3
        const dx = BASE[j] - BASE[i]
        const dy = BASE[j + 1] - BASE[i + 1]
        const dz = BASE[j + 2] - BASE[i + 2]
        const distance = dx * dx + dy * dy + dz * dz
        if (distance < WIRE_DISTANCE_SQUARED) candidates.push({ cell: active[b], distance })
      }
      candidates.sort((p, q) => p.distance - q.distance)
      for (let c = 0; c < Math.min(WIRES_PER_CELL, candidates.length); c++) {
        if (pairs.length >= MAX_WIRES * 2) break
        pairs.push(active[a], candidates[c].cell)
      }
    }
    wiresRef.current = Int32Array.from(pairs)
  }, [activity])

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    const sprites = {
      cyan: makeSprite('#2fd3ff'),
      amber: makeSprite('#ffb020'),
      white: makeSprite('#eafcff'),
    }

    let width = 1
    let height = 1
    const resize = () => {
      const rect = canvas.getBoundingClientRect()
      width = Math.max(1, rect.width)
      height = Math.max(1, rect.height)
      const dpr = Math.min(2, window.devicePixelRatio || 1)
      canvas.width = Math.round(width * dpr)
      canvas.height = Math.round(height * dpr)
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    }
    resize()
    const observer = new ResizeObserver(resize)
    observer.observe(canvas)

    // Cursor state, in canvas pixels.
    const pointer = { x: width / 2, y: height / 2, inside: false }
    const onPointerMove = (event: PointerEvent) => {
      const rect = canvas.getBoundingClientRect()
      pointer.x = ((event.clientX - rect.left) / rect.width) * width
      pointer.y = ((event.clientY - rect.top) / rect.height) * height
      pointer.inside = true
    }
    const onPointerLeave = () => {
      pointer.inside = false
    }
    canvas.addEventListener('pointermove', onPointerMove)
    canvas.addEventListener('pointerleave', onPointerLeave)

    // Per-frame scratch buffers: projected positions, depth and cursor shove.
    const screenX = new Float32Array(KC_COUNT)
    const screenY = new Float32Array(KC_COUNT)
    const screenDepth = new Float32Array(KC_COUNT)
    const shoveX = new Float32Array(KC_COUNT)
    const shoveY = new Float32Array(KC_COUNT)
    // Fixed-size "five nearest firing cells to the cursor" buffers.
    const nearestCell = new Int32Array(5)
    const nearestDistance = new Float32Array(5)

    let smoothX = 0
    let smoothY = 0
    let smoothEnjoyment = 0
    let elapsed = 0
    let last = performance.now()
    let frame = 0

    const draw = (now: number) => {
      frame = requestAnimationFrame(draw)
      const dt = Math.min(0.05, Math.max(0.001, (now - last) / 1000))
      last = now
      if (!reduceMotion) elapsed += dt

      const data = dataRef.current
      const activity = data.activity
      const weights = data.weights
      // Real MBON weights start around eta (~0.005), so normalise to the largest
      // magnitude actually present; cold-start (all zero) falls back to dust.
      const weightScale = Math.max(data.weightScale, 1e-9)
      const wires = wiresRef.current
      const active = activeRef.current
      const flash = flashRef.current

      const cx = width * 0.5
      const cy = height * 0.5
      const minDim = Math.min(width, height)
      const sphereR = minDim * 0.355
      const ringR = minDim * 0.45
      const cursorR = Math.max(64, minDim * 0.17)
      const cursorR2 = cursorR * cursorR
      const flashDecay = Math.exp(-dt * 2.6)
      const shoveDecay = Math.exp(-dt * 3.4)
      const spring = Math.min(1, dt * 4)

      // The pointer tilts and stirs; it relaxes back to rest when it leaves.
      const targetX = pointer.inside ? (pointer.x / width) * 2 - 1 : 0
      const targetY = pointer.inside ? (pointer.y / height) * 2 - 1 : 0
      smoothX += (targetX - smoothX) * spring
      smoothY += (targetY - smoothY) * spring
      smoothEnjoyment += (data.enjoyment - smoothEnjoyment) * Math.min(1, dt * 5)

      const rotY = elapsed * 0.12 + smoothX * 1.05
      const rotX = smoothY * 0.55
      const cosY = Math.cos(rotY)
      const sinY = Math.sin(rotY)
      const cosX = Math.cos(rotX)
      const sinX = Math.sin(rotX)
      const parallaxX = smoothX * 8
      const parallaxY = smoothY * 8

      const waveAge = (now - waveRef.current) / 1000
      const waveActive = waveAge >= 0 && waveAge < 1.1
      const waveR = sphereR * (0.12 + 1.35 * Math.min(1, waveAge / 1.1))

      ctx.clearRect(0, 0, width, height)

      // --- soft glow behind the sphere --------------------------------------
      const backdrop = ctx.createRadialGradient(cx, cy, 0, cx, cy, minDim * 0.75)
      backdrop.addColorStop(0, 'rgba(47, 211, 255, 0.11)')
      backdrop.addColorStop(0.55, 'rgba(10, 80, 140, 0.05)')
      backdrop.addColorStop(1, 'rgba(3, 20, 40, 0)')
      ctx.fillStyle = backdrop
      ctx.fillRect(0, 0, width, height)

      // --- drifting weight matrix behind everything -------------------------
      const pad = 14
      const stepX = (width - pad * 2) / (FIELD_COLUMNS - 1)
      const stepY = (height - pad * 2) / (FIELD_ROWS - 1)
      for (let row = 0; row < FIELD_ROWS; row++) {
        for (let col = 0; col < FIELD_COLUMNS; col++) {
          const cell =
            Math.min(MATRIX_ROWS - 1, Math.floor((row / FIELD_ROWS) * MATRIX_ROWS)) * MATRIX_COLUMNS +
            Math.min(MATRIX_COLUMNS - 1, Math.floor((col / FIELD_COLUMNS) * MATRIX_COLUMNS))
          const firing = activity[cell] ?? 0
          const weight = weights[cell] ?? 0
          const strength = Math.min(1, Math.abs(weight) / weightScale)
          const drift = 2 + 5 * strength
          const speed = 0.35 + 0.9 * (1 - strength)
          const x = pad + col * stepX + Math.sin(elapsed * speed + row * 0.9 + col * 0.45) * drift
          const y = pad + row * stepY + Math.cos(elapsed * speed * 0.85 + col * 1.1) * drift

          let brightness = 0.035 + 0.13 * strength
          if (firing > 0) brightness += 0.3 * firing
          if (pointer.inside) {
            const dx = x - pointer.x
            const dy = y - pointer.y
            const d2 = dx * dx + dy * dy
            if (d2 < cursorR2) brightness += 0.3 * (1 - Math.sqrt(d2) / cursorR)
          }
          if (waveActive) {
            const delta = (Math.hypot(x - cx, y - cy) - waveR) / (sphereR * 0.18)
            brightness += 0.45 * Math.exp(-delta * delta) * (1 - waveAge / 1.1)
          }

          if (firing > 0) ctx.fillStyle = `rgba(220, 252, 255, ${Math.min(0.8, brightness)})`
          else if (weight > 0) ctx.fillStyle = `rgba(47, 211, 255, ${Math.min(0.7, brightness)})`
          else if (weight < 0) ctx.fillStyle = `rgba(255, 176, 32, ${Math.min(0.7, brightness)})`
          else ctx.fillStyle = `rgba(190, 235, 255, ${Math.min(0.45, brightness)})`

          const size = 1.4 + 2.2 * strength + (firing > 0 ? 1.2 : 0)
          ctx.fillRect(x - size / 2, y - size / 2, size, size)
        }
      }

      // --- project the sphere and let the cursor shove cells around ---------
      for (let i = 0; i < KC_COUNT; i++) {
        const base = i * 3
        const bx = BASE[base]
        const by = BASE[base + 1]
        const bz = BASE[base + 2]
        const x1 = bx * cosY + bz * sinY
        const z1 = bz * cosY - bx * sinY
        const y1 = by * cosX - z1 * sinX
        const z2 = z1 * cosX + by * sinX
        const perspective = 1 / (1 + z2 * 0.32)
        const rawX = cx + x1 * sphereR * perspective + parallaxX
        const rawY = cy + y1 * sphereR * perspective + parallaxY

        shoveX[i] *= shoveDecay
        shoveY[i] *= shoveDecay
        if (pointer.inside) {
          const dx = rawX - pointer.x
          const dy = rawY - pointer.y
          const d2 = dx * dx + dy * dy
          if (d2 < cursorR2 && d2 > 0.01) {
            const d = Math.sqrt(d2)
            const push = (1 - d / cursorR) ** 2 * 340 * dt
            shoveX[i] += (dx / d) * push - (dy / d) * push * 0.6
            shoveY[i] += (dy / d) * push + (dx / d) * push * 0.6
          }
        }
        const shoveLen = shoveX[i] * shoveX[i] + shoveY[i] * shoveY[i]
        if (shoveLen > 1600) {
          const scale = 40 / Math.sqrt(shoveLen)
          shoveX[i] *= scale
          shoveY[i] *= scale
        }

        screenX[i] = rawX + shoveX[i]
        screenY[i] = rawY + shoveY[i]
        // 0 = far side, 1 = nearest the viewer; also folds in perspective size.
        screenDepth[i] = perspective * (0.35 + 0.65 * (1 - z2) * 0.5)
        flash[i] *= flashDecay
      }

      // --- cursor spotlight under the sphere ---------------------------------
      if (pointer.inside) {
        const aura = ctx.createRadialGradient(pointer.x, pointer.y, 0, pointer.x, pointer.y, cursorR)
        aura.addColorStop(0, 'rgba(210, 250, 255, 0.15)')
        aura.addColorStop(0.55, 'rgba(47, 211, 255, 0.06)')
        aura.addColorStop(1, 'rgba(47, 211, 255, 0)')
        ctx.fillStyle = aura
        ctx.fillRect(pointer.x - cursorR, pointer.y - cursorR, cursorR * 2, cursorR * 2)
      }

      // --- wires between firing cells ----------------------------------------
      ctx.lineCap = 'round'
      for (let e = 0; e < wires.length; e += 2) {
        const i = wires[e]
        const j = wires[e + 1]
        const depth = (screenDepth[i] + screenDepth[j]) * 0.5
        const midX = (screenX[i] + screenX[j]) * 0.5
        const midY = (screenY[i] + screenY[j]) * 0.5
        let boost = 0
        if (pointer.inside) {
          const dx = midX - pointer.x
          const dy = midY - pointer.y
          const d2 = dx * dx + dy * dy
          if (d2 < cursorR2) boost = 1 - Math.sqrt(d2) / cursorR
        }
        const shimmer = reduceMotion ? 0.6 : 0.55 + 0.45 * Math.sin(elapsed * 2.2 + (i + j) * 0.15)
        const alpha = (0.07 + 0.28 * depth) * shimmer + boost * 0.4
        if (alpha < 0.015) continue
        ctx.strokeStyle = `rgba(120, 226, 255, ${alpha.toFixed(3)})`
        ctx.lineWidth = 0.8 + 1.8 * depth + boost * 1.4
        ctx.beginPath()
        ctx.moveTo(screenX[i], screenY[i])
        ctx.lineTo(screenX[j], screenY[j])
        ctx.stroke()
      }

      // --- wires from the cursor to the nearest firing cells -----------------
      nearestCell.fill(-1)
      nearestDistance.fill(Infinity)
      if (pointer.inside) {
        for (let a = 0; a < active.length; a++) {
          const i = active[a]
          const dx = screenX[i] - pointer.x
          const dy = screenY[i] - pointer.y
          const d2 = dx * dx + dy * dy
          let slot = -1
          for (let s = 0; s < nearestCell.length; s++) {
            if (d2 < nearestDistance[s]) {
              slot = s
              break
            }
          }
          if (slot >= 0) {
            for (let s = nearestCell.length - 1; s > slot; s--) {
              nearestDistance[s] = nearestDistance[s - 1]
              nearestCell[s] = nearestCell[s - 1]
            }
            nearestDistance[slot] = d2
            nearestCell[slot] = i
          }
        }
        for (let s = 0; s < nearestCell.length; s++) {
          const i = nearestCell[s]
          if (i < 0) continue
          const alpha = 0.32 * (1 - Math.sqrt(nearestDistance[s]) / cursorR)
          if (alpha <= 0.01) continue
          ctx.strokeStyle = `rgba(200, 255, 235, ${alpha.toFixed(3)})`
          ctx.lineWidth = 1
          ctx.beginPath()
          ctx.moveTo(pointer.x, pointer.y)
          ctx.lineTo(screenX[i], screenY[i])
          ctx.stroke()
        }
        ctx.strokeStyle = 'rgba(220, 255, 255, 0.7)'
        ctx.lineWidth = 1
        ctx.beginPath()
        ctx.arc(pointer.x, pointer.y, 3, 0, TAU)
        ctx.stroke()
      }

      // --- the cells themselves ----------------------------------------------
      for (let i = 0; i < KC_COUNT; i++) {
        const firing = activity[i] ?? 0
        const weight = weights[i] ?? 0
        const depth = screenDepth[i]
        const afterglow = flash[i]
        let sprite: HTMLCanvasElement
        let size: number
        let alpha: number

        if (firing > 0) {
          sprite = sprites.white
          size = (4 + 6 * firing + 6 * afterglow) * depth
          alpha = (0.55 + 0.45 * firing) * (0.45 + 0.55 * depth) + afterglow * 0.55
        } else {
          const strength = Math.min(1, Math.abs(weight) / weightScale)
          if (strength < 0.05) {
            sprite = sprites.cyan
            size = 2.4 * depth
            alpha = 0.05 * depth
          } else {
            sprite = weight > 0 ? sprites.cyan : sprites.amber
            size = (2.8 + 5.5 * strength) * depth
            alpha = (0.16 + 0.55 * strength) * (0.45 + 0.55 * depth)
          }
        }

        if (pointer.inside) {
          const dx = screenX[i] - pointer.x
          const dy = screenY[i] - pointer.y
          const d2 = dx * dx + dy * dy
          if (d2 < cursorR2) {
            const glow = 1 - Math.sqrt(d2) / cursorR
            alpha += glow * 0.5
            size += glow * 3
          }
        }
        if (alpha <= 0.01 || size <= 0.5) continue
        ctx.globalAlpha = Math.min(1, alpha)
        ctx.drawImage(sprite, screenX[i] - size / 2, screenY[i] - size / 2, size, size)
      }
      ctx.globalAlpha = 1

      // --- calm the dots behind the central readout for contrast --------------
      const centerVignette = ctx.createRadialGradient(cx, cy, 0, cx, cy, minDim * 0.24)
      centerVignette.addColorStop(0, 'rgba(4, 30, 58, 0.55)')
      centerVignette.addColorStop(0.6, 'rgba(4, 30, 58, 0.28)')
      centerVignette.addColorStop(1, 'rgba(4, 30, 58, 0)')
      ctx.fillStyle = centerVignette
      ctx.fillRect(cx - minDim * 0.24, cy - minDim * 0.24, minDim * 0.48, minDim * 0.48)

      // --- predicted-enjoyment ring ------------------------------------------
      ctx.lineWidth = 4
      ctx.strokeStyle = 'rgba(190, 240, 255, 0.16)'
      ctx.beginPath()
      ctx.arc(cx, cy, ringR, 0, TAU)
      ctx.stroke()

      const start = -Math.PI / 2
      const sweep = TAU * Math.max(0, Math.min(1, smoothEnjoyment))
      ctx.strokeStyle = 'rgba(190, 240, 255, 0.28)'
      ctx.lineWidth = 1
      for (let tick = 0; tick < 12; tick++) {
        const angle = start + (tick / 12) * TAU
        ctx.beginPath()
        ctx.moveTo(cx + Math.cos(angle) * (ringR - 6), cy + Math.sin(angle) * (ringR - 6))
        ctx.lineTo(cx + Math.cos(angle) * (ringR + 6), cy + Math.sin(angle) * (ringR + 6))
        ctx.stroke()
      }

      if (sweep > 0.001) {
        const gradient = ctx.createLinearGradient(cx - ringR, cy + ringR, cx + ringR, cy - ringR)
        gradient.addColorStop(0, rgba('#2fd3ff', 0.9))
        gradient.addColorStop(1, rgba('#9be22d', 0.9))
        ctx.strokeStyle = gradient
        ctx.lineWidth = 5
        ctx.lineCap = 'round'
        ctx.shadowColor = 'rgba(47, 211, 255, 0.75)'
        ctx.shadowBlur = 12
        ctx.beginPath()
        ctx.arc(cx, cy, ringR, start, start + sweep)
        ctx.stroke()
        ctx.shadowBlur = 0

        const tip = start + sweep
        ctx.fillStyle = '#f2fdff'
        ctx.beginPath()
        ctx.arc(cx + Math.cos(tip) * ringR, cy + Math.sin(tip) * ringR, 3.4, 0, TAU)
        ctx.fill()
      }

      // --- learning shockwave -------------------------------------------------
      if (waveActive) {
        ctx.strokeStyle = `rgba(180, 255, 130, ${0.5 * (1 - waveAge / 1.1)})`
        ctx.lineWidth = 2
        ctx.beginPath()
        ctx.arc(cx, cy, waveR, 0, TAU)
        ctx.stroke()
      }
    }

    frame = requestAnimationFrame(draw)

    return () => {
      cancelAnimationFrame(frame)
      observer.disconnect()
      canvas.removeEventListener('pointermove', onPointerMove)
      canvas.removeEventListener('pointerleave', onPointerLeave)
    }
  }, [])

  return (
    <canvas
      ref={canvasRef}
      role="img"
      aria-label={label}
      className={`size-full touch-none ${className ?? ''}`}
    />
  )
}
