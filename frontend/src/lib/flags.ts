/// <reference types="vite/client" />

// Features still being tried. On for everyone at build time (VITE_DEVELOPING_STRIP=true), or for
// one browser with localStorage "sabq.flag.developingStrip" = "1".

function onInThisBrowser(name: string): boolean {
  try {
    return localStorage.getItem(`sabq.flag.${name}`) === "1";
  } catch {
    return false;
  }
}

export const developingStrip =
  import.meta.env.VITE_DEVELOPING_STRIP === "true" || onInThisBrowser("developingStrip");
