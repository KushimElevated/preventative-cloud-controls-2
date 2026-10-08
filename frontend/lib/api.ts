export async function api<T>(path: string, method = 'GET', body?: unknown): Promise<T> {
  const token = typeof window !== 'undefined' ? sessionStorage.getItem('control-token') : null;
  const result = await fetch(`/api${path}`, {
    method, cache: 'no-store', headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
  if (result.status === 204) return undefined as T;
  const data = await result.json();
  if (!result.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Request validation failed. Check the supplied fields.');
  return data as T;
}

export function downloadJson(value: unknown, filename: string) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(value, null, 2)], { type: 'application/json' }));
  const link = document.createElement('a'); link.href = url; link.download = filename; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
