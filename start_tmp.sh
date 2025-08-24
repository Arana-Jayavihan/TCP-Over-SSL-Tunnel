#!/usr/bin/env bash

SSH_PASSWORD=
USERNAME=
STUN_PORT=
HOST=
HTTP=true

pid=$(netstat -tulpn | grep 9092 | cut -d "/" -f 1 | cut -d "N" -f 2 )
kill -9 $pid;
cd /path/to/folder
source .venv/bin/activate;
python tunnel.py &
sleep 3
sshpass -p $SSH_PASSWORD ssh -C -o "ProxyCommand=nc -X CONNECT -x 127.0.0.1:9092 %h %p" $USERNAME@$HOST -p $STUN_PORT -CN -D 1080 -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null &
# Optional HTTP proxy
if [ "$HTTP" == "true" ]; then
  sleep 1
  echo "[+] HTTP Proxy Running on 127.0.0.1:1090"
  pproxy -l http://0.0.0.0:1090 -r socks5://127.0.0.1:1080 > /dev/null
f1
