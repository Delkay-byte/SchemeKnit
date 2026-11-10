/** Bundled form assets, cached for the page lifetime. */

const cache = new Map<string, Promise<Uint8Array>>()

export function clearTemplateCache(): void {
  cache.clear()
}

export function loadTemplateAsset(path: string): Promise<Uint8Array> {
  const key = path.startsWith('/') ? path : `/${path}`
  const existing = cache.get(key)
  if (existing) return existing
  const request = (async () => {
    const response = await fetch(key, { cache: 'force-cache' })
    if (!response.ok) {
      throw new Error(
        `The Word template could not be loaded (${response.status}). Refresh and try again.`,
      )
    }
    return new Uint8Array(await response.arrayBuffer())
  })()
  cache.set(key, request)
  request.catch(() => cache.delete(key))
  return request
}
