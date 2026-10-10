import Image from 'next/image'
import { MusicPlayer } from '@/components/aero/music-player'
import { Bubbles } from '@/components/aero/bubbles'
import { Taskbar } from '@/components/aero/taskbar'

export default function Page() {
  return (
    <main className="relative flex min-h-dvh items-center justify-center overflow-hidden p-3 pb-16 sm:p-8 sm:pb-20">
      <Image
        src="/images/aero-wallpaper.jpg"
        alt=""
        fill
        priority
        sizes="100vw"
        className="-z-10 object-cover"
      />
      <div aria-hidden="true" className="absolute inset-0 -z-10 bg-gradient-to-b from-white/10 via-transparent to-cyan-200/20" />
      <Bubbles />
      <div className="relative z-10 w-full max-w-5xl">
        <MusicPlayer />
      </div>
      <Taskbar />
    </main>
  )
}
