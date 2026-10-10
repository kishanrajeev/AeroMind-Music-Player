export type Song = {
  id: string
  title: string
  artist: string
  album: string
  cover: string
  duration: number
}

const covers = {
  aqua: '/images/album-aqua.png',
  meadow: '/images/album-meadow.png',
  orbit: '/images/album-orbit.png',
  koi: '/images/album-koi.png',
}

export const songs: Song[] = [
  { id: '1', title: 'Crystal Droplet', artist: 'Aqua Horizon', album: 'Liquid Sky', cover: covers.aqua, duration: 214 },
  { id: '2', title: 'Bubble Stream', artist: 'Aqua Horizon', album: 'Liquid Sky', cover: covers.aqua, duration: 187 },
  { id: '3', title: 'Glass Ocean', artist: 'Aqua Horizon', album: 'Liquid Sky', cover: covers.aqua, duration: 243 },
  { id: '4', title: 'Green Hills Forever', artist: 'Meadowlight', album: 'Dewpoint', cover: covers.meadow, duration: 198 },
  { id: '5', title: 'Morning Dew', artist: 'Meadowlight', album: 'Dewpoint', cover: covers.meadow, duration: 226 },
  { id: '6', title: 'Lens Flare Love', artist: 'Meadowlight', album: 'Dewpoint', cover: covers.meadow, duration: 175 },
  { id: '7', title: 'Aurora Ribbon', artist: 'Vista Dreams', album: 'Orbital Glass', cover: covers.orbit, duration: 261 },
  { id: '8', title: 'Translucent Orb', artist: 'Vista Dreams', album: 'Orbital Glass', cover: covers.orbit, duration: 204 },
  { id: '9', title: 'Sidebar Gadget', artist: 'Vista Dreams', album: 'Orbital Glass', cover: covers.orbit, duration: 168 },
  { id: '10', title: 'Koi Pond Reverie', artist: 'Tropical Tank', album: 'Aquarium Screensaver', cover: covers.koi, duration: 232 },
  { id: '11', title: 'Sunlit Caustics', artist: 'Tropical Tank', album: 'Aquarium Screensaver', cover: covers.koi, duration: 219 },
  { id: '12', title: 'Goldfish Glide', artist: 'Tropical Tank', album: 'Aquarium Screensaver', cover: covers.koi, duration: 191 },
]

export function formatTime(seconds: number) {
  const s = Math.max(0, Math.floor(seconds))
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
}
