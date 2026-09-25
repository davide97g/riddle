import { useCallback, useState } from 'react'

const KEPT = 'riddle.snapshots'
const MAX = 10

export type Snapshot = {
  id: string
  /** unix epoch ms, for the label and the file name only */
  at: number
  /** the frame as the tablet sent it, a png data url */
  png: string
}

function load(): Snapshot[] {
  try {
    const raw = localStorage.getItem(KEPT)
    const list = raw ? JSON.parse(raw) : []
    return Array.isArray(list) ? list.slice(0, MAX) : []
  } catch {
    // Private browsing throws rather than returning null, and a shelf that
    // cannot remember is still a shelf for this tab.
    return []
  }
}

/** Write as many of the newest as fit. A dense page is a couple of hundred
 *  kilobytes as a data url, so ten of them can meet the quota; the oldest
 *  goes first rather than the one just taken. Returns how many were kept. */
function save(list: Snapshot[]): number {
  for (let n = list.length; n >= 0; n--) {
    try {
      localStorage.setItem(KEPT, JSON.stringify(list.slice(0, n)))
      return n
    } catch {
      // over quota, or no storage at all: try with one fewer
    }
  }
  return 0
}

function dataUrl(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(reader.result as string)
    reader.onerror = () => reject(reader.error)
    reader.readAsDataURL(blob)
  })
}

/** `riddle-2026-09-25-153207.png`, in the browser's own time zone. */
export function fileName(at: number) {
  const d = new Date(at)
  const two = (n: number) => String(n).padStart(2, '0')
  return `riddle-${d.getFullYear()}-${two(d.getMonth() + 1)}-${two(d.getDate())}-${two(d.getHours())}${two(d.getMinutes())}${two(d.getSeconds())}.png`
}

/** Put a png on the clipboard.
 *
 *  The item is handed a promise rather than a blob so the write starts inside
 *  the click: Safari refuses a clipboard write that begins after an await,
 *  and turning a data url back into a blob is one. */
export function copyPng(png: Blob | Promise<Blob>): Promise<void> {
  if (!navigator.clipboard?.write || typeof ClipboardItem === 'undefined')
    return Promise.reject(new Error('this browser cannot put an image on the clipboard'))
  return navigator.clipboard.write([new ClipboardItem({ 'image/png': png })])
}

export function blobOf(snap: Snapshot): Promise<Blob> {
  return fetch(snap.png).then((r) => r.blob())
}

/** The last ten frames somebody chose to keep, newest first.
 *
 *  In the browser and nowhere else: the server never learns a snapshot was
 *  taken, and the frame is the png it already sent, so nothing is read off
 *  the tablet twice. */
export function useSnapshots() {
  const [snaps, setSnaps] = useState<Snapshot[]>(load)
  // Whether the newest write fitted. A shelf that is quietly not being kept
  // would be found out on the next visit, when it is too late.
  const [kept, setKept] = useState(true)

  const keep = useCallback((next: Snapshot[]) => {
    setSnaps(next)
    setKept(save(next) === next.length)
  }, [])

  const take = useCallback(
    async (png: Blob) => {
      const snap: Snapshot = { id: crypto.randomUUID(), at: Date.now(), png: await dataUrl(png) }
      keep([snap, ...snaps].slice(0, MAX))
      return snap
    },
    [keep, snaps],
  )

  const remove = useCallback(
    (id: string) => keep(snaps.filter((s) => s.id !== id)),
    [keep, snaps],
  )

  return { snaps, kept, take, remove }
}
