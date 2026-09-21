"""How this project talks to the tablet, and where the tablet keeps things.

Two sets of ssh options rather than one, because the two connections want
opposite things. The agent pipe is long-lived and interactive: it wants
keepalives so a sleeping tablet surfaces as a dead link in about fifteen
seconds instead of hanging, and tiny writes sent now rather than coalesced.
A screen read is one big transfer that must never sit waiting on a password
prompt nobody is there to answer.
"""

# Shared by everything: fail fast, never prompt.
BASE = [
    "-o", "ConnectTimeout=10",
    "-o", "BatchMode=yes",
]

# The agent pipe: notice a dead link in about 15s instead of hanging on TCP's
# own timeout, and keep an access point from idling the connection out between
# replies.
INTERACTIVE = BASE + [
    "-o", "ServerAliveInterval=5",
    "-o", "ServerAliveCountMax=3",
    "-o", "TCPKeepAlive=yes",
    # Interactive traffic: tiny writes, sent now rather than coalesced.
    "-o", "IPQoS=lowdelay throughput",
]

# Where xochitl keeps the documents. Both the notebook lookup and the
# page-turn watcher read this directory, and they used to spell it twice.
XOCHITL_DIR = "/home/root/.local/share/remarkable/xochitl"

# Where the cross-compiled agent is installed on the tablet.
REMOTE_AGENT = "/home/root/riddle/riddled"
