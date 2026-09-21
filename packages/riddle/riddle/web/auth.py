"""One password in front of the page, for when it is not only on the LAN.

The page is a diary, and it can make the pen write: anyone who reaches it
reads what was written and can ask for more of it. On loopback that is the
same trust as the machine itself, which is why the gate is off by default and
`RIDDLE_WEB_PASSWORD` is what closes it. Published on a tunnel, it is the only
thing between the internet and someone else's notebook.

A cookie rather than HTTP Basic, for one concrete reason: the browser
WebSocket API cannot send an `Authorization` header, so a Basic gate would
have to let `/ws/events` through unauthenticated -- and that socket is the
whole feed and the send path both. Cookies ride the upgrade request like any
other, so one check covers the page, the api and the socket.

The token is `hmac(password, "riddle-v1")`: deterministic, so a restart does
not log anybody out and no secret has to be kept on disk beside the database,
and one-way, so the cookie cannot be turned back into the password. Changing
the password is what revokes it.
"""

import hashlib
import hmac

COOKIE = "riddle"
YEAR_S = 31_536_000


class Gate:
    def __init__(self, password: str) -> None:
        self.password = password or ""
        self._token = _mint(self.password) if self.password else ""

    @property
    def closed(self) -> bool:
        """Whether anything is being asked for at all."""
        return bool(self.password)

    def allows(self, headers: dict) -> bool:
        if not self.closed:
            return True
        for crumb in headers.get("cookie", "").split(";"):
            name, _, value = crumb.strip().partition("=")
            if name == COOKIE and hmac.compare_digest(value, self._token):
                return True
        return False

    def admits(self, password: str) -> bool:
        return self.closed and hmac.compare_digest(_mint(password or ""), self._token)

    def crumb(self, secure: bool) -> str:
        """The Set-Cookie line that lets this browser back in.

        `HttpOnly` keeps it away from the page's own javascript, and `Lax`
        means another site cannot make your browser send it -- which for this
        page would be a cross-site request that writes on your tablet.
        """
        parts = [
            f"{COOKIE}={self._token}",
            "Path=/",
            "HttpOnly",
            "SameSite=Lax",
            f"Max-Age={YEAR_S}",
        ]
        if secure:
            parts.append("Secure")
        return "; ".join(parts)


def _mint(password: str) -> str:
    return hmac.new(password.encode(), b"riddle-v1", hashlib.sha256).hexdigest()


def page(wrong: bool = False) -> bytes:
    """The whole login page: no build step, no javascript, one field.

    It is served in place of whatever was asked for, with a 401, so a page
    reloaded after the cookie expires shows this rather than an empty app
    shell that cannot open its socket.
    """
    note = (
        '<p class="no">that is not it</p>' if wrong else ""
    )
    return f"""<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>riddle</title>
<style>
  :root {{ color-scheme: light dark; --ink: #111; --paper: #faf9f7; --line: #0002; }}
  @media (prefers-color-scheme: dark) {{
    :root {{ --ink: #ece9e4; --paper: #121212; --line: #fff3; }}
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; min-height: 100dvh; display: grid; place-items: center;
    background: var(--paper); color: var(--ink); padding: 24px;
    font: 16px/1.5 ui-serif, Georgia, serif;
  }}
  form {{ width: min(22rem, 100%); display: grid; gap: 12px; }}
  h1 {{ font-size: 1.25rem; font-weight: 500; margin: 0 0 4px; }}
  p {{ margin: 0; opacity: .7; font-size: .9rem; }}
  .no {{ opacity: 1; color: #c0392b; }}
  input, button {{
    font: inherit; padding: 10px 12px; border-radius: 10px;
    border: 1px solid var(--line); background: transparent; color: inherit;
  }}
  button {{ cursor: pointer; background: var(--ink); color: var(--paper); border: 0; }}
</style>
<form method="post" action="/api/login">
  <h1>riddle</h1>
  <p>this diary is not open to everyone.</p>
  {note}
  <input type="password" name="password" autofocus autocomplete="current-password"
         aria-label="password" placeholder="password">
  <button type="submit">open it</button>
</form>
</html>""".encode()
