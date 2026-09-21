import { createContext, useCallback, useContext, useReducer, useRef } from 'react'
import type { ReactNode } from 'react'
import { useRiddleSocket } from '@/hooks/useRiddleSocket'
import { initial, nowMs, reduce } from '@/state/reducer'
import type { State } from '@/state/reducer'

type Diary = {
  state: State
  setDraft: (text: string) => void
  note: (text: string) => void
  send: () => void
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

  return (
    <Context.Provider value={{ state, setDraft, note, send }}>
      {children}
    </Context.Provider>
  )
}

export function useDiary(): Diary {
  const diary = useContext(Context)
  if (!diary) throw new Error('useDiary outside RiddleProvider')
  return diary
}
