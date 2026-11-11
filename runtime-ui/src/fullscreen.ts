import { useSyncExternalStore } from "react";

function subscribe(listener: () => void) {
  document.addEventListener("fullscreenchange", listener);
  return () => document.removeEventListener("fullscreenchange", listener);
}

/** Native fullscreen hides portals outside the active fullscreen element. */
export function useFullscreenElement() {
  return useSyncExternalStore(
    subscribe,
    () => document.fullscreenElement as HTMLElement | null,
    () => null,
  );
}
