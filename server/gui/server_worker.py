"""GUI bridge with one asyncio thread owning every device operation."""
import asyncio
import copy
import logging
import sys
import threading
from collections import deque
from dataclasses import replace

from PySide6.QtCore import QObject, Signal

from server.backends.factory import create_tablet_backend
from server.security import load_identity
from server.server import SPenServer
from server.protocol import ACTION_CANCEL
from server.settings import effective_settings, listener_address, runtime_settings
from server.pairing import PairingManager
from server.gui.network_info import get_local_ip

logger = logging.getLogger("SPenGUI")


class ServerWorker(QObject):
    sig_status = Signal(str, str)
    sig_client_connected = Signal(str)
    sig_client_disconnected = Signal(str)
    sig_stats = Signal(float, int, int)
    sig_pen_events_ready = Signal()
    sig_log = Signal(str)
    sig_pairing_requested = Signal(object)
    sig_pairing_finished = Signal(bool, str)
    sig_pairing_ready = Signal()

    def __init__(self, config):
        super().__init__()
        self.config = config
        self.tablet = self.server = self._loop = self._thread = None
        self.listener_endpoint = None
        self._device_error = None
        self._state = "stopped"
        self._state_lock = threading.Lock()
        self._stop_requested = threading.Event()
        self._stop_async = None
        self._events = deque()
        self._events_lock = threading.Lock()
        self._notification_pending = False

    @property
    def _is_running(self):
        return self._state == "running"

    @property
    def state(self):
        with self._state_lock:
            return self._state

    def start_server(self):
        error = None
        with self._state_lock:
            if self._state != "stopped":
                return
            try:
                snapshot = copy.deepcopy(self.config)
                snapshot.validate()
            except ValueError as failure:
                error = str(failure)
            if error is None:
                self._device_error = None
                self._state = "starting"
                self._stop_requested.clear()
                self._thread = threading.Thread(target=self._run_loop, args=(snapshot,),
                                                name="SPenServer", daemon=True)
                self._thread.start()
        # Same-thread Qt callbacks may read state or request shutdown.
        if error is not None:
            self.sig_status.emit("error", error)

    def _run_loop(self, config):
        loop = asyncio.new_event_loop()
        self._loop = loop
        asyncio.set_event_loop(loop)
        error = None

        async def serve():
            self._stop_async = asyncio.Event()
            try:
                if self._stop_requested.is_set():
                    return
                options = effective_settings(config)
                self.tablet = create_tablet_backend(**options, on_event_processed=self._on_tablet_event)
                if self._stop_requested.is_set():
                    return
                identity = load_identity()
                pairing = PairingManager(identity, config.port, lan_address=get_local_ip(),
                                         on_request=self.sig_pairing_requested.emit,
                                         on_result=self.sig_pairing_finished.emit)
                self.server = SPenServer(
                    self.tablet, host=listener_address(config), port=config.port,
                    tls_context=identity.server_context(), pairing_code=identity.pairing_code,
                    on_client_connected=self.sig_client_connected.emit,
                    on_client_disconnected=self.sig_client_disconnected.emit,
                    on_stats=self.sig_stats.emit,
                    on_device_error=self._on_device_error,
                    pairing_manager=pairing,
                )
                await self.server.start()
                self.listener_endpoint = (listener_address(config), config.port)
                if self._stop_requested.is_set():
                    return
                with self._state_lock:
                    self._state = "running"
                self.sig_status.emit("running", f"Listening on {listener_address(config)}:{config.port} (TLS)")
                await self._stop_async.wait()
            finally:
                try:
                    if self.server:
                        await self.server.stop()
                finally:
                    if self.tablet:
                        self.tablet.close()
                    self.tablet = self.server = None
                    self.listener_endpoint = None

        try:
            loop.run_until_complete(serve())
        except Exception as failure:
            logger.exception("Server worker failed")
            error = str(failure)
        finally:
            pending = asyncio.all_tasks(loop)
            for task in pending:
                task.cancel()
            if pending:
                loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            loop.run_until_complete(loop.shutdown_asyncgens())
            with self._state_lock:
                self._loop = self._stop_async = None
                loop.close()
                self._state = "stopped"
            error = error or self._device_error
            self.sig_status.emit("error" if error else "stopped", error or "Server stopped")

    def _on_device_error(self, message):
        self._device_error = f"Input device failed: {message}"
        self._stop_requested.set()
        if self._stop_async:
            self._stop_async.set()

    def _on_tablet_event(self, ev, pressure, x, y):
        with self._events_lock:
            if len(self._events) >= 2048:
                self._events.clear()
                self._events.append((replace(ev, action=ACTION_CANCEL, pressure=0, buttons=0), 0, x, y))
            self._events.append((ev, pressure, x, y))
            notify = not self._notification_pending
            self._notification_pending = True
        if notify:
            self.sig_pen_events_ready.emit()

    def drain_pen_events(self):
        with self._events_lock:
            events = list(self._events)
            self._events.clear()
            self._notification_pending = False
            return events

    def stop_server(self):
        with self._state_lock:
            if self._state == "stopped":
                return
            self._state = "stopping"
            self._stop_requested.set()
            if self._loop and self._stop_async:
                self._loop.call_soon_threadsafe(self._stop_async.set)

    def shutdown(self, timeout=12):
        """Explicit joined shutdown for application exit, including startup."""
        self.stop_server()
        thread = self._thread
        if thread and thread is not threading.current_thread():
            thread.join(timeout)
            if thread.is_alive():
                raise TimeoutError("Server input cleanup did not finish")

    def _submit(self, operation):
        def apply():
            if self.tablet is None or self._stop_requested.is_set():
                return
            try:
                operation()
            except Exception as error:
                logger.exception("Tablet settings rejected")
                self.sig_log.emit(f"Tablet settings could not be applied: {error}")
                if isinstance(error, OSError):
                    self._on_device_error(str(error))
        with self._state_lock:
            loop = self._loop
            if loop:
                loop.call_soon_threadsafe(apply)
                return
        # Allows explicitly supplied test backends without starting a worker.
        if self._thread is None:
            apply()

    def update_tablet_settings(self, **kwargs):
        changes = copy.deepcopy(kwargs)
        self._submit(lambda: self.tablet.update_settings(**changes))

    def open_pairing(self):
        def begin():
            if self.server is not None:
                self.server.pairing_manager.lan_address = get_local_ip()
                self.server.pairing_manager.open_window()
                self.sig_pairing_ready.emit()
        self._submit(begin)

    def answer_pairing(self, token, approved):
        self._submit(lambda: self.server.pairing_manager.decide(token, approved) if self.server else None)

    def cancel_pairing(self):
        self._submit(lambda: self.server.pairing_manager.cancel() if self.server else None)

    def apply_config(self, config=None):
        snapshot = copy.deepcopy(config if config is not None else self.config)
        self._submit(lambda: self._apply_config(snapshot))

    def _apply_config(self, config):
        options = effective_settings(config)
        current = self.tablet
        changed = any(getattr(current, key) != options[key] for key in ("mode", "direct_mode", "name"))
        if changed and sys.platform != "win32":
            replacement = create_tablet_backend(**options, on_event_processed=self._on_tablet_event)
            try:
                current.close()
            except Exception:
                replacement.close()
                self._stop_requested.set()
                if self._stop_async:
                    self._stop_async.set()
                raise
            self.tablet = replacement
            if self.server:
                self.server.tablet = replacement
        else:
            current.update_settings(**runtime_settings(options))
            # Windows has a single installed device; these are persisted Linux
            # preferences only and must not cause another exclusive open.
            current.mode, current.direct_mode, current.name = options["mode"], options["direct_mode"], options["name"]

    def set_device_mode(self, mode=None, direct_mode=None, device_name=None):
        snapshot = copy.deepcopy(self.config)
        profile = snapshot.get_active_profile()
        if mode is not None:
            profile.device_mode = mode
        if direct_mode is not None:
            profile.direct_mode = direct_mode
        if device_name is not None:
            snapshot.device_name = device_name
        self.apply_config(snapshot)
