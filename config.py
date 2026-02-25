"""Configuration management for TCP-Over-SSL-Tunnel."""

import argparse
import ipaddress
import os
import re
from configparser import ConfigParser
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from exceptions import ConfigurationError, ValidationError
from logger import get_logger

logger = get_logger()


@dataclass
class Settings:
    """General tunnel settings."""

    local_ip: str = "127.0.0.1"
    listen_port: int = 9092
    socks_port: int = 1080
    max_connections: int = 100


@dataclass
class HttpProxySettings:
    """HTTP proxy bridge settings."""

    enable: bool = True
    expose: bool = False
    http_port: int = 1090


@dataclass
class SSHSettings:
    """SSH connection settings."""

    host: str = ""
    port: int = 22
    username: str = ""
    password: Optional[str] = None
    key_file: Optional[Path] = None
    known_hosts: Optional[Path] = None
    host_key_fingerprint: Optional[str] = None


@dataclass
class SNISettings:
    """SNI/TLS settings."""

    server_name: str = ""


@dataclass
class LoggingSettings:
    """Logging configuration."""

    level: str = "INFO"
    file: Optional[Path] = None


@dataclass
class Config:
    """Main configuration container."""

    settings: Settings = field(default_factory=Settings)
    http_proxy: HttpProxySettings = field(default_factory=HttpProxySettings)
    ssh: SSHSettings = field(default_factory=SSHSettings)
    sni: SNISettings = field(default_factory=SNISettings)
    logging: LoggingSettings = field(default_factory=LoggingSettings)


def validate_ip(ip: str) -> str:
    """Validate IP address format."""
    try:
        if ip == "0.0.0.0":
            return ip
        ipaddress.ip_address(ip)
        return ip
    except ValueError as e:
        raise ValidationError(f"Invalid IP address: {ip}") from e


def validate_port(port: int, name: str = "port") -> int:
    """Validate port number range."""
    if not 1 <= port <= 65535:
        raise ValidationError(f"Invalid {name}: {port} (must be 1-65535)")
    return port


def validate_hostname(hostname: str) -> str:
    """Validate hostname format."""
    if not hostname:
        raise ValidationError("Hostname cannot be empty")
    pattern = re.compile(
        r"^(?=.{1,253}$)(?:(?!-)[A-Za-z0-9-]{1,63}(?<!-)\.)*(?!-)[A-Za-z0-9-]{1,63}(?<!-)$"
    )
    if not pattern.match(hostname) and not _is_valid_ip(hostname):
        raise ValidationError(f"Invalid hostname: {hostname}")
    return hostname


def _is_valid_ip(value: str) -> bool:
    """Check if string is a valid IP address."""
    try:
        ipaddress.ip_address(value)
        return True
    except ValueError:
        return False


def load_config(config_path: Path) -> Config:
    """
    Load and validate configuration from INI file.

    Args:
        config_path: Path to the configuration file

    Returns:
        Validated Config object

    Raises:
        ConfigurationError: If config file is missing or invalid
    """
    if not config_path.exists():
        raise ConfigurationError(f"Configuration file not found: {config_path}")

    parser = ConfigParser()
    try:
        parser.read_file(open(config_path))
    except Exception as e:
        raise ConfigurationError(f"Failed to parse config file: {e}") from e

    config = Config()

    if "settings" in parser:
        s = parser["settings"]
        config.settings.local_ip = validate_ip(s.get("local_ip", "127.0.0.1"))
        config.settings.listen_port = validate_port(
            int(s.get("listen_port", 9092)), "listen_port"
        )
        config.settings.socks_port = validate_port(
            int(s.get("socks_port", 1080)), "socks_port"
        )
        config.settings.max_connections = int(s.get("max_connections", 100))

    if "http_proxy" in parser:
        hp = parser["http_proxy"]
        config.http_proxy.enable = hp.get("enable", "true").lower() == "true"
        config.http_proxy.expose = hp.get("expose", "false").lower() == "true"
        config.http_proxy.http_port = validate_port(
            int(hp.get("http_port", 1090)), "http_port"
        )

    if "ssh" in parser:
        ssh = parser["ssh"]
        config.ssh.host = validate_hostname(ssh.get("host", ""))
        config.ssh.port = validate_port(int(ssh.get("stun_port", 22)), "ssh_port")
        key_file = ssh.get("key_file")
        if key_file:
            config.ssh.key_file = Path(key_file).expanduser()
        known_hosts = ssh.get("known_hosts")
        if known_hosts:
            config.ssh.known_hosts = Path(known_hosts).expanduser()
        config.ssh.host_key_fingerprint = ssh.get("host_key_fingerprint")

    if "account" in parser:
        acc = parser["account"]
        config.ssh.username = acc.get("username", "")
        env_password = os.environ.get("TCP_TUNNEL_PASSWORD")
        if env_password:
            config.ssh.password = env_password
        else:
            config.ssh.password = acc.get("password")
            if config.ssh.password:
                logger.warning(
                    "Password stored in config file. Consider using TCP_TUNNEL_PASSWORD env var."
                )

        env_key = os.environ.get("TCP_TUNNEL_SSH_KEY")
        if env_key:
            config.ssh.key_file = Path(env_key).expanduser()

    if "sni" in parser:
        sni = parser["sni"]
        config.sni.server_name = validate_hostname(sni.get("server_name", ""))

    if "logging" in parser:
        log = parser["logging"]
        config.logging.level = log.get("level", "INFO").upper()
        log_file = log.get("file")
        if log_file:
            config.logging.file = Path(log_file).expanduser()

    _validate_required_fields(config)

    return config


def _validate_required_fields(config: Config) -> None:
    """Validate that all required fields are present."""
    errors = []

    if not config.ssh.host:
        errors.append("ssh.host is required")
    if not config.ssh.username:
        errors.append("account.username is required")
    if not config.ssh.password and not config.ssh.key_file:
        errors.append("Either account.password or ssh.key_file is required")
    if not config.sni.server_name:
        errors.append("sni.server_name is required")

    if errors:
        raise ConfigurationError("Missing required configuration:\n  - " + "\n  - ".join(errors))


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        prog="tcp-tunnel",
        description="TCP Over SSL Tunnel with SNI injection",
    )
    parser.add_argument(
        "-c", "--config",
        type=Path,
        default=Path("settings.ini"),
        help="Path to configuration file (default: settings.ini)",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose (debug) logging",
    )
    parser.add_argument(
        "-q", "--quiet",
        action="store_true",
        help="Suppress non-error output",
    )
    parser.add_argument(
        "--version",
        action="version",
        version="%(prog)s 2.0.0",
    )
    return parser.parse_args()
