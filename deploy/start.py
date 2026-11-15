"""Initialize demo data and supervise the two HTTP processes in the app container."""

import os
import signal
import socket
import subprocess
import sys
import time


def interrupted(signum, _frame):
    raise SystemExit(128 + signum)


def main():
    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    processes = []
    try:
        ingest = subprocess.Popen([sys.executable, "/app/services/data-pipeline/ingest.py"])
        processes.append(ingest)
        status = ingest.wait()
        if status:
            return status

        web = subprocess.Popen(["node", "server.js"], cwd="/app/web",
                               env={**os.environ, "PORT": "3000", "HOSTNAME": "127.0.0.1"})
        processes.append(web)
        deadline = time.monotonic() + 30
        while web.poll() is None and time.monotonic() < deadline:
            try:
                with socket.create_connection(("127.0.0.1", 3000), timeout=0.5):
                    break
            except OSError:
                time.sleep(0.2)
        else:
            print("Next.js did not become ready", file=sys.stderr)
            return 1

        api = subprocess.Popen(["trends-api"], env={**os.environ, "WEB_ORIGIN": "http://127.0.0.1:3000"})
        processes.append(api)
        while all(process.poll() is None for process in (web, api)):
            time.sleep(0.3)
        return 1
    finally:
        for process in reversed(processes):
            if process.poll() is None:
                process.terminate()
        for process in reversed(processes):
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


if __name__ == "__main__":
    sys.exit(main())
