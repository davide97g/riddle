import { useCallback, useState } from 'react'
import { INK } from '@/components/rows/Rows'

/** How a picture of the page is shown.
 *
 *  `paper` is the page as it is: white paper, black ink, the same in either
 *  theme. `ink` drops the paper and lets the ink sit on the theme -- which in
 *  the dark theme means inverting it, a negative of the page. Paper is the
 *  default, because a negative of a photograph or a pdf is not the page. */
export type Look = 'paper' | 'ink'

const KEPT = 'riddle.look'

function load(): Look {
  try {
    return localStorage.getItem(KEPT) === 'ink' ? 'ink' : 'paper'
  } catch {
    return 'paper'
  }
}

export function lookClass(look: Look) {
  return look === 'ink' ? INK : ''
}

export function useLook() {
  const [look, setLook] = useState<Look>(load)
  const choose = useCallback((next: Look) => {
    setLook(next)
    try {
      localStorage.setItem(KEPT, next)
    } catch {
      // A look that cannot be remembered is still the look for this visit.
    }
  }, [])
  return [look, choose] as const
}
