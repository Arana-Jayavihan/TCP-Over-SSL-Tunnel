import ssl
import socket
import signal
from time import sleep
from os import path, setsid, killpg, getpgid
from json import load
from select import select
from certifi import where
from subprocess import Popen
from threading import Thread
from argparse import ArgumentParser
import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning) 

def tunnel(conn, addr):
    decoded = conn.recv(9124).decode("utf-8")
    host = decoded.splitlines(False)[0].split(":")[0].split()[1]
    port = int(decoded.splitlines(False)[0].split(":")[1].split()[0])
    print(f"[+] Connecting to - {host}:{str(port)}")

    ssl_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    ssl_sock.connect((host, int(port)))
    
    context = ssl.SSLContext(ssl.PROTOCOL_TLSv1_2)
    ssl_sock = context.wrap_socket(ssl_sock, server_hostname=str(config['SNI']))
    context.verify_mode = ssl.CERT_REQUIRED
    context.load_verify_locations(cafile=path.relpath(where()), capath=None, cadata=None)

    try:
        print(f"[+] SNI injectection success - {config['SNI']}")
        print(f"[+] Ciphers - {ssl_sock.cipher()[0]}")
    except Exception as error:
        print("[+] Error -", error)
        pass

    conn.send(b"HTTP/1.1 200 Connection Established\r\n\r\n")

    connected = True
    print("[+] Tunnel Connected")

    print("\n#########################################################")
    print("#\t\t\t\t\t\t\t#")
    print(f"#\tSOCKS5 Proxy\t-\t127.0.0.1:{config['PROXY_PORT']}\t\t#")
    
    if args.port:
        print(f"#\tHTTP Proxy\t-\t0.0.0.0:{args.port}\t\t#")

    print("#\t\t\t\t\t\t\t#")
    print("#########################################################\n")

    while connected == True:
        r, w, x = select([conn, ssl_sock], [], [conn, ssl_sock], 3)
        if x: 
            connected = False
            break
        for i in r:
            try:
                data = i.recv(16384)
                if not data: 
                    connected = False
                    break
                if i is ssl_sock:
                    conn.send(data)
                else:
                    ssl_sock.send(data)
            except KeyboardInterrupt:
                connected = False
                break
            
    conn.close()
    ssl_sock.close()
    global listen_socket
    listen_socket.close()
    
    print("[+] Tunnel Disconnected")
    print("[+] Reconnecting in 60 seconds...\n")
    sleep(60)
    start()

def connect():
    try:
        global listen_socket
        listen_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listen_socket.bind((config['LISTEN_ADDR'], int(config['LISTEN_PORT'])))
        listen_socket.listen(0)
        
        print(f"[+] Awaiting connections - {config['LISTEN_ADDR']}:{str(config['LISTEN_PORT'])}")
        while True:
            try:
                conn, addr = listen_socket.accept()
                Thread(target=tunnel, args=(conn, addr)).start()

            except Exception as error:
                print("[+] Error -", error)
                break

    except Exception as error:
        print("[+] Error - ", error)
        listen_socket.close()

def start():
    try:
        command = f"sshpass -p {config['SSH_PASS']} ssh -o 'ProxyCommand=nc -X CONNECT -x {config['LISTEN_ADDR']}:{config['LISTEN_PORT']} %h %p' -p {config['SSH_SERVER_PORT']} {config['SSH_USER']}@{config['SSH_SERVER']} -C -N -D {config['PROXY_PORT']}"
        command2 = f"pproxy -l http://0.0.0.0:{str(args.port)} -r socks5://127.0.0.1:{config['PROXY_PORT']} > /dev/null"
        Thread(target=connect).start()
        sleep(5)
        ssh = Popen(command, shell=True)
        if args.port:
            httpProxy = Popen(command2, shell=True, preexec_fn=setsid)
    
    except KeyboardInterrupt:
        print("\n[+] Exiting...")
        killpg(getpgid(httpProxy.pid), signal.SIGTERM)
        exit(0)
    
    except Exception as error:
        print("[+] Error:", error)
        killpg(getpgid(httpProxy.pid), signal.SIGTERM)
        exit(1)

listen_socket = ""
parser = ArgumentParser()
parser.add_argument('-c', '--config', type=str, required=True, help="Config File")
parser.add_argument('-p', '--port', type=str, help="HTTP Proxy Port")
args = parser.parse_args()
config = load(open(args.config, "r"))

start()

#socat TCP-LISTEN:9000,fork,bind=0.0.0.0 TCP:localhost:1080
