"""Frozen real-CLI stdin EOF oracle; a live reconnect is the defect signature."""
import json
import pathlib
import selectors
import socket
import statistics
import subprocess
import sys
import tempfile
import time


def main():
    with tempfile.TemporaryDirectory(prefix="mcp-repro-") as folder:
        path = str(pathlib.Path(folder) / "proxy.sock")
        listener = socket.socket(socket.AF_UNIX)
        listener.bind(path)
        listener.listen(16)
        listener.settimeout(3)
        started = time.perf_counter()
        proxy = subprocess.Popen([sys.argv[1], "mcp-proxy", path], stdin=subprocess.PIPE,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        connections = []
        backend_input = None
        try:
            backend, _ = listener.accept()
            connections.append(backend)
            backend.settimeout(2)
            backend_input = backend.makefile("rb")
            request = b'{"jsonrpc":"2.0","id":1,"method":"ping"}\n'
            reply = b'{"jsonrpc":"2.0","id":1,"result":{}}\n'
            samples = []
            with selectors.DefaultSelector() as selector:
                selector.register(proxy.stdout, selectors.EVENT_READ)
                for index in range(30):
                    exchange_started = time.perf_counter()
                    proxy.stdin.write(request)
                    proxy.stdin.flush()
                    if backend_input.readline() != request:
                        raise RuntimeError("healthy request did not reach backend")
                    backend.sendall(reply)
                    if not selector.select(2) or proxy.stdout.readline() != reply:
                        raise RuntimeError("healthy reply did not reach client")
                    if index == 0:
                        startup_ms = (time.perf_counter() - started) * 1000
                    if index >= 5:
                        samples.append((time.perf_counter() - exchange_started) * 1000)
            proxy.stdin.close()
            deadline = time.monotonic() + 1
            reconnects = 0
            listener.settimeout(0.05)
            while time.monotonic() < deadline and proxy.poll() is None:
                try:
                    conn, _ = listener.accept()
                    connections.append(conn)
                    reconnects += 1
                except socket.timeout:
                    pass
            alive = proxy.poll() is None
            observed = {"healthy_exchange": True, "stdin_closed": True,
                        "alive_after_eof": alive, "reconnects_after_eof": reconnects,
                        "exit_code": proxy.poll(),
                        "timing": {"startup_to_first_reply_ms": round(startup_ms, 3),
                                   "warmups": 5, "samples": len(samples),
                                   "roundtrip_median_ms": round(statistics.median(samples), 3),
                                   "roundtrip_p95_ms": round(sorted(samples)[23], 3)}}
            print(json.dumps(observed), flush=True)
            if alive and reconnects > 0:
                print("ORACLE: live proxy reconnects after its client stdin EOF", flush=True)
                return 1
            if not alive and proxy.returncode == 0 and reconnects == 0:
                print("HEALTHY: stdin EOF ends the client without reconnect", flush=True)
                return 0
            raise RuntimeError("neither healthy nor declared defect signature")
        finally:
            if proxy.poll() is None:
                proxy.kill()
            proxy.wait(timeout=3)
            if backend_input is not None:
                backend_input.close()
            for conn in connections:
                conn.close()
            listener.close()
            proxy.stdout.close()
            stderr = proxy.stderr.read().decode(errors="replace")
            proxy.stderr.close()
            if stderr:
                print("CLI STDERR: " + stderr, flush=True)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print("HARNESS ERROR: " + repr(error), flush=True)
        raise SystemExit(2)
