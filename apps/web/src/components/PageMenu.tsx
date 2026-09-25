import { Eye, NotebookPen, ScreenShare } from 'lucide-react'
import { cn } from '@/lib/utils'

export type PageName = 'diary' | 'live' | 'share'

const PAGES: { name: PageName; href: string; label: string; icon: typeof Eye; title: string }[] = [
  { name: 'diary', href: '/', label: 'Diary', icon: NotebookPen, title: 'The timeline: what was written, said and answered' },
  { name: 'live', href: '/live', label: 'Live', icon: Eye, title: 'Watch the page on the tablet, live' },
  { name: 'share', href: '/share', label: 'Share', icon: ScreenShare, title: 'Share a screen with the tablet and see what is written on it' },
]

/** The three pages, and which one this is.
 *
 *  Plain links, not a router: each page is its own document with its own
 *  sockets, and leaving one is meant to close them -- the live feed and the
 *  share's beat both stop when nobody is on their page.
 *
 *  `off` names pages that cannot work right now, with the reason as their
 *  title. A link to a page that can only say "refused" is a link that lies
 *  about where it goes. */
export function PageMenu({
  current,
  off = {},
}: {
  current: PageName
  off?: Partial<Record<PageName, string>>
}) {
  return (
    <nav aria-label="Pages" className="flex items-center gap-0.5 rounded-md border p-0.5">
      {PAGES.map(({ name, href, label, icon: Icon, title }) => {
        const here = name === current
        const why = off[name]
        const look = cn(
          'flex h-7 items-center gap-1.5 rounded-sm px-2 text-xs transition-colors',
          here
            ? 'bg-secondary text-secondary-foreground'
            : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground',
        )
        const inner = (
          <>
            <Icon className="size-3.5" />
            <span className="hidden sm:inline">{label}</span>
            <span className="sr-only sm:hidden">{label}</span>
          </>
        )
        if (why && !here)
          return (
            <span key={name} title={why} aria-disabled className={cn(look, 'cursor-not-allowed opacity-50 hover:bg-transparent hover:text-muted-foreground')}>
              {inner}
            </span>
          )
        return (
          <a key={name} href={href} title={title} aria-current={here ? 'page' : undefined} className={look}>
            {inner}
          </a>
        )
      })}
    </nav>
  )
}
