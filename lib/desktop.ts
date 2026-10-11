/**
 * Bridge exposed by electron/preload.js when the UI runs in the desktop shell.
 * In a normal browser (`npm run dev`) it is absent.
 */
export type AeroDesktop = {
  /** 'glass' = see-through window (the compositor blurs the desktop); 'css' = blur inside the app. */
  blurMode: 'css' | 'glass'
}

declare global {
  interface Window {
    aeroDesktop?: AeroDesktop
  }
}

export function getDesktop(): AeroDesktop | undefined {
  return typeof window === 'undefined' ? undefined : window.aeroDesktop
}
