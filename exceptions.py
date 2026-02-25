"""Custom exceptions for TCP-Over-SSL-Tunnel."""

from typing import Optional


class TunnelError(Exception):
    """Base exception for all tunnel-related errors."""

    def __init__(self, message: str, cause: Optional[Exception] = None) -> None:
        super().__init__(message)
        self.cause = cause


class ConfigurationError(TunnelError):
    """Raised when configuration is invalid or missing."""

    pass


class SSHConnectionError(TunnelError):
    """Raised when SSH connection fails."""

    pass


class SSHHostKeyError(SSHConnectionError):
    """Raised when SSH host key verification fails."""

    pass


class ProxyConnectionError(TunnelError):
    """Raised when proxy connection fails."""

    pass


class TLSHandshakeError(TunnelError):
    """Raised when TLS/SSL handshake fails."""

    pass


class ConnectionLimitError(TunnelError):
    """Raised when maximum connection limit is reached."""

    pass


class ValidationError(ConfigurationError):
    """Raised when input validation fails."""

    pass
