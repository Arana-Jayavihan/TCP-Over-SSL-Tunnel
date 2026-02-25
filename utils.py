"""Utility functions for TCP-Over-SSL-Tunnel."""

import asyncio
import socket
import struct
from pathlib import Path
from subprocess import DEVNULL, Popen
from typing import Optional

import asyncssh

from config import Config
from exceptions import (
    ProxyConnectionError,
    SSHConnectionError,
)
from logger import get_logger

logger = get_logger()


def http_proxy_process(config: Config) -> Popen:
    """
    Launch pproxy HTTP-to-SOCKS bridge process.

    Args:
        config: Application configuration

    Returns:
        Popen process handle
    """
    logger.info("Starting HTTP proxy bridge")
    address = config.settings.local_ip
    if config.http_proxy.expose:
        address = "0.0.0.0"
        logger.warning("HTTP proxy exposed on all interfaces")

    cmd = [
        "pproxy",
        "-l", f"http://{address}:{config.http_proxy.http_port}",
        "-r", f"socks5://{config.settings.local_ip}:{config.settings.socks_port}",
    ]
    proc = Popen(cmd, stdout=DEVNULL, stderr=DEVNULL)
    logger.info(f"HTTP proxy listening on {address}:{config.http_proxy.http_port}")
    return proc


def http_proxy_connect_sync(
    proxy_host: str,
    proxy_port: int,
    target_host: str,
    target_port: int,
) -> socket.socket:
    """
    Establish connection through HTTP CONNECT proxy (synchronous).

    Returns a raw socket that can be passed to asyncssh.

    Args:
        proxy_host: Proxy server host
        proxy_port: Proxy server port
        target_host: Target host to connect to
        target_port: Target port

    Returns:
        Connected socket through the proxy tunnel

    Raises:
        ProxyConnectionError: If proxy connection fails
    """
    try:
        sock = socket.create_connection((proxy_host, proxy_port), timeout=30)
    except OSError as e:
        raise ProxyConnectionError(f"Failed to connect to proxy {proxy_host}:{proxy_port}") from e

    connect_req = (
        f"CONNECT {target_host}:{target_port} HTTP/1.1\r\n"
        f"Host: {target_host}:{target_port}\r\n"
        f"\r\n"
    )
    sock.sendall(connect_req.encode())

    response = b""
    while b"\r\n\r\n" not in response:
        chunk = sock.recv(4096)
        if not chunk:
            sock.close()
            raise ProxyConnectionError("Proxy closed connection unexpectedly")
        response += chunk

    status_line = response.split(b"\r\n", 1)[0]
    if not (status_line.startswith(b"HTTP/1.1 200") or status_line.startswith(b"HTTP/1.0 200")):
        sock.close()
        raise ProxyConnectionError(f"Proxy CONNECT failed: {status_line.decode(errors='ignore')}")

    sock.setblocking(False)
    logger.debug(f"Connected to {target_host}:{target_port} via HTTP proxy")
    return sock


async def init_ssh(config: Config) -> asyncssh.SSHClientConnection:
    """
    Initialize SSH connection through HTTP proxy tunnel.

    Args:
        config: Application configuration

    Returns:
        SSH client connection

    Raises:
        SSHConnectionError: If SSH connection fails
    """
    loop = asyncio.get_running_loop()

    # Create proxy connection in executor to not block event loop
    proxy_sock = await loop.run_in_executor(
        None,
        http_proxy_connect_sync,
        config.settings.local_ip,
        config.settings.listen_port,
        config.ssh.host,
        config.ssh.port,
    )

    try:
        # Disable host key verification since we connect through a proxy
        # The socket connects to 127.0.0.1 but the actual host is the SSH server.
        # This mirrors the original behavior with paramiko's AutoAddPolicy.
        # For better security, users should configure ssh.host_key_fingerprint.
        connect_kwargs = {
            "username": config.ssh.username,
            "known_hosts": None,  # Disable host key checking (like AutoAddPolicy)
            "compression_algs": ["zlib@openssh.com", "zlib", "none"],
        }

        logger.warning("SSH host key verification disabled (proxy mode)")

        if config.ssh.key_file and config.ssh.key_file.exists():
            connect_kwargs["client_keys"] = [str(config.ssh.key_file)]
            logger.debug(f"Using SSH key: {config.ssh.key_file}")
        elif config.ssh.password:
            connect_kwargs["password"] = config.ssh.password

        conn = await asyncssh.connect(
            sock=proxy_sock,
            **connect_kwargs,
        )

        logger.info(f"SSH connection established to {config.ssh.host}:{config.ssh.port}")
        return conn

    except asyncssh.DisconnectError as e:
        proxy_sock.close()
        raise SSHConnectionError(f"SSH disconnected: {e}") from e
    except asyncssh.PermissionDenied as e:
        proxy_sock.close()
        raise SSHConnectionError(f"SSH authentication failed: {e}") from e
    except Exception as e:
        proxy_sock.close()
        raise SSHConnectionError(f"SSH connection failed: {e}") from e


async def handle_socks_client(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    ssh_conn: asyncssh.SSHClientConnection,
    stop_event: asyncio.Event,
) -> None:
    """
    Handle a single SOCKS5 client connection.

    Args:
        reader: Client stream reader
        writer: Client stream writer
        ssh_conn: SSH connection for tunneling
        stop_event: Shutdown signal
    """
    addr = writer.get_extra_info("peername")
    logger.debug(f"SOCKS5 client connected: {addr}")

    try:
        data = await asyncio.wait_for(reader.read(2), timeout=30)
        if len(data) < 2:
            return

        ver, nmethods = struct.unpack("!BB", data)
        if ver != 5:
            logger.warning(f"Unsupported SOCKS version: {ver}")
            return

        await reader.read(nmethods)
        writer.write(b"\x05\x00")
        await writer.drain()

        data = await asyncio.wait_for(reader.read(4), timeout=30)
        if len(data) < 4:
            return

        ver, cmd, _, atyp = struct.unpack("!BBBB", data)

        if cmd != 1:
            writer.write(b"\x05\x07\x00\x01" + b"\x00" * 6)
            await writer.drain()
            return

        if atyp == 1:
            raw_addr = await reader.read(4)
            target_addr = socket.inet_ntoa(raw_addr)
        elif atyp == 3:
            length = (await reader.read(1))[0]
            target_addr = (await reader.read(length)).decode()
        elif atyp == 4:
            raw_addr = await reader.read(16)
            target_addr = socket.inet_ntop(socket.AF_INET6, raw_addr)
        else:
            writer.write(b"\x05\x08\x00\x01" + b"\x00" * 6)
            await writer.drain()
            return

        port_data = await reader.read(2)
        target_port = struct.unpack("!H", port_data)[0]

        reply = b"\x05\x00\x00\x01" + socket.inet_aton("0.0.0.0") + struct.pack("!H", 0)
        writer.write(reply)
        await writer.drain()

        logger.debug(f"SOCKS5 connecting to {target_addr}:{target_port}")

        try:
            channel_reader, channel_writer = await ssh_conn.open_connection(
                target_addr, target_port
            )
        except asyncssh.ChannelOpenError as e:
            logger.error(f"Failed to open SSH channel: {e}")
            return

        await relay_streams(reader, writer, channel_reader, channel_writer, stop_event)

    except asyncio.TimeoutError:
        logger.debug(f"SOCKS5 client timeout: {addr}")
    except Exception as e:
        logger.debug(f"SOCKS5 client error: {e}")
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass


async def relay_streams(
    client_reader: asyncio.StreamReader,
    client_writer: asyncio.StreamWriter,
    remote_reader: asyncio.StreamReader,
    remote_writer: asyncio.StreamWriter,
    stop_event: asyncio.Event,
    bufsize: int = 65536,
) -> None:
    """
    Relay data bidirectionally between two stream pairs.

    Args:
        client_reader: Client read stream
        client_writer: Client write stream
        remote_reader: Remote read stream
        remote_writer: Remote write stream
        stop_event: Shutdown signal
        bufsize: Buffer size for reads
    """

    async def forward(
        src: asyncio.StreamReader,
        dst: asyncio.StreamWriter,
        name: str,
    ) -> None:
        try:
            while not stop_event.is_set():
                data = await asyncio.wait_for(src.read(bufsize), timeout=1.0)
                if not data:
                    break
                dst.write(data)
                await dst.drain()
        except asyncio.TimeoutError:
            pass
        except Exception:
            pass

    await asyncio.gather(
        forward(client_reader, remote_writer, "client->remote"),
        forward(remote_reader, client_writer, "remote->client"),
        return_exceptions=True,
    )

    for writer in (client_writer, remote_writer):
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass


async def start_socks_server(
    config: Config,
    ssh_conn: asyncssh.SSHClientConnection,
    stop_event: asyncio.Event,
    connection_semaphore: asyncio.Semaphore,
) -> None:
    """
    Start SOCKS5 proxy server.

    Args:
        config: Application configuration
        ssh_conn: SSH connection for tunneling
        stop_event: Shutdown signal
        connection_semaphore: Semaphore for connection limiting
    """
    local_ip = config.settings.local_ip
    local_port = config.settings.socks_port

    async def client_handler(
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        if not connection_semaphore.locked():
            async with connection_semaphore:
                await handle_socks_client(reader, writer, ssh_conn, stop_event)
        else:
            logger.warning("Connection limit reached, rejecting client")
            writer.close()
            await writer.wait_closed()

    server = await asyncio.start_server(
        client_handler,
        local_ip,
        local_port,
        reuse_address=True,
    )

    logger.info(f"SOCKS5 proxy listening on {local_ip}:{local_port}")

    async with server:
        while not stop_event.is_set():
            await asyncio.sleep(1)

    server.close()
    await server.wait_closed()
    logger.info("SOCKS5 proxy stopped")


async def keep_ssh_alive(
    config: Config,
    stop_event: asyncio.Event,
    connection_semaphore: asyncio.Semaphore,
) -> None:
    """
    Maintain SSH connection with auto-reconnect.

    Args:
        config: Application configuration
        stop_event: Shutdown signal
        connection_semaphore: Semaphore for connection limiting
    """
    ssh_conn: Optional[asyncssh.SSHClientConnection] = None
    socks_task: Optional[asyncio.Task] = None

    while not stop_event.is_set():
        try:
            if ssh_conn is None:
                logger.info("Establishing SSH connection...")
                ssh_conn = await init_ssh(config)

                socks_task = asyncio.create_task(
                    start_socks_server(config, ssh_conn, stop_event, connection_semaphore)
                )

            await asyncio.sleep(5)

            # Check if SOCKS server task is still running (connection is alive)
            if socks_task and not socks_task.done():
                continue

            logger.warning("SSH connection dropped, reconnecting...")
            if socks_task:
                socks_task.cancel()
                try:
                    await socks_task
                except asyncio.CancelledError:
                    pass
            ssh_conn = None
            await asyncio.sleep(2)

        except SSHConnectionError as e:
            logger.error(f"SSH error: {e}, retrying in 5 seconds...")
            if ssh_conn:
                ssh_conn.close()
            ssh_conn = None
            if socks_task:
                socks_task.cancel()
            await asyncio.sleep(5)

        except Exception as e:
            logger.error(f"Unexpected error: {e}, retrying in 5 seconds...")
            if ssh_conn:
                try:
                    ssh_conn.close()
                except Exception:
                    pass
            ssh_conn = None
            if socks_task:
                socks_task.cancel()
            await asyncio.sleep(5)

    if socks_task:
        socks_task.cancel()
        try:
            await socks_task
        except asyncio.CancelledError:
            pass

    if ssh_conn:
        ssh_conn.close()
        await ssh_conn.wait_closed()

    logger.info("SSH keepalive stopped")
