import { Contrast } from 'lucide-react'
import { Button } from '@/components/ui/button'
import type { Look } from '@/hooks/useLook'

/** Paper or ink: the page as it is, or its ink on the theme. */
export function LookToggle({ look, setLook }: { look: Look; setLook: (look: Look) => void }) {
  const paper = look === 'paper'
  return (
    <Button
      type="button"
      size="sm"
      variant="outline"
      aria-pressed={!paper}
      onClick={() => setLook(paper ? 'ink' : 'paper')}
      title={
        paper
          ? 'Showing the page as it is. Press to show only the ink, on the theme.'
          : 'Showing only the ink, on the theme. Press to show the page as it is.'
      }
    >
      <Contrast className="size-4" />
      <span className="max-sm:sr-only">{paper ? 'Paper' : 'Ink'}</span>
    </Button>
  )
}
