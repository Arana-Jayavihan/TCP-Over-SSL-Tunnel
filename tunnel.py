import socket
from os import path
from select import select
from certifi import where
from threading import Event, Thread
from configparser import ConfigParser
from ssl import SSLContext, PROTOCOL_TLS, CERT_REQUIRED

class Tunnel:
    def __init__(self, config, stopEvent):
        self.threads = []
        self.listen_socket = None
        self.stop_event = stopEvent
        self.host = config['ssh']['host']
        self.SNI = config['sni']['server_name']
        self.local_ip = config['settings']['local_ip']
        self.listen_port = int(config['settings']['listen_port'])

    def tunneling(self, client, stunnel_socket):
        connected = True
        print("[+] Connection Established.")
        while connected and not self.stop_event.is_set():
            r, w, x = select([client, stunnel_socket], [], [client, stunnel_socket], 3)
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
        print("[+] Client disconnected!")
        self.restart_event.set()

    def destination(self, client, address):
        if self.stop_event.is_set():
            client.close()
            return
        print("[+] New Client connected!")
        try:
            request = client.recv(16384).decode()
            host = self.host
            port = request.split(':')[-1].split()[0]
            stunnel_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            stunnel_socket.connect((host, int(port)))
            SNI_HOST = self.SNI
            context = SSLContext(PROTOCOL_TLS)
            stunnel_socket = context.wrap_socket(stunnel_socket, server_hostname=str(SNI_HOST))
            context.verify_mode = CERT_REQUIRED
            context.load_verify_locations(cafile=path.relpath(where()))
            print(f'[+] Handshaked successfully with {SNI_HOST}')
            try:
                print(f"[+] Ciphersuite : {stunnel_socket.cipher()[0]}")
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
                self.listen_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
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

            print(f'[+] Waiting for incoming connection to : {self.local_ip}:{self.listen_port}')
            while not self.stop_event.is_set():
                try:
                    self.listen_socket.settimeout(1.0)
                    client, address = self.listen_socket.accept()
                    t = Thread(target=self.destination, args=(client, address), daemon=True)
                    t.start()
                    self.threads.append(t)
                except socket.timeout:
                    continue
                except Exception as e:
                    if not self.stop_event.is_set():
                        print(f"[Error] {e}")
            break

    def stop(self):
        print("[+] Stopping tunnel...")
        self.stop_event.set()
        if self.listen_socket:
            self.listen_socket.close()
        for t in self.threads:
            t.join()
        print("[+] Tunnel stopped.")