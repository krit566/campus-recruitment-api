"""Local Postgres without Docker (handy on Windows): starts a server in backend/.pgdata and prints its URL.

    pip install pgserver
    python dev_db.py            # prints DATABASE_URL=...; the server keeps running in the background
    python dev_db.py --stop
"""

import sys
from pathlib import Path

import pgserver

DATA = Path(__file__).resolve().parent / ".pgdata"

if __name__ == "__main__":
    if "--stop" in sys.argv:
        pgserver.get_server(str(DATA), cleanup_mode="stop").cleanup()
        print("stopped")
    else:
        server = pgserver.get_server(str(DATA), cleanup_mode=None)  # None: keep running after this script exits
        print("DATABASE_URL=" + server.get_uri())
