/**
 * Opaque visitor id for public share pages (no auth, no PII).
 * Scoped per public slug so different links get independent ids by default.
 */

const keyFor = (publicSlug: string) => `docubase_public_visitor:${publicSlug}`;

export function getStoredVisitorId(publicSlug: string): string | null {
  try {
    const v = localStorage.getItem(keyFor(publicSlug));
    if (!v) return null;
    const t = v.trim();
    return t.length >= 8 ? t : null;
  } catch {
    return null;
  }
}

export function setStoredVisitorId(publicSlug: string, visitorId: string): void {
  try {
    localStorage.setItem(keyFor(publicSlug), visitorId.trim());
  } catch {
    /* ignore quota / private mode */
  }
}

export function clearStoredVisitorId(publicSlug: string): void {
  try {
    localStorage.removeItem(keyFor(publicSlug));
  } catch {
    /* ignore */
  }
}

export function generateVisitorId(): string {
  const c = globalThis.crypto as Crypto | undefined;
  if (c && typeof c.randomUUID === "function") {
    return c.randomUUID();
  }
  if (c && typeof c.getRandomValues === "function") {
    const bytes = new Uint8Array(16);
    c.getRandomValues(bytes);
    return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
  }
  return `anon-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`;
}
