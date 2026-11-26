"""Connect PARKER to Google Calendar (one time):  python -m backend.calendar_connect"""

import sys

from backend.google_calendar import connect_and_show

sys.exit(connect_and_show())
