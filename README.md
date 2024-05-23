# TCP OVER SSL TUNNEL
TLS wrapper for TCP packets allowing SNI injection through SSH Proxy.

# Installation and Usage
1. Clone the repository.
2. Create a python virtual environment in the repo directory.
3. Install dependencies using pip install -r requirements.txt.
4. Add your config to settings_tmp.ini and rename the file settings.ini.
5. Change values in start_tmp.sh accordingly and rename it as start.sh.
6. Give execute permissions to start.sh and run it.
7. Add SOCKS5 or HTTP proxy to browser or os.