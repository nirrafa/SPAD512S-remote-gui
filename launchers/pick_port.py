"""Print the first bindable localhost port from the candidates given as args.

Used by the Windows launchers: lab PCs often have other software squatting on
common ports (a real case: the attocube AMC webapp owning 8080 answered the
browser with its own 404 while the bridge died with winerror 10013). Probing
with a real bind also catches Windows excluded-port ranges, which `netstat`
does not show. Exits 1 if none of the candidates are free.
"""
from __future__ import annotations

import socket
import sys


def main() -> int:
    for arg in sys.argv[1:]:
        port = int(arg)
        try:
            probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            probe.bind(("127.0.0.1", port))
            probe.close()
        except OSError:
            continue
        print(port)
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
