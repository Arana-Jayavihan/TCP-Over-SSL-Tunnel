import socket
import warnings
from os import path
from sys import exit
from time import sleep
from select import select
from certifi import where
from threading import Event, Thread
from configparser import ConfigParser
from subprocess import Popen, DEVNULL
from signal import signal, SIGTERM, SIGINT
from ssl import SSLContext, PROTOCOL_TLS, CERT_REQUIRED

warnings.filterwarnings("ignore", category=DeprecationWarning)

config = ConfigParser()
config.read_file(open('settings.ini'))


class Tunnel():
    def __init__(self):
        self.local_ip = config['settings']['local_ip']
        self.listen_port = int(config['settings']['listen_port'])
        self.stop_event = Event()
        self.threads = []
        self.listen_socket = None

    def tunneling(self, client, stunnel_socket):
        connected = True
        print("[*] Connection Established.")
        while connected and not self.stop_event.is_set():
            r, w, x = select([client, stunnel_socket], [], [
                client, stunnel_socket], 3)
            if x:
                connected = False
                break
            for i in r:
                try:
                    data = i.recv(16384)
                    if not data:
                        connected = False
                        break
                    if i is stunnel_socket:
                        client.send(data)
                    else:
                        stunnel_socket.send(data)
                except Exception:
                    connected = False
                    break
        client.close()
        stunnel_socket.close()
        print("[*] Client disconnected!")

    def destination(self, client, address):
        if self.stop_event.is_set():
            client.close()
            return
        print("[*] New Client connected!")
        try:
            request = client.recv(16384).decode()
            host = config['ssh']['host']
            port = request.split(':')[-1].split()[0]
            stunnel_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            stunnel_socket.connect((host, int(port)))
            print(f'[*] Connected to {host}:{port}')
            SNI_HOST = config['sni']['server_name']
            context = SSLContext(PROTOCOL_TLS)
            stunnel_socket = context.wrap_socket(
                stunnel_socket, server_hostname=str(SNI_HOST))
            context.verify_mode = CERT_REQUIRED
            context.load_verify_locations(cafile=path.relpath(
                where()), capath=None, cadata=None)
            print(f'[*] Handshaked successfully to {SNI_HOST}')
            try:
                print(f"[*] Ciphersuite : {stunnel_socket.cipher()[0]}")
            except:
                pass
            client.send(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            self.tunneling(client, stunnel_socket)
        except Exception as e:
            print(f"[Error] {e}")
            client.close()

    def create_connection(self):
        for res in socket.getaddrinfo(self.local_ip, self.listen_port, socket.AF_UNSPEC, socket.SOCK_STREAM, 0, socket.AI_PASSIVE):
            af, socktype, proto, canonname, sa = res
            try:
                self.listen_socket = socket.socket(af, socktype, proto)
                self.listen_socket.setsockopt(
                    socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            except OSError as e:
                print(f"[Error] {e}")
                exit(1)
            try:
                self.listen_socket.bind((self.local_ip, self.listen_port))
                self.listen_socket.listen(5)
            except OSError as e:
                print(f"[Error] {e}")
                self.listen_socket.close()
                exit(1)

            print(
                f'[*] Waiting for incoming connection to : {self.local_ip}:{self.listen_port}')
            while not self.stop_event.is_set():
                try:
                    self.listen_socket.settimeout(1.0)
                    client, address = self.listen_socket.accept()
                    t = Thread(
                        target=self.destination, args=(client, address))
                    t.start()
                    self.threads.append(t)
                except socket.timeout:
                    continue
                except Exception as e:
                    if not self.stop_event.is_set():
                        print(f"[Error] {e}")
            break

    def stop(self):
        print("[*] Stopping tunnel...")
        self.stop_event.set()
        if self.listen_socket:
            self.listen_socket.close()
        for t in self.threads:
            t.join()
        print("[*] Tunnel stopped.")


def initSSH():
    print("[+] Initialize SSH Port Forwarding")
    proxyCmd = "ProxyCommand=nc -X CONNECT -x " + \
        config["settings"]["local_ip"] + ":" + \
        config["settings"]["listen_port"] + " %h %p"

    cmd = [
        "sshpass",
        "-p",
        config["account"]["password"],
        "ssh",
        "-C",
        "-o",
        proxyCmd,
        config["account"]["username"] + "@" + config["ssh"]["host"],
        "-p",
        config["ssh"]["stun_port"],
        "-CND",
        config["settings"]["socks_port"],
        "-o",
        "StrictHostKeyChecking=no",
        "-o",
        "UserKnownHostsFile=/dev/null"
    ]
    proc = Popen(
        cmd, stdout=DEVNULL)
    return proc


def httpProxy():
    print("[+] Extending to HTTP Proxy")
    address = "127.0.0.1"
    if (config["http_proxy"]["expose"] == "true"):
        address = "0.0.0.0"
    cmd = [
        "pproxy",
        "-l",
        "http://" + address + ":" + config["http_proxy"]["http_port"],
        "-r",
        "socks5://" + config["settings"]["local_ip"] +
        ":" + config["settings"]["socks_port"]
    ]
    proc = Popen(
        cmd, stdout=DEVNULL, stderr=DEVNULL)
    return proc


if __name__ == '__main__':
    sshProc = None
    httpProxyProc = None
    tunnel = None
    running = True

    def cleanup(*args):
        print("\n[*] Exiting, cleaning up...")
        running = False
        if tunnel:
            tunnel.stop()
        if sshProc:
            sshProc.kill()
            sshProc.wait()
        if httpProxyProc:
            httpProxyProc.kill()
            httpProxyProc.wait()
        exit(0)

    signal(SIGINT, cleanup)
    signal(SIGTERM, cleanup)

    while running:
        try:
            sshProc = initSSH()
            if (config["http_proxy"]["enable"] == "true"):
                httpProxyProc = httpProxy()
            tunnel = Tunnel()

            connection = Thread(
                target=tunnel.create_connection, daemon=True)
            connection.start()

            while running:
                ret = sshProc.poll()
                if ret is not None:
                    print(f"[!] SSH process died with exit code {
                          ret}. Restarting...")
                    tunnel.stop()
                    if httpProxyProc:
                        httpProxyProc.kill()
                        httpProxyProc.wait()
                        httpProxyProc = None
                    sshProc.kill()
                    sshProc.wait()
                    sshProc = None
                    break
                sleep(2)

        except KeyboardInterrupt:
            cleanup()

        print("[*] Restarting in 5 seconds...")
        sleep(5)
