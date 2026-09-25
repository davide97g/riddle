// The geometry of /share: a frame of somebody's screen laid out as a page of
// the tablet, and the pen's points on that page brought back to the frame.

/** The panel, in the pixels the pen's points arrive in: portrait, always. */
export const SCREEN_W = 1404
export const SCREEN_H = 1872

export type Orientation = 'portrait' | 'landscape'

/** A frame as the tablet will show it: a png of the screen's own shape, the
 *  shared screen letterboxed onto white inside it. */
export type Still = {
  blob: Blob
  url: string
  orientation: Orientation
  /** the page's own size, 1404x1872 or 1872x1404 */
  width: number
  height: number
}

/** Which way xochitl turns a landscape page: the page's top edge lies along
 *  the panel's right edge. Settled with a page of labelled corners, written on
 *  at each one -- see docs/device.md. If the ink ever comes back mirrored or a
 *  quarter turn out, this is the one line that is wrong. */
const LANDSCAPE_TOP = 'right' as 'right' | 'left'

/** The current frame of a video, as a page for the tablet.
 *
 *  The page is the screen's own proportions whatever the frame's are. xochitl
 *  fits a page to the screen, and a page that already is the screen's shape
 *  fits by scaling alone: no margins of its choosing, so a point on the panel
 *  is a point on this canvas and nothing has to be measured on the tablet. */
export async function grab(video: HTMLVideoElement): Promise<Still> {
  const vw = video.videoWidth
  const vh = video.videoHeight
  if (!vw || !vh) throw new Error('the shared screen has not sent a frame yet')
  const orientation: Orientation = vw > vh ? 'landscape' : 'portrait'
  const width = orientation === 'landscape' ? SCREEN_H : SCREEN_W
  const height = orientation === 'landscape' ? SCREEN_W : SCREEN_H

  const canvas = document.createElement('canvas')
  canvas.width = width
  canvas.height = height
  const ctx = canvas.getContext('2d')
  if (!ctx) throw new Error('this browser will not draw a frame')
  ctx.fillStyle = '#fff'
  ctx.fillRect(0, 0, width, height)
  // The same arithmetic `object-contain` does, so the live video in a box of
  // this shape sits exactly where the frame does on the page.
  const scale = Math.min(width / vw, height / vh)
  const dw = vw * scale
  const dh = vh * scale
  ctx.drawImage(video, (width - dw) / 2, (height - dh) / 2, dw, dh)

  const blob = await new Promise<Blob | null>((done) => canvas.toBlob(done, 'image/png'))
  if (!blob) throw new Error('this browser would not encode the frame')
  return { blob, url: URL.createObjectURL(blob), orientation, width, height }
}

/** A point on the panel, as a point on the page it is showing. */
export function onPage(x: number, y: number, orientation: Orientation): [number, number] {
  if (orientation === 'portrait') return [x, y]
  return LANDSCAPE_TOP === 'right' ? [y, SCREEN_W - x] : [SCREEN_H - y, x]
}

type Point = [number, number]

/** Whether an eraser pass went over a stroke. The loop's own test
 *  (`apps/diary.py`, `crosses`), so the page rubs out what the tablet did. */
export function crosses(stroke: Point[], pass: Point[], radius: number): boolean {
  if (!stroke.length || !pass.length) return false
  const box = (ps: Point[]) => {
    let [x0, y0, x1, y1] = [Infinity, Infinity, -Infinity, -Infinity]
    for (const [x, y] of ps) {
      x0 = Math.min(x0, x)
      y0 = Math.min(y0, y)
      x1 = Math.max(x1, x)
      y1 = Math.max(y1, y)
    }
    return [x0, y0, x1, y1]
  }
  const s = box(stroke)
  const p = box(pass)
  if (s[0] - radius > p[2] || s[2] + radius < p[0] || s[1] - radius > p[3] || s[3] + radius < p[1])
    return false
  const near = radius * radius
  for (let i = 0; i < pass.length; i += 3) {
    for (let j = 0; j < stroke.length; j += 3) {
      const dx = pass[i][0] - stroke[j][0]
      const dy = pass[i][1] - stroke[j][1]
      if (dx * dx + dy * dy <= near) return true
    }
  }
  return false
}
