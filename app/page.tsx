import Image from 'next/image'
import { MusicPlayer } from '@/components/aero/music-player'
import { Bubbles } from '@/components/aero/bubbles'

export default function Page() {
  return (
    <main className="aero-page relative flex min-h-dvh items-center justify-center overflow-hidden p-3 sm:p-8">
      <Image
        src="/images/aero-wallpaper.jpg"
        alt=""
        fill
        priority
        sizes="100vw"
        className="aero-wallpaper -z-10 object-cover"
      />
      <div aria-hidden="true" className="aero-wallpaper-tint absolute inset-0 -z-10 bg-gradient-to-b from-white/10 via-transparent to-cyan-200/20" />
      <Bubbles />
      <div className="aero-player-slot relative z-10 w-full max-w-5xl">
        <MusicPlayer />
      </div>
    </main>
  )
}
