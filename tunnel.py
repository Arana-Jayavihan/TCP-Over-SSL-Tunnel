import ssl
import json
import certifi
import select
import socket
import subprocess
from os import path
from threading import Thread

config = json.load(open("config.json", "r"))

def tunnel(conn, addr):
    decoded = conn.recv(8192).decode("utf-8")
    host = decoded.splitlines(False)[0].split(":")[0].split()[1]
    port = int(decoded.splitlines(False)[0].split(":")[1].split()[0])
    print("[+] Connecting to " + host + ":" + str(port))

    ssl_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    ssl_sock.connect((host, int(port)))
    
    SNI_HOST = config['SNI']
    context = ssl.SSLContext(ssl.PROTOCOL_TLSv1_2)
    ssl_sock = context.wrap_socket(ssl_sock, server_hostname=str(config['SNI']))
    context.verify_mode = ssl.CERT_REQUIRED
    context.load_verify_locations(cafile=path.relpath(certifi.where()),capath=None, cadata=None)
    print('[+] SNI injectection success -', config["SNI"])

    try:
        print("[+] Ciphers :", ssl_sock.cipher()[0])
    except:
        pass

    conn.send(b"HTTP/1.1 200 Connection Established\r\n\r\n")

    connected = True
    print("[+] Tunnel Connected")
    while connected == True:
        r, w, x = select.select([conn, ssl_sock], [], [conn, ssl_sock], 3)
        if x: 
            connected = False
            break
        for i in r:
            try:
                data = i.recv(8192)
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
    print("[+] Tunnel Disconnected")

def connect():
    try:
        listen_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    except Exception as error:
        print("[+] Error: ", error)
        exit(0)
    try:
        listen_socket.bind((config['LISTEN_ADDR'], int(config['LISTEN_PORT'])))
        listen_socket.listen(0)

    except Exception as error:
        print("[+] Error: ", error)
        listen_socket.close()
        exit(0)
    
    print("[+] Awaiting connections to " + config['LISTEN_ADDR'] + ":" + str(config['LISTEN_PORT']))

    while True:
        try:
            conn, addr = listen_socket.accept()
            Thread(target=tunnel, args=(conn, addr)).start()
        except KeyboardInterrupt:
            print("\n[+] Exiting...")
            break
    
    exit(0)

def start():
    try:
        Thread(target=connect).start()
        command = f"ssh -o 'ProxyCommand=nc -X CONNECT -x {config['LISTEN_ADDR']}:{config['LISTEN_PORT']} %h %p' -p {config['SSH_SERVER_PORT']} {config['SSH_USER']}@{config['SSH_SERVER']} -C -N -D {config['PROXY_PORT']}"
        subprocess.Popen(command, shell=True)
    
    except Exception as error:
        print(error)
        exit(0)

start()

