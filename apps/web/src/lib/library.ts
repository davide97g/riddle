// The tablet's library, from the page. The server packs and pushes; this is
// only the request, kept in one place because two pages make it.

/** Put a file in the tablet's library. What `SendToTablet` and `/share` both
 *  go through: one request, which restarts xochitl on the way. */
export async function putInLibrary(body: Blob, name: string): Promise<{ id: string; name: string }> {
  const res = await fetch(`/api/library?name=${encodeURIComponent(name)}`, {
    method: 'POST',
    body,
    headers: { 'Content-Type': body.type || 'application/octet-stream' },
  })
  const said = await res.json().catch(() => ({}))
  if (!res.ok) throw new Error(said.error ?? `the server answered ${res.status}`)
  return said
}
