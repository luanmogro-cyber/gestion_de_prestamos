import os
import sys
import json
import socket
import logging
import threading
from pathlib import Path
from typing import Dict, Any, Optional, Callable

logger = logging.getLogger("prestamos.ipc")

class UnixSocketServer:
    """
    Servidor IPC mediante Socket Unix (~/.local/share/gestion_prestamos/ipc.sock).
    Permite a la GUI enviar comandos al demonio:
    - FORZAR_RESPALDO
    - VERIFICAR_ALERTAS
    - ESTADO_DEMONIO
    - PING
    """
    def __init__(self, socket_path: Path):
        self.socket_path = socket_path
        self.server_sock: Optional[socket.socket] = None
        self.is_running = False
        self.thread: Optional[threading.Thread] = None
        self.command_handlers: Dict[str, Callable[[Dict[str, Any]], Dict[str, Any]]] = {}

    def register_handler(self, command: str, handler: Callable[[Dict[str, Any]], Dict[str, Any]]):
        self.command_handlers[command.upper()] = handler

    def start(self):
        if not hasattr(socket, "AF_UNIX"):
            logger.warning("AF_UNIX no disponible en este sistema operativo (no POSIX). IPC socket desactivado.")
            return

        self.socket_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self.socket_path.parent, 0o700)
        except (OSError, NotImplementedError):
            pass

        # Eliminar socket previo si quedó residual
        if self.socket_path.exists():
            try:
                self.socket_path.unlink()
            except OSError as e:
                logger.warning(f"No se pudo eliminar socket existente {self.socket_path}: {e}")

        self.server_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.server_sock.bind(str(self.socket_path))
        
        # Permisos estrictos 600 en el socket
        try:
            os.chmod(self.socket_path, 0o600)
        except (OSError, NotImplementedError):
            pass

        self.server_sock.listen(5)
        self.is_running = True

        self.thread = threading.Thread(target=self._listen_loop, daemon=True, name="IPCServerThread")
        self.thread.start()
        logger.info(f"Servidor IPC Socket Unix escuchando en {self.socket_path}")

    def _listen_loop(self):
        while self.is_running and self.server_sock:
            try:
                conn, _ = self.server_sock.accept()
                client_thread = threading.Thread(target=self._handle_client, args=(conn,), daemon=True)
                client_thread.start()
            except OSError:
                break
            except Exception as e:
                logger.error(f"Error en bucle de escucha IPC: {e}")

    def _handle_client(self, conn: socket.socket):
        with conn:
            try:
                data = b""
                while True:
                    chunk = conn.recv(4096)
                    if not chunk:
                        break
                    data += chunk
                    if b"\n" in chunk:
                        break

                if not data:
                    return

                msg_str = data.decode("utf-8").strip()
                request = json.loads(msg_str)
                cmd = str(request.get("command", "")).upper()
                params = request.get("params", {})

                if cmd in self.command_handlers:
                    response = self.command_handlers[cmd](params)
                else:
                    response = {"status": "error", "message": f"Comando desconocido: {cmd}"}

                out_bytes = (json.dumps(response) + "\n").encode("utf-8")
                conn.sendall(out_bytes)
            except Exception as e:
                logger.error(f"Error procesando solicitud cliente IPC: {e}")
                err_resp = (json.dumps({"status": "error", "message": str(e)}) + "\n").encode("utf-8")
                try:
                    conn.sendall(err_resp)
                except OSError:
                    pass

    def stop(self):
        self.is_running = False
        if self.server_sock:
            try:
                self.server_sock.close()
            except OSError:
                pass
            self.server_sock = None

        if self.socket_path.exists():
            try:
                self.socket_path.unlink()
            except OSError:
                pass
        logger.info("Servidor IPC Socket Unix detenido.")


class UnixSocketClient:
    """
    Cliente IPC utilizado por la GUI (prestamos-gui) para interactuar con prestamos-daemon.
    """
    def __init__(self, socket_path: Path):
        self.socket_path = socket_path

    def is_daemon_active(self) -> bool:
        if not hasattr(socket, "AF_UNIX"):
            return False
        if not self.socket_path.exists():
            return False
        res = self.send_command("PING")
        return res.get("status") == "pong" or res.get("status") == "ok"

    def send_command(self, command: str, params: Optional[Dict[str, Any]] = None, timeout: float = 3.0) -> Dict[str, Any]:
        if not hasattr(socket, "AF_UNIX"):
            return {"status": "error", "message": "AF_UNIX no soportado en este SO"}

        if not self.socket_path.exists():
            return {"status": "error", "message": f"Socket no encontrado en {self.socket_path}. ¿Está el demonio activo?"}

        try:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            sock.connect(str(self.socket_path))
            
            payload = json.dumps({"command": command.upper(), "params": params or {}}) + "\n"
            sock.sendall(payload.encode("utf-8"))

            data = b""
            while True:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                data += chunk
                if b"\n" in chunk:
                    break
            
            sock.close()
            if not data:
                return {"status": "error", "message": "Respuesta vacía del demonio"}
            return json.loads(data.decode("utf-8").strip())
        except socket.timeout:
            return {"status": "error", "message": "Tiempo de espera agotado al comunicarse con el demonio"}
        except ConnectionRefusedError:
            return {"status": "error", "message": "Conexión rechazada. El demonio no está respondiendo."}
        except Exception as e:
            return {"status": "error", "message": f"Error de comunicación IPC: {e}"}


