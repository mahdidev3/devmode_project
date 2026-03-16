\
import asyncio
import os
import signal
import ssl
from pathlib import Path
from typing import Dict, Optional, Tuple
from urllib.parse import urlsplit

from .config import AppConfig
from .runtime import remove_state_files, write_info_file
from .security import decode_basic_auth, encode_basic_auth
from .userdb import UserDB


def parse_host_port_from_connect(target: str) -> Tuple[str, int]:
    if ":" not in target:
        raise ValueError(f"Invalid CONNECT target: {target!r}")
    host, port_str = target.rsplit(":", 1)
    return host.strip(), int(port_str)


def parse_host_port_from_http_target(target: str, headers: Dict[str, str]) -> Tuple[str, int]:
    parsed = urlsplit(target)
    if parsed.scheme and parsed.hostname:
        return parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80)
    host_header = headers.get("host")
    if not host_header:
        raise ValueError("Missing Host header")
    if ":" in host_header:
        host, port_str = host_header.rsplit(":", 1)
        return host.strip(), int(port_str)
    return host_header.strip(), 80


class BaseConnection:
    def __init__(self, config: AppConfig, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        self.config = config
        self.userdb = UserDB(config.users_file)
        self.client_reader = reader
        self.client_writer = writer
        self.remote_reader: Optional[asyncio.StreamReader] = None
        self.remote_writer: Optional[asyncio.StreamWriter] = None

    async def handle(self) -> None:
        try:
            header_block, buffered_body = await self._read_request_head_and_body_prefix(self.client_reader)
            if not header_block:
                return
            method, target, version, headers = self._parse_request_headers(header_block)
            if self.config.auth_enabled and not self._is_authorized(headers):
                await self._send_auth_required()
                return
            await self.dispatch(method, target, version, headers, buffered_body)
        except asyncio.IncompleteReadError:
            pass
        except Exception as exc:
            await self._safe_send_error(502, f"Bad Gateway: {exc}")
        finally:
            await self._cleanup()

    def _is_authorized(self, headers: Dict[str, str]) -> bool:
        username, password = decode_basic_auth(headers)
        if not (username and password is not None and self.userdb.verify(username, password)):
            return False
        if self.config.allowed_user and username != self.config.allowed_user:
            return False
        return True

    async def _send_auth_required(self) -> None:
        body = f"Authentication required for {self.config.app_name}.\n".encode("utf-8")
        response = (
            b"HTTP/1.1 407 Proxy Authentication Required\r\n"
            + f'Proxy-Authenticate: Basic realm="{self.config.app_name}"\r\n'.encode("latin1")
            + b"Content-Type: text/plain; charset=utf-8\r\n"
            + f"Content-Length: {len(body)}\r\n".encode("latin1")
            + b"Connection: close\r\n\r\n"
            + body
        )
        self.client_writer.write(response)
        await self.client_writer.drain()

    async def dispatch(self, method: str, target: str, version: str, headers: Dict[str, str], buffered_body: bytes) -> None:
        raise NotImplementedError

    async def _pipe(self, src: asyncio.StreamReader, dst: asyncio.StreamWriter, bufsize: int = 65536) -> None:
        try:
            while True:
                chunk = await src.read(bufsize)
                if not chunk:
                    break
                dst.write(chunk)
                await dst.drain()
        except (ConnectionResetError, BrokenPipeError):
            pass
        finally:
            if not dst.is_closing():
                dst.close()

    async def _read_request_head_and_body_prefix(self, reader: asyncio.StreamReader, limit: int = 65536):
        data = b""
        while b"\r\n\r\n" not in data:
            chunk = await reader.read(4096)
            if not chunk:
                break
            data += chunk
            if len(data) > limit:
                raise ValueError("Header too large")
        head, sep, rest = data.partition(b"\r\n\r\n")
        if not sep:
            return b"", b""
        return head + sep, rest

    def _parse_request_headers(self, header_block: bytes):
        head, _, _ = header_block.partition(b"\r\n\r\n")
        lines = head.split(b"\r\n")
        if not lines:
            raise ValueError("Empty request")
        request_line = lines[0].decode("latin1")
        parts = request_line.split(" ", 2)
        if len(parts) != 3:
            raise ValueError(f"Invalid request line: {request_line!r}")
        method, target, version = parts
        headers = {}
        for raw in lines[1:]:
            if b":" not in raw:
                continue
            k, v = raw.split(b":", 1)
            headers[k.decode("latin1").strip().lower()] = v.decode("latin1").strip()
        return method.upper(), target, version, headers

    def _rebuild_direct_request(self, method: str, target: str, version: str, headers: Dict[str, str]):
        parsed = urlsplit(target)
        if parsed.scheme and parsed.netloc:
            path = parsed.path or "/"
            if parsed.query:
                path += "?" + parsed.query
        else:
            path = target or "/"

        hop_by_hop = {
            "proxy-authorization",
            "proxy-connection",
            "connection",
            "keep-alive",
            "te",
            "trailer",
            "transfer-encoding",
            "upgrade",
        }
        clean_headers = [(k, v) for k, v in headers.items() if k.lower() not in hop_by_hop]
        clean_headers.append(("connection", "close"))
        request_line = f"{method} {path} {version}\r\n".encode("latin1")
        header_bytes = b"".join(f"{k}: {v}\r\n".encode("latin1") for k, v in clean_headers)
        return request_line, header_bytes

    def _rebuild_upstream_request(self, method: str, target: str, version: str, headers: Dict[str, str], connect_target: Optional[str] = None):
        hop_by_hop = {
            "proxy-authorization",
            "proxy-connection",
            "connection",
            "keep-alive",
            "te",
            "trailer",
            "transfer-encoding",
            "upgrade",
        }
        clean_headers = [(k, v) for k, v in headers.items() if k.lower() not in hop_by_hop]
        if self.config.upstream_username and self.config.upstream_password:
            clean_headers.append(("Proxy-Authorization", encode_basic_auth(self.config.upstream_username, self.config.upstream_password)))
        clean_headers.append(("connection", "close"))
        request_target = connect_target or target
        request_line = f"{method} {request_target} {version}\r\n".encode("latin1")
        header_bytes = b"".join(f"{k}: {v}\r\n".encode("latin1") for k, v in clean_headers)
        return request_line, header_bytes

    async def _safe_send_error(self, code: int, message: str) -> None:
        if self.client_writer.is_closing():
            return
        body = (message + "\n").encode("utf-8", errors="replace")
        response = (
            f"HTTP/1.1 {code} Error\r\nContent-Length: {len(body)}\r\nConnection: close\r\nContent-Type: text/plain; charset=utf-8\r\n\r\n".encode("latin1")
            + body
        )
        try:
            self.client_writer.write(response)
            await self.client_writer.drain()
        except Exception:
            pass

    async def _cleanup(self) -> None:
        for writer in (self.remote_writer, self.client_writer):
            if writer and not writer.is_closing():
                writer.close()
        for writer in (self.remote_writer, self.client_writer):
            if writer:
                try:
                    await writer.wait_closed()
                except Exception:
                    pass


class DirectProxyConnection(BaseConnection):
    async def dispatch(self, method: str, target: str, version: str, headers: Dict[str, str], buffered_body: bytes) -> None:
        if method == "CONNECT":
            host, port = parse_host_port_from_connect(target)
            await self._handle_connect(host, port)
            return
        host, port = parse_host_port_from_http_target(target, headers)
        await self._handle_http_forward(method, target, version, headers, host, port, buffered_body)

    async def _handle_connect(self, host: str, port: int) -> None:
        self.remote_reader, self.remote_writer = await asyncio.open_connection(host, port)
        self.client_writer.write(b"HTTP/1.1 200 Connection established\r\n\r\n")
        await self.client_writer.drain()
        await asyncio.gather(
            self._pipe(self.client_reader, self.remote_writer),
            self._pipe(self.remote_reader, self.client_writer),
            return_exceptions=True,
        )

    async def _handle_http_forward(self, method: str, target: str, version: str, headers: Dict[str, str], host: str, port: int, buffered_body: bytes) -> None:
        self.remote_reader, self.remote_writer = await asyncio.open_connection(host, port)
        request_line, rebuilt_headers = self._rebuild_direct_request(method, target, version, headers)
        outbound = request_line + rebuilt_headers + b"\r\n"
        content_length = int(headers.get("content-length", "0") or "0")
        body = buffered_body
        if content_length > len(body):
            body += await self.client_reader.readexactly(content_length - len(body))
        self.remote_writer.write(outbound + body)
        await self.remote_writer.drain()
        await asyncio.gather(
            self._pipe(self.client_reader, self.remote_writer),
            self._pipe(self.remote_reader, self.client_writer),
            return_exceptions=True,
        )


class TunnelProxyConnection(BaseConnection):
    async def dispatch(self, method: str, target: str, version: str, headers: Dict[str, str], buffered_body: bytes) -> None:
        if not self.config.upstream_host or not self.config.upstream_port:
            raise ValueError("Tunnel upstream is not configured")
        ssl_context = None
        if self.config.upstream_scheme == "https":
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
        self.remote_reader, self.remote_writer = await asyncio.open_connection(
            self.config.upstream_host,
            self.config.upstream_port,
            ssl=ssl_context,
            server_hostname=self.config.upstream_host if ssl_context else None,
        )
        if method == "CONNECT":
            await self._handle_connect_via_upstream(method, target, version, headers)
        else:
            await self._handle_http_via_upstream(method, target, version, headers, buffered_body)

    async def _handle_connect_via_upstream(self, method: str, target: str, version: str, headers: Dict[str, str]) -> None:
        request_line, rebuilt_headers = self._rebuild_upstream_request(method, target, version, headers, connect_target=target)
        self.remote_writer.write(request_line + rebuilt_headers + b"\r\n")
        await self.remote_writer.drain()
        upstream_head, upstream_body = await self._read_request_head_and_body_prefix(self.remote_reader)
        if not upstream_head:
            raise ValueError("Upstream proxy closed CONNECT response")
        self.client_writer.write(upstream_head + upstream_body)
        await self.client_writer.drain()
        if b" 200 " not in upstream_head.split(b"\r\n", 1)[0]:
            return
        await asyncio.gather(
            self._pipe(self.client_reader, self.remote_writer),
            self._pipe(self.remote_reader, self.client_writer),
            return_exceptions=True,
        )

    async def _handle_http_via_upstream(self, method: str, target: str, version: str, headers: Dict[str, str], buffered_body: bytes) -> None:
        absolute_target = target
        if not urlsplit(target).scheme:
            host = headers.get("host")
            if not host:
                raise ValueError("Missing Host header")
            absolute_target = f"http://{host}{target}"
        request_line, rebuilt_headers = self._rebuild_upstream_request(method, absolute_target, version, headers)
        outbound = request_line + rebuilt_headers + b"\r\n"
        content_length = int(headers.get("content-length", "0") or "0")
        body = buffered_body
        if content_length > len(body):
            body += await self.client_reader.readexactly(content_length - len(body))
        self.remote_writer.write(outbound + body)
        await self.remote_writer.drain()
        await asyncio.gather(
            self._pipe(self.client_reader, self.remote_writer),
            self._pipe(self.remote_reader, self.client_writer),
            return_exceptions=True,
        )


class ProxyServer:
    def __init__(self, config: AppConfig):
        self.config = config

    def build_ssl_context(self) -> Optional[ssl.SSLContext]:
        if not self.config.tls_enabled:
            return None
        if not self.config.tls_cert or not self.config.tls_key:
            raise FileNotFoundError(f"TLS files not configured for {self.config.app_name}")
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(certfile=str(self.config.tls_cert), keyfile=str(self.config.tls_key))
        return context

    def write_state(self, port: int) -> None:
        self.config.state_dir.mkdir(parents=True, exist_ok=True)
        instance_info_file = Path(os.environ.get("DEVMODE_INSTANCE_INFO_FILE", str(self.config.info_file)))
        instance_log_file = Path(os.environ.get("DEVMODE_INSTANCE_LOG_FILE", str(self.config.log_file)))
        instance_id = os.environ.get("DEVMODE_INSTANCE_ID", "default")
        if instance_info_file == self.config.info_file:
            self.config.pid_file.write_text(str(os.getpid()), encoding="utf-8")
            self.config.port_file.write_text(str(port), encoding="utf-8")
        write_info_file(
            instance_info_file,
            {
                "app": self.config.app_name,
                "instance_id": instance_id,
                "app_key": self.config.app_key,
                "mode_kind": self.config.mode_kind,
                "scheme": self.config.listen_scheme,
                "auth_enabled": self.config.auth_enabled,
                "pid": os.getpid(),
                "host": self.config.host,
                "port": port,
                "run_dir": str(self.config.state_dir),
                "log_file": str(instance_log_file),
                "users_file": str(self.config.users_file),
                "tls_cert": str(self.config.tls_cert) if self.config.tls_cert else None,
                "tls_key": str(self.config.tls_key) if self.config.tls_key else None,
                "upstream_url": self.config.upstream_url,
                "allowed_user": self.config.allowed_user,
            },
        )

    async def start(self) -> None:
        loop = asyncio.get_running_loop()

        async def on_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
            connection_cls = TunnelProxyConnection if self.config.mode_kind == "tunnel" else DirectProxyConnection
            connection = connection_cls(self.config, reader, writer)
            await connection.handle()

        ssl_context = self.build_ssl_context()
        server = await asyncio.start_server(
            on_client,
            host=self.config.host,
            port=self.config.port,
            ssl=ssl_context,
            start_serving=True,
        )
        sockets = server.sockets or []
        if not sockets:
            raise RuntimeError("No listening sockets created")
        port = sockets[0].getsockname()[1]
        self.write_state(port)

        stop_event = asyncio.Event()

        def stop_handler():
            stop_event.set()

        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, stop_handler)
            except NotImplementedError:
                pass

        try:
            await stop_event.wait()
        finally:
            server.close()
            await server.wait_closed()
            instance_info_file = Path(os.environ.get("DEVMODE_INSTANCE_INFO_FILE", str(self.config.info_file)))
            if instance_info_file == self.config.info_file:
                remove_state_files(self.config.pid_file, self.config.port_file, self.config.info_file)
            else:
                remove_state_files(instance_info_file)


def run_server(config: AppConfig) -> None:
    server = ProxyServer(config)
    asyncio.run(server.start())
