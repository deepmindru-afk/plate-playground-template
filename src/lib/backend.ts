/**
 * Base URL of the Python backend, configurable via NEXT_PUBLIC_BACKEND_URL.
 */
export const BACKEND_URL =
  process.env.NEXT_PUBLIC_BACKEND_URL?.replace(/\/+$/, '') ||
  'http://localhost:8000';

export function backendUrl(path: string): string {
  return `${BACKEND_URL}${path.startsWith('/') ? path : `/${path}`}`;
}
