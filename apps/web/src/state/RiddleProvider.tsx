import { createContext, useCallback, useContext, useReducer } from 'react'
import type { ReactNode } from 'react'
import { useRiddleSocket } from '@/hooks/useRiddleSocket'
import { initial, reduce } from '@/state/reducer'
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
  const say = useRiddleSocket(dispatch)

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
    if (text) note(text)
    // `at_ms` is when the button was pressed, not when the loop notices, so
    // the tail of what you were still saying belongs to this turn.
    say({
      type: 'send',
      at_ms: state.startedMs ? Date.now() - state.startedMs : 0,
      draft: text,
    })
    dispatch({ type: 'draft', text: '' })
  }, [note, say, state.draft, state.startedMs])

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
