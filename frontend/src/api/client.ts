// Thin fetch wrapper. credentials:'include' so the session cookie rides along.

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message)
  }
}

async function req<T>(method: string, url: string, body?: unknown): Promise<T> {
  const opts: RequestInit = { method, credentials: 'include', headers: {} }
  if (body !== undefined) {
    ;(opts.headers as Record<string, string>)['Content-Type'] = 'application/json'
    opts.body = JSON.stringify(body)
  }
  const r = await fetch(url, opts)
  if (!r.ok) {
    let detail = r.statusText
    try {
      detail = (await r.json()).detail ?? detail
    } catch {
      /* non-json error */
    }
    throw new ApiError(r.status, detail)
  }
  if (r.status === 204) return undefined as T
  return (await r.json()) as T
}

export const api = {
  get: <T>(u: string) => req<T>('GET', u),
  post: <T>(u: string, b?: unknown) => req<T>('POST', u, b),
  put: <T>(u: string, b?: unknown) => req<T>('PUT', u, b),
  del: <T>(u: string) => req<T>('DELETE', u),
  async upload<T>(u: string, form: FormData): Promise<T> {
    const r = await fetch(u, { method: 'POST', credentials: 'include', body: form })
    if (!r.ok) throw new ApiError(r.status, r.statusText)
    return (await r.json()) as T
  },
}
