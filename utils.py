import sys
import socket
import struct
from time import sleep
from select import select
from os import path, name
from threading import Thread, Event
from paramiko import SSHClient, AutoAddPolicy
from subprocess import Popen, DEVNULL

if name == 'nt':
    from subprocess import STARTUPINFO, STARTF_USESHOWWINDOW
    si = STARTUPINFO()
    si.dwFlags |= STARTF_USESHOWWINDOW

def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = path.abspath(".")
    return path.join(base_path, relative_path)

def httpProxy(config):
    print("[+] Extending to HTTP Proxy")
    address = config['settings']['local_ip']
    if config["http_proxy"]["expose"] == "true":
        address = "0.0.0.0"
    cmd = [
        "pproxy",
        "-l",
        f"http://{address}:{config['http_proxy']['http_port']}",
        "-r",
        f"socks5://{config['settings']['local_ip']}:{config['settings']['socks_port']}"
    ]
    if name == 'nt':
        proc = Popen(cmd, startupinfo=si, stdout=DEVNULL, stderr=DEVNULL)
    else:
        proc = Popen(cmd, stdout=DEVNULL, stderr=DEVNULL)
    return proc

def tune_socket(sock, bufsize=4 << 20):
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, bufsize)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, bufsize)
    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    return sock


def relay(sock1, sock2, stop_event, bufsize=65536):
    tune_socket(sock1)
    sockets = [sock1, sock2]
    try:
        while not stop_event.is_set():
            r, _, _ = select(sockets, [], [], 1)
            for s in r:
                data = s.recv(bufsize)
                if not data:
                    return
                if s is sock1:
                    sock2.sendall(data)
                else:
                    sock1.sendall(data)
    finally:
        sock1.close()
        sock2.close()


def handle_socks(client, transport, stop_event, bufsize=65536):
    try:
        tune_socket(client)

        data = client.recv(2)
        if len(data) < 2:
            client.close()
            return
        ver, nmethods = struct.unpack("!BB", data)
        client.recv(nmethods)
        client.sendall(b"\x05\x00")

        data = client.recv(4)
        ver, cmd, _, atyp = struct.unpack("!BBBB", data)
        if atyp == 1:
            addr = socket.inet_ntoa(client.recv(4))
        elif atyp == 3:
            length = client.recv(1)[0]
            addr = client.recv(length).decode()
        elif atyp == 4:
            addr = socket.inet_ntop(socket.AF_INET6, client.recv(16))
        else:
            client.close()
            return

        port = struct.unpack("!H", client.recv(2))[0]
        reply = b"\x05\x00\x00\x01" + socket.inet_aton("0.0.0.0") + struct.pack("!H", 0)
        client.sendall(reply)

        chan = transport.open_channel("direct-tcpip", (addr, port), client.getpeername())
        if chan is None:
            client.close()
            return

        relay(client, chan, stop_event, bufsize)

    except Exception as e:
        try:
            client.close()
        except:
            pass


def start_socks_server(local_ip, local_port, transport, stop_event, bufsize=65536):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((local_ip, int(local_port)))
    sock.listen(100)
    print(f"[+] SOCKS5 Proxy listening on {local_ip}:{local_port}")
    try:
        while not stop_event.is_set():
            sock.settimeout(1)
            try:
                client, addr = sock.accept()
                Thread(
                    target=handle_socks,
                    args=(client, transport, stop_event, bufsize),
                    daemon=True
                ).start()
            except socket.timeout:
                continue
    finally:
        sock.close()


def http_proxy_connect(proxy_host, proxy_port, target_host, target_port, bufsize=65536):
    sock = tune_socket(socket.create_connection((proxy_host, proxy_port)))
    connect_req = (
        f"CONNECT {target_host}:{target_port} HTTP/1.1\r\n"
        f"Host: {target_host}:{target_port}\r\n"
        f"\r\n"
    )
    sock.sendall(connect_req.encode())

    response = b""
    while b"\r\n\r\n" not in response:
        chunk = sock.recv(bufsize)
        if not chunk:
            raise Exception("Proxy closed connection")
        response += chunk

    status_line = response.split(b"\r\n", 1)[0]
    if not status_line.startswith(b"HTTP/1.1 200") and not status_line.startswith(b"HTTP/1.0 200"):
        raise Exception(f"Proxy CONNECT failed: {response.decode(errors='ignore')}")

    print(f"[+] Connected to {target_host}:{target_port} via HTTP proxy {proxy_host}:{proxy_port}")
    return sock


def initSSH(config):
    client = SSHClient()
    client.set_missing_host_key_policy(AutoAddPolicy())

    proxy_sock = http_proxy_connect(
        config['settings']['local_ip'],
        config['settings']['listen_port'],
        config['ssh']['host'],
        config['ssh']['stun_port']
    )

    client.connect(
        hostname=config['ssh']['host'],
        port=config['ssh']['stun_port'],
        username=config['account']['username'],
        password=config['account']['password'],
        sock=proxy_sock,
        compress=True,
    )

    transport = client.get_transport()
    if not (transport and transport.is_active()):
        client.close()
        raise Exception("SSH transport failed to start")

    return client, transport


def keep_ssh_alive(config, stop_event):
    ssh_client = None
    socks_stop = None
    socks_thread = None

    while not stop_event.is_set():
        try:
            if ssh_client is None:
                ssh_client, transport = initSSH(config)

                socks_stop = Event()
                socks_thread = Thread(
                    target=start_socks_server,
                    args=(config['settings']['local_ip'], config['settings']['socks_port'], transport, socks_stop),
                    daemon=True
                )
                socks_thread.start()

            transport = ssh_client.get_transport()
            if transport is None or not transport.is_active():
                print("[+] SSH connection dropped, restarting...")
                if socks_stop:
                    socks_stop.set()
                if ssh_client:
                    ssh_client.close()
                ssh_client = None
                sleep(2)
                continue

            sleep(5)

        except Exception as e:
            print(f"[+] SSH error: {e}, retrying in 5 seconds...")
            if socks_stop:
                socks_stop.set()
            if ssh_client:
                try:
                    ssh_client.close()
                except:
                    pass
            ssh_client = None
            sleep(5)

    if socks_stop:
        socks_stop.set()
    if ssh_client:
        ssh_client.close()
