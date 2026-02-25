# TCP Over SSL Tunnel

A TLS wrapper for TCP traffic with SNI injection, tunneled through SSH. Provides SOCKS5 and HTTP proxy interfaces.

## How It Works

```
Application -> SOCKS5/HTTP Proxy -> SSH Tunnel -> TLS+SNI -> Internet
                 (localhost)         (encrypted)   (spoofed)
```

1. Applications connect to local SOCKS5 (port 1080) or HTTP proxy (port 1090)
2. Traffic is forwarded through an SSH tunnel to your server
3. The SSH connection is wrapped in TLS with a custom SNI hostname
4. To network observers, traffic appears as HTTPS to the SNI domain

## Requirements

- Python 3.8+
- SSH server with TCP forwarding enabled

## Quick Start

```bash
git clone https://github.com/Arana-Jayavihan/TCP-Over-SSL-Tunnel.git
cd TCP-Over-SSL-Tunnel

python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp settings_template.ini settings.ini
# Edit settings.ini with your configuration

python main.py
```

## Configuration

```ini
[settings]
local_ip = 127.0.0.1
listen_port = 9092
socks_port = 1080

[http_proxy]
enable = true
expose = false
http_port = 1090

[ssh]
host = your.server.com
stun_port = 22
key_file = /path/to/private_key.pem

[sni]
server_name = example.com

[account]
username = your_username
password = your_password
```

### Authentication

**SSH Key (recommended):**
```ini
[ssh]
key_file = ~/.ssh/id_rsa
```
Or: `export TCP_TUNNEL_SSH_KEY=~/.ssh/id_rsa`

**Password:**
```ini
[account]
password = your_password
```
Or: `export TCP_TUNNEL_PASSWORD=your_password`

## Usage

```bash
# Run with default config
python main.py

# Run with custom config
python main.py -c /path/to/config.ini

# Use the proxies
curl -x socks5://127.0.0.1:1080 http://example.com
curl -x http://127.0.0.1:1090 http://example.com
```

## License

MIT

## Star History

<a href="https://www.star-history.com/#Arana-Jayavihan/TCP-Over-SSL-Tunnel&Date">
 <picture>
   <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/svg?repos=Arana-Jayavihan/TCP-Over-SSL-Tunnel&type=Date&theme=dark" />
   <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/svg?repos=Arana-Jayavihan/TCP-Over-SSL-Tunnel&type=Date" />
   <img alt="Star History Chart" src="https://api.star-history.com/svg?repos=Arana-Jayavihan/TCP-Over-SSL-Tunnel&type=Date" />
 </picture>
</a>
