export class ApiError extends Error {}

/** Throws ApiError with a readable message for any non-2xx or network failure. */
export async function api<T>(path: string, opts: { method?: string; body?: unknown } = {}): Promise<T> {
  let res: Response;
  try {
    res = await fetch('/api' + path, {
      method: opts.method ?? 'GET',
      headers: { 'Content-Type': 'application/json' },
      body: opts.body === undefined ? undefined : JSON.stringify(opts.body),
    });
  } catch {
    throw new ApiError('Cannot reach the PromptGraph API. Is the backend running on port 8000?');
  }
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    const errs = data?.detail?.errors ?? (typeof data?.detail === 'string' ? [data.detail] : null);
    throw new ApiError(errs ? errs.join(' · ') : `Request failed (${res.status})`);
  }
  return data as T;
}
