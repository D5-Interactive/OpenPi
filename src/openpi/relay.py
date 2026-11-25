"""A tiny outbound relay: no open port on the machine running openpi.

Three sockets per client connection:

    browser ──▶ relay :public ──▶ (piped) ──▶ relay :instance ◀── RelayClient ──▶ openpi :port

The instance keeps one control connection; every browser connection makes the relay send
`GO <id>` and the instance dial back with `DATA <token> <id>`, which the relay pairs with the
waiting browser socket. Plain byte pipe, so HTTP, SSE, and keep-alive all behave normally.

v1 is not end-to-end encrypted: run the relay on a host you trust, or put TLS in front of it.
The instance token authenticates the instance side; the openpi token authenticates users.
"""

from __future__ import annotations

import asyncio
import threading
import uuid

CONTROL_TIMEOUT = 8.0


async def _pipe(reader_a, writer_a, reader_b, writer_b) -> None:
    async def copy(source, sink) -> None:
        try:
            while data := await source.read(65536):
                sink.write(data)
                await sink.drain()
        except (ConnectionError, asyncio.CancelledError):
            pass
        finally:
            try:
                sink.write_eof()
            except (OSError, RuntimeError):
                pass

    await asyncio.gather(copy(reader_a, writer_b), copy(reader_b, writer_a),
                         return_exceptions=True)
    for writer in (writer_a, writer_b):
        try:
            writer.close()
        except (OSError, RuntimeError):
            pass


async def _refuse(reader, writer, status: str = "503 Service Unavailable") -> None:
    # Consume the request first: closing a socket with unread bytes sends RST, not a response.
    try:
        await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), timeout=2)
    except (asyncio.TimeoutError, asyncio.IncompleteReadError, asyncio.LimitOverrunError, OSError):
        pass
    try:
        writer.write(f"HTTP/1.0 {status}\r\nContent-Length: 0\r\nConnection: close\r\n\r\n".encode())
        await writer.drain()
    except OSError:
        pass
    finally:
        try:
            writer.write_eof()
            await asyncio.wait_for(writer.wait_closed(), timeout=2)
        except (OSError, RuntimeError, asyncio.TimeoutError):
            pass


def _finish(loop: asyncio.AbstractEventLoop) -> None:
    """Cancel whatever is left, let it unwind, then close the loop."""
    pending = [task for task in asyncio.all_tasks(loop) if not task.done()]
    for task in pending:
        task.cancel()
    if pending:
        try:
            loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
        except (RuntimeError, asyncio.CancelledError):
            pass
    loop.close()


def stop_loop(loop: asyncio.AbstractEventLoop, tasks: list) -> None:
    def shutdown() -> None:
        for task in tasks:
            task.cancel()

    try:
        loop.call_soon_threadsafe(shutdown)
    except RuntimeError:
        pass


def start_relay(token: str, public_port: int = 0, instance_port: int = 0, host: str = "0.0.0.0"):
    """Bind both ports and serve in a background thread. Returns (public, instance, thread, loop)."""
    loop = asyncio.new_event_loop()
    state: dict = {"control": None, "waiting": {}}
    ports: dict = {}
    ready = threading.Event()

    async def handle_instance(reader, writer) -> None:
        try:
            header = await asyncio.wait_for(reader.readline(), timeout=10)
        except asyncio.TimeoutError:
            writer.close()
            return
        parts = header.decode("utf-8", "replace").split()
        if len(parts) < 2 or parts[1] != token:
            writer.close()
            return
        kind = parts[0]
        if kind == "CTRL":
            previous = state.get("control")
            if previous is not None:
                previous.close()
            state["control"] = writer
            writer.write(b"OK\n")
            await writer.drain()
            try:
                await reader.read()  # hold until the instance disconnects
            finally:
                if state.get("control") is writer:
                    state["control"] = None
            return
        if kind == "DATA" and len(parts) >= 3:
            pending = state["waiting"].pop(parts[2], None)
            if pending is not None and not pending.done():
                pending.set_result((reader, writer))
                return
            writer.close()
            return
        writer.close()

    async def handle_public(reader, writer) -> None:
        control = state.get("control")
        if control is None or control.is_closing():
            return await _refuse(reader, writer)
        connection_id = uuid.uuid4().hex[:10]
        future = loop.create_future()
        state["waiting"][connection_id] = future
        try:
            control.write(f"GO {connection_id}\n".encode())
            await control.drain()
            instance_reader, instance_writer = await asyncio.wait_for(future, timeout=CONTROL_TIMEOUT)
        except (asyncio.TimeoutError, ConnectionError, OSError):
            state["waiting"].pop(connection_id, None)
            return await _refuse(reader, writer)
        await _pipe(reader, writer, instance_reader, instance_writer)

    async def serve() -> None:
        public = await asyncio.start_server(lambda r, w: handle_public(r, w), host, public_port)
        instance = await asyncio.start_server(lambda r, w: handle_instance(r, w), host, instance_port)
        ports["public"] = public.sockets[0].getsockname()[1]
        ports["instance"] = instance.sockets[0].getsockname()[1]
        loop._openpi_tasks = [asyncio.current_task()]
        ready.set()
        await asyncio.gather(public.serve_forever(), instance.serve_forever())

    def run() -> None:
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(serve())
        except (RuntimeError, asyncio.CancelledError):
            pass
        finally:
            _finish(loop)

    thread = threading.Thread(target=run, daemon=True, name="openpi-relay")
    thread.start()
    if not ready.wait(5):
        raise RuntimeError("relay did not start")
    return ports["public"], ports["instance"], thread, loop


def stop_relay(loop: asyncio.AbstractEventLoop) -> None:
    stop_loop(loop, list(getattr(loop, "_openpi_tasks", [])))


class RelayClient:
    """Runs inside the openpi server: keeps a control socket out and dials back on demand."""

    def __init__(self, host: str, port: int, token: str, local_host: str, local_port: int) -> None:
        self.host = host
        self.port = port
        self.token = token
        self.local_host = local_host
        self.local_port = local_port
        self.connected = False
        self.failed = False
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._main_task = None
        self._control = None

    def start(self) -> None:
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run, daemon=True, name="openpi-relay-client")
        self._thread.start()

    def _run(self) -> None:
        assert self._loop is not None
        asyncio.set_event_loop(self._loop)
        self._main_task = self._loop.create_task(self._main())
        try:
            self._loop.run_until_complete(self._main_task)
        except (asyncio.CancelledError, RuntimeError):
            pass
        except Exception:  # noqa: BLE001 - surfaced as a flag
            self.failed = True
        finally:
            self.connected = False
            _finish(self._loop)

    async def _main(self) -> None:
        reader, writer = await asyncio.open_connection(self.host, self.port)
        self._control = writer
        writer.write(f"CTRL {self.token}\n".encode())
        await writer.drain()
        line = await reader.readline()
        if not line.startswith(b"OK"):
            self.failed = True
            writer.close()
            return
        self.connected = True
        while line := await reader.readline():
            if line.startswith(b"GO "):
                connection_id = line[3:].strip().decode()
                asyncio.create_task(self._pair(connection_id))
        self.connected = False

    async def _pair(self, connection_id: str) -> None:
        try:
            remote_reader, remote_writer = await asyncio.open_connection(self.host, self.port)
        except OSError:
            return
        remote_writer.write(f"DATA {self.token} {connection_id}\n".encode())
        await remote_writer.drain()
        try:
            local_reader, local_writer = await asyncio.open_connection(self.local_host, self.local_port)
        except OSError:
            remote_writer.close()
            return
        await _pipe(remote_reader, remote_writer, local_reader, local_writer)

    def stop(self) -> None:
        if self._loop is None:
            return
        stop_loop(self._loop, [self._main_task])
        self.connected = False
        if self._thread is not None:
            self._thread.join(timeout=5)
