# TCP Over SSL Tunnel

TLS wrapper for TCP packets with SNI injection, tunneled through an SSH proxy. Provides SOCKS5 and HTTP proxy interfaces for applications.

## Features

- **SNI Injection**: Wraps connections in TLS with custom Server Name Indication
- **SSH Tunneling**: Routes traffic through SSH for secure transport
- **Dual Proxy Support**: SOCKS5 (port 1080) and HTTP (port 1090) interfaces
- **Async Architecture**: Built on asyncio for high concurrency with low resource usage
- **Auto-Reconnect**: Maintains SSH connection with automatic recovery
- **Connection Limits**: Configurable max connections to prevent resource exhaustion
- **Systemd Ready**: Includes service file for production deployment

## Requirements

- Python 3.10+
- SSH server with tunneling enabled

## Installation

```bash
# Clone the repository
git clone https://github.com/Arana-Jayavihan/TCP-Over-SSL-Tunnel.git
cd TCP-Over-SSL-Tunnel

# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure settings
cp settings_template.ini settings.ini
# Edit settings.ini with your configuration
```

## Configuration

Edit `settings.ini`:

```ini
[settings]
local_ip = 127.0.0.1      # Bind address for proxies
listen_port = 9092         # TLS tunnel listener port
socks_port = 1080          # SOCKS5 proxy port
max_connections = 100      # Max concurrent connections

[http_proxy]
enable = true              # Enable HTTP proxy bridge
expose = false             # Expose on 0.0.0.0 (use with caution)
http_port = 1090           # HTTP proxy port

[ssh]
host = your.ssh.server     # SSH server hostname/IP
stun_port = 22             # SSH server port
# key_file = ~/.ssh/id_rsa # Optional: SSH private key

[sni]
server_name = example.com  # SNI hostname for TLS handshake

[account]
username = your_username
password = your_password   # Or use TCP_TUNNEL_PASSWORD env var

[logging]
level = INFO               # DEBUG, INFO, WARNING, ERROR
# file = /var/log/tcp-tunnel.log
```

### Environment Variables

| Variable | Description |
|----------|-------------|
| `TCP_TUNNEL_PASSWORD` | SSH password (recommended over config file) |
| `TCP_TUNNEL_SSH_KEY` | Path to SSH private key |

## Usage

### Basic Usage

```bash
# Activate virtual environment
source .venv/bin/activate

# Run with default config
python main.py

# Run with custom config
python main.py --config /path/to/settings.ini

# Verbose logging
python main.py --verbose

# Quiet mode (errors only)
python main.py --quiet
```

### CLI Options

```
usage: tcp-tunnel [-h] [-c CONFIG] [-v] [-q] [--version]

options:
  -h, --help            show help message
  -c, --config CONFIG   Path to configuration file (default: settings.ini)
  -v, --verbose         Enable debug logging
  -q, --quiet           Suppress non-error output
  --version             Show version
```

### Using the Proxies

```bash
# SOCKS5 proxy
curl -x socks5://127.0.0.1:1080 http://example.com

# HTTP proxy
curl -x http://127.0.0.1:1090 http://example.com

# Set system-wide (Linux)
export http_proxy=http://127.0.0.1:1090
export https_proxy=http://127.0.0.1:1090
```

## Systemd Service

Install as a system service:

```bash
# Copy files
sudo mkdir -p /opt/tcp-tunnel
sudo cp *.py /opt/tcp-tunnel/
sudo cp requirements.txt /opt/tcp-tunnel/

# Install dependencies
sudo pip install -r /opt/tcp-tunnel/requirements.txt

# Copy config
sudo mkdir -p /etc/tcp-tunnel
sudo cp settings.ini /etc/tcp-tunnel/

# Install service
sudo cp tcp-tunnel.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable tcp-tunnel
sudo systemctl start tcp-tunnel

# Check status
sudo systemctl status tcp-tunnel
journalctl -u tcp-tunnel -f
```

## Architecture

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Client    │────▶│   Tunnel    │────▶│ SSH Server  │────▶ Internet
│ Application │     │  (TLS+SNI)  │     │             │
└─────────────┘     └─────────────┘     └─────────────┘
       │                   │
       │            ┌──────┴──────┐
       │            │             │
       ▼            ▼             ▼
   SOCKS5:1080  HTTP:1090    TLS:9092
```

**Flow:**
1. Client connects to SOCKS5/HTTP proxy
2. Proxy forwards through SSH tunnel
3. SSH connection wrapped in TLS with SNI injection
4. Traffic appears as HTTPS to SNI hostname

## Performance Benchmarks

Tested with `hey` HTTP load generator through the proxy:

| Test | Requests | Concurrency | Throughput | Avg Latency | Success Rate |
|------|----------|-------------|------------|-------------|--------------|
| Light | 100 | 10 | 17.5 req/s | 453ms | 100% |
| Medium | 200 | 20 | 30.9 req/s | 484ms | 100% |
| Stress | 100 | 50 | 46.3 req/s | 684ms | 98% |
| Sustained | 500 | 25 | 41.2 req/s | 445ms | 99.6% |

**Latency Distribution (sustained load):**
- p50: 310ms
- p90: 755ms
- p99: 1.65s

*Note: Latency dominated by network round-trip through SSH tunnel, not proxy overhead.*

### Async Benefits

The asyncio architecture provides:
- **Low memory**: ~8KB per connection (vs ~1MB per thread)
- **High concurrency**: 50+ simultaneous connections
- **Efficient I/O**: Non-blocking operations
- **Graceful scaling**: Throughput increases with concurrency

## Project Structure

```
TCP-Over-SSL-Tunnel/
├── main.py              # Entry point, CLI, async event loop
├── tunnel.py            # TLS/SNI tunnel server
├── utils.py             # SSH, SOCKS5, HTTP proxy utilities
├── config.py            # Configuration loading and validation
├── logger.py            # Logging setup
├── exceptions.py        # Custom exception classes
├── settings.ini         # Runtime configuration
├── settings_template.ini
├── requirements.txt
├── tcp-tunnel.service   # Systemd unit file
└── README.md
```

## Troubleshooting

### Connection Refused
- Verify SSH server is reachable
- Check `host` and `stun_port` in config
- Ensure SSH credentials are correct

### TLS Handshake Failed
- SNI hostname may be blocked
- Try a different `server_name`

### SSH Authentication Failed
- Verify username/password
- Try SSH key authentication with `key_file`
- Check `TCP_TUNNEL_PASSWORD` env var

### High Latency
- Normal for tunneled connections
- Latency = local → tunnel → SSH server → destination
- Choose geographically closer SSH server

## License

MIT License

## Star History

<a href="https://www.star-history.com/#Arana-Jayavihan/TCP-Over-SSL-Tunnel&Date">
 <picture>
   <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/svg?repos=Arana-Jayavihan/TCP-Over-SSL-Tunnel&type=Date&theme=dark" />
   <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/svg?repos=Arana-Jayavihan/TCP-Over-SSL-Tunnel&type=Date" />
   <img alt="Star History Chart" src="https://api.star-history.com/svg?repos=Arana-Jayavihan/TCP-Over-SSL-Tunnel&type=Date" />
 </picture>
</a>
