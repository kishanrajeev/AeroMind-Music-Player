const bubbles = [
  { left: '4%', size: 38, duration: 18, delay: 0 },
  { left: '11%', size: 16, duration: 13, delay: 4 },
  { left: '19%', size: 54, duration: 24, delay: 7 },
  { left: '28%', size: 22, duration: 15, delay: 2 },
  { left: '37%', size: 12, duration: 11, delay: 9 },
  { left: '48%', size: 30, duration: 20, delay: 5 },
  { left: '57%', size: 18, duration: 14, delay: 11 },
  { left: '66%', size: 46, duration: 22, delay: 1 },
  { left: '74%', size: 14, duration: 12, delay: 6 },
  { left: '82%', size: 34, duration: 19, delay: 3 },
  { left: '90%', size: 20, duration: 16, delay: 8 },
  { left: '96%', size: 60, duration: 26, delay: 12 },
]

export function Bubbles() {
  return (
    <div aria-hidden="true" className="pointer-events-none fixed inset-0 overflow-hidden">
      {bubbles.map((b, i) => (
        <span
          key={i}
          className="aero-bubble"
          style={{
            left: b.left,
            width: b.size,
            height: b.size,
            animationDuration: `${b.duration}s`,
            animationDelay: `${b.delay}s`,
          }}
        />
      ))}
    </div>
  )
}

export function Droplet({
  className,
  size = 14,
  style,
}: {
  className?: string
  size?: number
  style?: React.CSSProperties
}) {
  return (
    <span
      aria-hidden="true"
      className={`aero-droplet ${className ?? ''}`}
      style={{ width: size, height: size * 1.15, ...style }}
    />
  )
}
