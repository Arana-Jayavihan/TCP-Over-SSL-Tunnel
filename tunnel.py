"""SSL/TLS Tunnel with SNI injection for TCP-Over-SSL-Tunnel."""

import asyncio
import ssl
from typing import Optional

from config import Config
from exceptions import TLSHandshakeError, TunnelError
from logger import get_logger

logger = get_logger()


class Tunnel:
    """
    Async SSL/TLS tunnel with SNI injection.

    Listens for incoming connections, wraps them in TLS with custom SNI,
    and relays traffic bidirectionally.
    """

    def __init__(
        self,
        config: Config,
        stop_event: asyncio.Event,
        connection_semaphore: asyncio.Semaphore,
    ) -> None:
        """
        Initialize tunnel.

        Args:
            config: Application configuration
            stop_event: Shutdown signal
            connection_semaphore: Semaphore for connection limiting
        """
        self.config = config
        self.stop_event = stop_event
        self.connection_semaphore = connection_semaphore
        self.ready_event = asyncio.Event()

        self.host = config.ssh.host
        self.sni_hostname = config.sni.server_name
        self.local_ip = config.settings.local_ip
        self.listen_port = config.settings.listen_port
        self.ssh_port = config.ssh.port

        self._server: Optional[asyncio.Server] = None
        self._tasks: set[asyncio.Task] = set()

    def _create_ssl_context(self) -> ssl.SSLContext:
        """
        Create SSL context for SNI injection tunnel.

        Note: Certificate verification is disabled because SNI injection
        uses a different hostname than the actual server, so cert validation
        would always fail. This is intentional for this use case.

        Returns:
            Configured SSLContext for SNI tunneling
        """
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        context.minimum_version = ssl.TLSVersion.TLSv1_2

        return context

    async def start(self) -> None:
        """Start the tunnel server."""
        self._server = await asyncio.start_server(
            self._handle_client,
            self.local_ip,
            self.listen_port,
            reuse_address=True,
        )

        logger.info(f"Tunnel listening on {self.local_ip}:{self.listen_port}")
        logger.info(f"SNI hostname: {self.sni_hostname}")
        self.ready_event.set()

        async with self._server:
            while not self.stop_event.is_set():
                await asyncio.sleep(1)

        await self.stop()

    async def stop(self) -> None:
        """Stop the tunnel server and cleanup."""
        logger.info("Stopping tunnel...")
        self.stop_event.set()

        if self._server:
            self._server.close()
            await self._server.wait_closed()

        for task in self._tasks:
            task.cancel()

        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)

        self._tasks.clear()
        logger.info("Tunnel stopped")

    async def _handle_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        """
        Handle incoming client connection.

        Args:
            reader: Client stream reader
            writer: Client stream writer
        """
        addr = writer.get_extra_info("peername")

        if self.connection_semaphore.locked():
            logger.warning(f"Connection limit reached, rejecting {addr}")
            writer.close()
            await writer.wait_closed()
            return

        task = asyncio.current_task()
        if task:
            self._tasks.add(task)

        try:
            async with self.connection_semaphore:
                await self._process_client(reader, writer, addr)
        finally:
            if task:
                self._tasks.discard(task)

    async def _process_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        addr: tuple,
    ) -> None:
        """
        Process client connection request.

        Args:
            reader: Client stream reader
            writer: Client stream writer
            addr: Client address tuple
        """
        logger.info(f"New client connected: {addr}")

        ssl_reader: Optional[asyncio.StreamReader] = None
        ssl_writer: Optional[asyncio.StreamWriter] = None

        try:
            request = await asyncio.wait_for(reader.read(16384), timeout=30)
            if not request:
                return

            request_str = request.decode(errors="ignore")
            port = self._parse_connect_port(request_str)

            ssl_reader, ssl_writer = await self._establish_ssl_connection(port)

            writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            await writer.drain()

            logger.info(f"Connection established for {addr}")
            await self._relay(reader, writer, ssl_reader, ssl_writer)

        except asyncio.TimeoutError:
            logger.warning(f"Client timeout: {addr}")
        except TLSHandshakeError as e:
            logger.error(f"TLS handshake failed: {e}")
        except Exception as e:
            logger.error(f"Client error: {e}")
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass

            if ssl_writer:
                ssl_writer.close()
                try:
                    await ssl_writer.wait_closed()
                except Exception:
                    pass

            logger.info(f"Client disconnected: {addr}")

    def _parse_connect_port(self, request: str) -> int:
        """
        Parse port from CONNECT request.

        Args:
            request: HTTP CONNECT request string

        Returns:
            Target port number
        """
        try:
            port_str = request.split(":")[1].split()[0]
            return int(port_str)
        except (IndexError, ValueError):
            return self.ssh_port

    async def _establish_ssl_connection(
        self,
        port: int,
    ) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        """
        Establish SSL/TLS connection with SNI injection.

        Args:
            port: Target port

        Returns:
            Tuple of (reader, writer) for SSL connection

        Raises:
            TLSHandshakeError: If TLS handshake fails
        """
        ssl_context = self._create_ssl_context()

        try:
            reader, writer = await asyncio.open_connection(
                self.host,
                port,
                ssl=ssl_context,
                server_hostname=self.sni_hostname,
            )

            ssl_obj = writer.get_extra_info("ssl_object")
            if ssl_obj:
                cipher = ssl_obj.cipher()
                if cipher:
                    logger.debug(f"Ciphersuite: {cipher[0]}")
                version = ssl_obj.version()
                if version:
                    logger.debug(f"TLS version: {version}")

            logger.info(f"TLS handshake successful with SNI: {self.sni_hostname}")
            return reader, writer

        except ssl.SSLCertVerificationError as e:
            raise TLSHandshakeError(f"Certificate verification failed: {e}") from e
        except ssl.SSLError as e:
            raise TLSHandshakeError(f"SSL error: {e}") from e
        except OSError as e:
            raise TLSHandshakeError(f"Connection failed: {e}") from e

    async def _relay(
        self,
        client_reader: asyncio.StreamReader,
        client_writer: asyncio.StreamWriter,
        remote_reader: asyncio.StreamReader,
        remote_writer: asyncio.StreamWriter,
        bufsize: int = 16384,
    ) -> None:
        """
        Relay data bidirectionally between client and remote.

        Args:
            client_reader: Client read stream
            client_writer: Client write stream
            remote_reader: Remote read stream
            remote_writer: Remote write stream
            bufsize: Buffer size for reads
        """

        async def forward(
            src: asyncio.StreamReader,
            dst: asyncio.StreamWriter,
            name: str,
        ) -> None:
            try:
                while not self.stop_event.is_set():
                    try:
                        data = await asyncio.wait_for(src.read(bufsize), timeout=3.0)
                    except asyncio.TimeoutError:
                        continue
                    if not data:
                        break
                    dst.write(data)
                    await dst.drain()
            except (ConnectionResetError, BrokenPipeError):
                pass
            except Exception as e:
                logger.debug(f"Relay {name} error: {e}")

        await asyncio.gather(
            forward(client_reader, remote_writer, "client->remote"),
            forward(remote_reader, client_writer, "remote->client"),
            return_exceptions=True,
        )
