"""Everything that talks to the tablet.

`agent` is the ssh pipe to `riddled` and the only thing that moves the pen;
`screen` reads the framebuffer out of xochitl's memory; `notebook` and
`pages` ask xochitl's files what document is open and whether the writer has
turned the page; `taps` remembers where the toolbar buttons are.

Device, and the events it hands back, are re-exported here because nearly
every caller wants only those.
"""

from riddle.device.agent import Device, PenUp, Sample, Tool, Touch

__all__ = ["Device", "PenUp", "Sample", "Tool", "Touch"]
