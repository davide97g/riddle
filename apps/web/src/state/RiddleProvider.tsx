import { createContext, useCallback, useContext, useEffect, useReducer, useRef } from 'react'
import type { ReactNode } from 'react'
import { useRiddleSocket } from '@/hooks/useRiddleSocket'
import { initial, nowMs, reduce } from '@/state/reducer'
import type { State } from '@/state/reducer'

type Diary = {
  state: State
  setDraft: (text: string) => void
  note: (text: string) => void
  send: () => void
  clear: () => void
  /** bring the half that owns the pen up, or take it down */
  runDiary: (up: boolean) => void
  /** fade the ink and answer after a pause, or leave the page alone */
  setVanish: (on: boolean) => void
}

const VANISH = 'riddle.vanish'

/** This browser's word on the switch, from the last time it was turned. */
function remembered(): boolean | null {
  try {
    const kept = localStorage.getItem(VANISH)
    return kept === null ? null : kept === '1'
  } catch {
    // Private browsing throws rather than returning null.
    return null
  }
}

function remember(on: boolean) {
  try {
    localStorage.setItem(VANISH, on ? '1' : '0')
  } catch {
    // A switch that cannot be remembered here is still kept by the server.
  }
}

const Context = createContext<Diary | null>(null)

export function RiddleProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(reduce, initial)
  const pendingSend = useRef<string | null>(null)
  const say = useRiddleSocket(dispatch, (intent) => {
    if (pendingSend.current) {
      dispatch({ type: 'acked', id: pendingSend.current, intent })
      pendingSend.current = null
    }
  })

  const setDraft = useCallback((text: string) => {
    dispatch({ type: 'draft', text })
  }, [])

  const note = useCallback(
    (text: string) => {
      const trimmed = text.trim()
      if (!trimmed) return
      // Show it immediately; the server's echo replaces this row in place.
      dispatch({ type: 'pending', id: crypto.randomUUID(), text: trimmed })
      say({ type: 'note', text: trimmed })
    },
    [say],
  )

  const send = useCallback(() => {
    const text = state.draft.trim()
    const id = crypto.randomUUID()
    // One optimistic row for the whole send, tagged with the intent id when
    // the server acknowledges it, so the reply can replace it in place.
    dispatch({ type: 'pending', id, text: text || 'asking the diary' })
    pendingSend.current = id
    // `at_ms` is when the button was pressed, not when the loop notices, so
    // the tail of what you were still saying belongs to this turn.
    say({ type: 'send', at_ms: nowMs(state), draft: text })
    dispatch({ type: 'draft', text: '' })
  }, [say, state])

  const clear = useCallback(() => {
    // The rows go now; the ink takes as long as the eraser takes. Nothing is
    // waited on, and a second press while the first is still running only
    // leaves a second intent, which finds nothing left to rub out.
    dispatch({ type: 'cleared' })
    say({ type: 'clear' })
  }, [say])

  const runDiary = useCallback(
    (up: boolean) => {
      // Nothing optimistic. The server says `busy` straight back and `diary`
      // again when it is done, and a book that swung open before the loop
      // was up would be the page lying about the one thing it must not.
      say({ type: up ? 'diary.start' : 'diary.stop' })
    },
    [say],
  )

  const setVanish = useCallback(
    (on: boolean) => {
      // Optimistic, unlike the diary's own switch: this is a setting, not a
      // process, and the server's echo says the same thing a moment later.
      remember(on)
      dispatch({ type: 'server', msg: { type: 'vanish', on } })
      say({ type: 'vanish', on })
    },
    [say],
  )

  // The switch lives in the store, because the loop is what obeys it, and in
  // this browser, so it survives the store being new. A server that has never
  // been told takes this browser's word; one that has is newer than it, and
  // is remembered here.
  useEffect(() => {
    if (state.conn !== 'open' || state.vanishKnown) return
    const mine = remembered()
    if (mine !== null) say({ type: 'vanish', on: mine })
  }, [state.conn, state.vanishKnown, say])
  useEffect(() => {
    if (state.vanishKnown) remember(state.vanish)
  }, [state.vanish, state.vanishKnown])

  return (
    <Context.Provider value={{ state, setDraft, note, send, clear, runDiary, setVanish }}>
      {children}
    </Context.Provider>
  )
}

export function useDiary(): Diary {
  const diary = useContext(Context)
  if (!diary) throw new Error('useDiary outside RiddleProvider')
  return diary
}
