// Generated once, not by hand and not by a font.
//
// These are the pen paths `riddle write "riddle"` would lay down: the same
// DancingScript skeleton the loop sends to the tablet, thinned by
// `ink/skeleton.py` and smoothed through Catmull-Rom into cubics. The page
// draws the word the way the machine would, in the order a hand would --
// strokes sorted left to right, each one running rightward -- so the splash
// is the product demonstrating itself rather than a logo fading in.
//
// To regenerate: Font("DancingScript", weight=700).word("riddle", 0, 0, 100),
// normalise to a 100-unit cap height, keep `len` as the path length so the
// nib can travel at one speed across strokes of different sizes.

/** One pen stroke. `len` is the arc length of the rendered curve in viewBox
 *  units -- measured off the cubics, not off the points they were fitted to,
 *  because a dasharray even slightly short of the path leaves a pinprick of
 *  ink showing before its stroke has been drawn. It is baked in here rather
 *  than read back from `getTotalLength`, which would cost a layout per
 *  stroke on every mount. */
export type Stroke = { d: string; len: number }

export const WORDMARK = {
  /** cap height is 100; the box is as wide as the hand made it */
  width: 314.9,
  height: 100.0,
  /** the width of the nib, in the same units */
  nib: 8,
  strokes: [
    { d: 'M0 80.6C0 80.1 -0.2 78.1 0 77.6C0.2 77.1 -0 80.1 1.5 77.6C3 75.1 7.2 66.7 9 62.7C10.7 58.7 11.2 55.2 11.9 53.7C12.7 52.2 13.2 53.7 13.4 53.7', len: 34.0 },
    { d: 'M14.9 43.3C14.7 43.5 13.7 43 13.4 44.8C13.2 46.5 11.9 51.5 13.4 53.7C14.9 56 20.4 56.2 22.4 58.2C24.4 60.2 24.9 63.2 25.4 65.7C25.9 68.2 26.1 70.1 25.4 73.1C24.6 76.1 21.9 81.8 20.9 83.6C19.9 85.3 19.4 81.3 19.4 83.6C19.4 85.8 19.7 94.5 20.9 97C22.1 99.5 24.6 98.5 26.9 98.5C29.1 98.5 33.1 97.5 34.3 97C35.6 96.5 33.8 95.8 34.3 95.5C34.8 95.3 36.8 95.8 37.3 95.5C37.8 95.3 35.6 95.3 37.3 94C39.1 92.8 45 89.1 47.8 88.1C50.5 87.1 52.5 86.8 53.7 88.1C55 89.3 54.2 93.8 55.2 95.5C56.2 97.3 57 98.3 59.7 98.5C62.4 98.8 68.2 98.8 71.6 97C75.1 95.3 77.6 89.8 80.6 88.1C83.6 86.3 87.3 89.3 89.6 86.6C91.8 83.8 93 74.1 94 71.6C95 69.2 94.8 72.9 95.5 71.6C96.3 70.4 95.8 67.7 98.5 64.2C101.2 60.7 107.5 53.7 111.9 50.7C116.4 47.8 121.4 46 125.4 46.3C129.4 46.5 133.6 51.5 135.8 52.2C138.1 53 135.8 57.2 138.8 50.7C141.8 44.3 151 19.7 153.7 13.4C156.5 7.2 155 13.9 155.2 13.4C155.5 12.9 155 10.9 155.2 10.4C155.5 9.9 155.5 12.2 156.7 10.4C158 8.7 161.7 1.7 162.7 0', len: 294.9 },
    { d: 'M53.7 88.1C54.2 85.6 54.7 78.4 56.7 73.1C58.7 67.9 64.2 59.5 65.7 56.7', len: 34.0 },
    { d: 'M77.6 29.9 L80.6 29.9', len: 3.0 },
    { d: 'M89.6 86.6C89.8 87.6 90.3 91 91 92.5C91.8 94 92.5 95 94 95.5C95.5 96 97.5 96 100 95.5C102.5 95 105.7 95 109 92.5C112.2 90 116.7 82.8 119.4 80.6C122.1 78.4 124.4 78.9 125.4 79.1C126.4 79.4 125.9 81.8 125.4 82.1C124.9 82.3 122.9 80.8 122.4 80.6', len: 55.2 },
    { d: 'M135.8 52.2C135.8 53.2 137.1 54.2 135.8 58.2C134.6 62.2 129.4 70.1 128.4 76.1C127.4 82.1 129.1 90.5 129.9 94C130.6 97.5 130.6 96.8 132.8 97C135.1 97.3 140 97.3 143.3 95.5C146.5 93.8 149.3 88.3 152.2 86.6C155.2 84.8 159.7 85.3 161.2 85.1', len: 81.2 },
    { d: 'M194 80.6C194.5 80.8 196.5 82.3 197 82.1C197.5 81.8 198 79.4 197 79.1C196 78.9 193.8 78.4 191 80.6C188.3 82.8 184.8 90 180.6 92.5C176.4 95 168.7 95.5 165.7 95.5C162.7 95.5 163.4 94 162.7 92.5C161.9 91 161.2 89.1 161.2 86.6C161.2 84.1 161.2 81.3 162.7 77.6C164.2 73.9 166.7 68.7 170.1 64.2C173.6 59.7 179.1 53.7 183.6 50.7C188.1 47.8 193 46 197 46.3C201 46.5 205.7 51.2 207.5 52.2', len: 125.7 },
    { d: 'M234.3 0C233.3 1.7 229.6 8.7 228.4 10.4C227.1 12.2 227.1 9.9 226.9 10.4C226.6 10.9 227.1 12.9 226.9 13.4C226.6 13.9 228.1 7.2 225.4 13.4C222.6 19.7 213.4 44.3 210.4 50.7C207.5 57.2 208 51 207.5 52.2C207 53.5 208.7 54.2 207.5 58.2C206.2 62.2 201.2 71.4 200 76.1C198.8 80.8 199.8 83.6 200 86.6C200.2 89.6 200.5 92.3 201.5 94C202.5 95.8 205 96.8 206 97C207 97.3 206 95.8 207.5 95.5C209 95.3 211.7 97.3 214.9 95.5C218.2 93.8 224.9 87.3 226.9 85.1C228.9 82.8 225.4 82.8 226.9 82.1C228.4 81.3 234.3 80.8 235.8 80.6', len: 157.3 },
    { d: 'M241.8 64.2C241.8 62.9 241.3 58.7 241.8 56.7C242.3 54.7 244 54.2 244.8 52.2C245.5 50.2 245.8 46 246.3 44.8C246.8 43.5 247.5 45.3 247.8 44.8C248 44.3 247.5 42.3 247.8 41.8C248 41.3 249 42.3 249.3 41.8C249.5 41.3 249 39.3 249.3 38.8C249.5 38.3 249 42.3 250.7 38.8C252.5 35.3 256.2 23.9 259.7 17.9C263.2 11.9 268.9 5.5 271.6 3C274.4 0.5 275.1 2.7 276.1 3C277.1 3.2 277.4 2.7 277.6 4.5C277.9 6.2 277.9 11.9 277.6 13.4C277.4 14.9 276.6 11.9 276.1 13.4C275.6 14.9 275.1 20.9 274.6 22.4C274.1 23.9 274.9 18.9 273.1 22.4C271.4 25.9 268.2 36.6 264.2 43.3C260.2 50 253 59.2 249.3 62.7C245.5 66.2 243.5 63.4 241.8 64.2C240 64.9 239.8 64.7 238.8 67.2C237.8 69.7 236.1 74.9 235.8 79.1C235.6 83.3 236.3 89.6 237.3 92.5C238.3 95.5 239.1 96.5 241.8 97C244.5 97.5 250.7 96.8 253.7 95.5C256.7 94.3 257.5 90.8 259.7 89.6C261.9 88.3 265.9 89.6 267.2 88.1C268.4 86.6 266.9 82.3 267.2 80.6C267.4 78.9 267.9 78.1 268.7 77.6C269.4 77.1 271.1 78.6 271.6 77.6C272.1 76.6 270.1 74.9 271.6 71.6C273.1 68.4 277.6 61.7 280.6 58.2C283.6 54.7 286.8 52.5 289.6 50.7C292.3 49 294.5 48 297 47.8C299.5 47.5 303 47.8 304.5 49.3C306 50.7 306.2 54.2 306 56.7C305.7 59.2 305.7 60.9 303 64.2C300.2 67.4 293 73.6 289.6 76.1C286.1 78.6 284.8 78.6 282.1 79.1C279.4 79.6 274.9 79.4 273.1 79.1C271.4 78.9 271.9 77.9 271.6 77.6', len: 345.9 },
    { d: 'M267.2 88.1C267.4 89.1 267.2 92 268.7 94C270.1 96 272.4 99 276.1 100C279.8 101 288.6 100.2 291 100C293.5 99.8 289.6 99.3 291 98.5C292.5 97.8 297.5 96.8 300 95.5C302.5 94.3 304 92.8 306 91C308 89.3 310.9 86.6 311.9 85.1C312.9 83.6 311.4 82.8 311.9 82.1C312.4 81.3 314.4 81.3 314.9 80.6C315.4 79.9 314.9 78.1 314.9 77.6', len: 68.9 },
  ] as Stroke[],
}

/** How far the nib travels to write the whole word. Stroke delays are shares
 *  of this, so the pen keeps one speed instead of spending equal time on the
 *  dot of the i and the tail of the e. */
export const TOTAL_LEN = WORDMARK.strokes.reduce((sum, s) => sum + s.len, 0)

/** Each stroke's share of the journey, as a start and a span in 0..1.
 *  Computed once here rather than accumulated inside a render. */
export const TIMING: { at: number; span: number }[] = (() => {
  let travelled = 0
  return WORDMARK.strokes.map((stroke) => {
    const at = travelled / TOTAL_LEN
    travelled += stroke.len
    return { at, span: stroke.len / TOTAL_LEN }
  })
})()
