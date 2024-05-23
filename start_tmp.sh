#!/usr/bin/env bash

test=$(netstat -tulpn | grep 9092 | cut -d "/" -f 1 | cut -d "N" -f 2 )
kill -9 $test;
cd /path/to/folder
source .venv/bin/activate;
python main.py &
sleep 3
sshpass -p SSH_PASSWORD ssh -C -o "ProxyCommand=nc -X CONNECT -x 127.0.0.1:9092 %h %p" USERNAME@IP -p STUN_PORT -v -CN -D 1080 -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null &
# Optional HTTP proxy
sleep 1
pproxy -l http://0.0.0.0:1090 -r socks5://127.0.0.1:1080 > /dev/null
