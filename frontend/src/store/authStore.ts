/**
 * Auth store — Zustand.
 *
 * Access token: memory only (never written to any browser storage).
 * Refresh token: sessionStorage only — survives page reloads and back/forward
 *   navigation within the same tab, but is cleared when the tab closes.
 *   This is the standard SPA approach: access tokens stay XSS-safe in memory,
 *   and the refresh token is scoped to the session so users aren't silently
 *   logged out on every reload.
 *
 * On startup, call init() once. It reads the refresh token from sessionStorage
 * and silently obtains a fresh access token, restoring the authenticated
 * session without requiring the user to log in again.
 */

import { create } from "zustand";
import { api, setAccessToken, clearAccessToken } from "@/lib/api";

const REFRESH_TOKEN_KEY = "oe_rt";

function saveRefreshToken(token: string) {
  sessionStorage.setItem(REFRESH_TOKEN_KEY, token);
}

function loadRefreshToken(): string | null {
  return sessionStorage.getItem(REFRESH_TOKEN_KEY);
}

function clearStoredRefreshToken() {
  sessionStorage.removeItem(REFRESH_TOKEN_KEY);
}

export interface AuthUser {
  id: string;
  email: string;
  display_name: string | null;
  is_active: boolean;
  is_verified: boolean;
  is_superuser: boolean;
  created_at: string;
}

interface AuthState {
  user: AuthUser | null;
  refreshToken: string | null;
  isLoading: boolean;
  isInitialised: boolean;

  // Actions
  init: () => Promise<void>;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, display_name?: string) => Promise<void>;
  logout: () => Promise<void>;
  refreshSession: () => Promise<void>;
  fetchMe: () => Promise<void>;
}

export const useAuthStore = create<AuthState>((set, get) => ({
  user: null,
  refreshToken: null,
  isLoading: false,
  isInitialised: false,

  /**
   * Call once on application mount.
   *
   * Reads any persisted refresh token from sessionStorage and attempts a
   * silent token exchange to restore the session. If no token is stored (or
   * the token is expired / revoked) the user is treated as logged out and
   * isInitialised is set to true so RequireAuth can render immediately.
   */
  init: async () => {
    const stored = loadRefreshToken();
    if (!stored) {
      set({ isInitialised: true });
      return;
    }
    set({ refreshToken: stored });
    await get().refreshSession();
  },

  login: async (email, password) => {
    set({ isLoading: true });
    try {
      const { data } = await api.post<{ access_token: string; refresh_token: string }>(
        "/users/login",
        { email, password }
      );
      setAccessToken(data.access_token);
      saveRefreshToken(data.refresh_token);
      set({ refreshToken: data.refresh_token });
      await get().fetchMe();
    } finally {
      set({ isLoading: false });
    }
  },

  register: async (email, password, display_name) => {
    set({ isLoading: true });
    try {
      const { data } = await api.post<{ access_token: string; refresh_token: string }>(
        "/users/register",
        { email, password, display_name: display_name || undefined }
      );
      setAccessToken(data.access_token);
      saveRefreshToken(data.refresh_token);
      set({ refreshToken: data.refresh_token });
      await get().fetchMe();
    } finally {
      set({ isLoading: false });
    }
  },

  logout: async () => {
    const { refreshToken } = get();
    // Revoke the refresh token server-side before clearing local state so a
    // stolen token cannot be replayed after the user logs out.
    if (refreshToken) {
      try {
        await api.post("/users/logout", { refresh_token: refreshToken });
      } catch {
        // Best-effort — clear local state regardless of network failure
      }
    }
    clearAccessToken();
    clearStoredRefreshToken();
    set({ user: null, refreshToken: null, isInitialised: true });
  },

  refreshSession: async () => {
    const { refreshToken } = get();
    if (!refreshToken) {
      set({ isInitialised: true });
      return;
    }
    try {
      const { data } = await api.post<{ access_token: string; refresh_token: string }>(
        "/users/refresh",
        { refresh_token: refreshToken }
      );
      setAccessToken(data.access_token);
      saveRefreshToken(data.refresh_token);
      set({ refreshToken: data.refresh_token });
      await get().fetchMe();
    } catch {
      // Refresh failed (expired / revoked) — treat as logged out
      clearAccessToken();
      clearStoredRefreshToken();
      set({ user: null, refreshToken: null, isInitialised: true });
    }
  },

  fetchMe: async () => {
    try {
      const { data } = await api.get<AuthUser>("/users/me");
      set({ user: data, isInitialised: true });
    } catch {
      set({ user: null, isInitialised: true });
    }
  },
}));
