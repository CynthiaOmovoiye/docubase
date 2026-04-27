import { useEffect, useState } from "react";

/**
 * Reactive breakpoint hook.
 *
 * Returns `true` when the viewport is at or below `breakpoint` pixels.
 * Subscribes to `matchMedia` change events so the value updates on resize
 * without polling.
 *
 * Safe to call during SSR — falls back to `false` when `window` is not
 * available.
 */
export function useIsMobile(breakpoint = 768): boolean {
  const [isMobile, setIsMobile] = useState<boolean>(() => {
    if (typeof window === "undefined") return false;
    return window.innerWidth <= breakpoint;
  });

  useEffect(() => {
    const mq = window.matchMedia(`(max-width: ${breakpoint}px)`);

    // Sync immediately in case the initial render ran at a different size
    setIsMobile(mq.matches);

    const handler = (e: MediaQueryListEvent) => setIsMobile(e.matches);
    mq.addEventListener("change", handler);
    return () => mq.removeEventListener("change", handler);
  }, [breakpoint]);

  return isMobile;
}
