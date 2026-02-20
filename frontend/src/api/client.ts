export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

export async function fetchJson<T>(input: string, init?: RequestInit): Promise<T> {
  const res = await fetch(input, {
    credentials: "include",
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers || {}),
    },
  });
  const text = await res.text();
  if (!res.ok) {
    const detail = text || res.statusText || "Request failed";
    throw new ApiError(detail, res.status);
  }
  if (!text) return {} as T;
  return JSON.parse(text) as T;
}

export function postJson<T>(path: string, body: unknown, init?: RequestInit) {
  return fetchJson<T>(path, {
    method: "POST",
    body: JSON.stringify(body),
    ...init,
  });
}

export function patchJson<T>(path: string, body: unknown, init?: RequestInit) {
  return fetchJson<T>(path, {
    method: "PATCH",
    body: JSON.stringify(body),
    ...init,
  });
}

