/** The diary, shut or lying open.
 *
 *  `state.diary.present` is the one thing on this page that changes what the
 *  page can do -- with the loop down, Send and Erase are dead controls -- so
 *  it is worth more than a dot going grey. The cover swings on the spine, the
 *  ruled lines come in behind it, and the whole book slides half a width to
 *  the left as it opens, because that is where the spine goes when a book is
 *  opened by its cover.
 *
 *  Two faces on the cover rather than one: flipped past ninety degrees you
 *  are looking at the inside of the front cover, which is paper, not board.
 *  The geometry is in `index.css` next to the keyframes it shares. */
export function DiaryIcon({ open }: { open: boolean }) {
  return (
    <span
      // Shut is the state in which half this page's controls are dead, so
      // it is also the state that should not be the brightest thing in the
      // header. Opening brings the book up to full contrast with it.
      className={`diary transition-colors duration-300 ${
        open ? 'text-foreground' : 'text-muted-foreground'
      }`}
      data-open={open || undefined}
      role="img"
      aria-label={open ? 'The diary is open' : 'The diary is closed'}
      title={
        open
          ? 'The diary is running and will answer a send.'
          : 'The diary is not running.'
      }
    >
      <span className="diary-book">
        <span className="diary-page">
          <span className="diary-rule" />
          <span className="diary-rule" />
          <span className="diary-rule" />
        </span>
        <span className="diary-cover">
          <span className="diary-face diary-face-front" />
          <span className="diary-face diary-face-back" />
        </span>
      </span>
    </span>
  )
}
