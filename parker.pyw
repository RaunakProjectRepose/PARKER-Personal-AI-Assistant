"""Double-click (or let Windows start) this file to run PARKER without a console.

`.pyw` files open with pythonw.exe, which shows no terminal window.
`--background` starts PARKER hidden in the system tray.
"""

import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
# pythonw.exe has no console, so there is nowhere to print to; libraries that
# show progress bars would otherwise fail.
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")
os.chdir(ROOT)
sys.path.insert(0, ROOT)

from frontend.app import main  # noqa: E402

sys.exit(main(sys.argv[1:]))
