'use client'

import Image, { type ImageProps } from 'next/image'
import { useState } from 'react'

type CoverImageProps = Omit<ImageProps, 'src' | 'onError'> & {
  src: string
  fallback: string
}

/** next/image that swaps to a fallback cover when the real one fails to load. */
export function CoverImage({ src, fallback, alt, ...props }: CoverImageProps) {
  const [trackedSrc, setTrackedSrc] = useState(src)
  const [failed, setFailed] = useState(false)

  if (src !== trackedSrc) {
    setTrackedSrc(src)
    setFailed(false)
  }

  return (
    <Image
      {...props}
      src={failed ? fallback : src}
      alt={alt}
      onError={() => setFailed(true)}
    />
  )
}
