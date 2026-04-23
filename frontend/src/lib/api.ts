/// <reference types="vite/client" />
/**
 * API client.
 *
 * All HTTP calls go through this module.
 * Features include:
 * - Base URL from env
 * - JWT token injection
 * - Consistent error handling
 * - TypeScript-typed responses
 */

import axios, { AxiosError, AxiosInstance } from "axios";
import type { APIError } from "@/types";

/**
 * When `VITE_API_URL` is unset, use same-origin `/api/v1` so Vite's `server.proxy`
 * forwards to the backend — avoids CORS and fixes "status (null)" when port 8000
 * is unreachable from the browser (e.g. backend only on Docker network).
 */
function resolveApiBaseURL(): string {
  const raw = import.meta.env.VITE_API_URL?.trim();
  if (!raw) {
    return "/api/v1";
  }
  const origin = raw.replace(/\/+$/, "");
  return `${origin}/api/v1`;
}

function createApiClient(): AxiosInstance {
  const client = axios.create({
    baseURL: resolveApiBaseURL(),
    withCredentials: true, // for httpOnly cookie auth
    headers: {
      "Content-Type": "application/json",
    },
  });

  // Request interceptor — inject auth token if present in memory
  client.interceptors.request.use((config) => {
    const token = getAccessToken();
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  });

  // Response interceptor — normalize errors
  client.interceptors.response.use(
    (response) => response,
    (error: AxiosError<APIError>) => {
      if (error.response?.status === 401) {
        clearAccessToken();
        window.location.href = "/login";
      }
      return Promise.reject(error);
    }
  );

  return client;
}

// In-memory token store — never localStorage
let _accessToken: string | null = null;

export function setAccessToken(token: string): void {
  _accessToken = token;
}

export function getAccessToken(): string | null {
  return _accessToken;
}

export function clearAccessToken(): void {
  _accessToken = null;
}

export const api = createApiClient();
