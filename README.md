# TCP-Over-SSL-Tunnel
TLS wrapper for TCP packets allowing SNI injection through SSH Proxy.

# Installation and Usage
1. Install netcat-openbsd.
2. run "pip install -r requirements.txt" to install required libraries.
3. Add your config to "config.json".
4. run "python3 tunnel.py -c config.json -p 8090".
5. Add SOCKS5 or HTTP proxy to browser or os.
