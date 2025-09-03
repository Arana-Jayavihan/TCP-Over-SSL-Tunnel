from os import path
from sys import exit
from PIL import Image
from time import sleep
from tunnel import Tunnel
from warnings import filterwarnings
from threading import Event, Thread
from configparser import ConfigParser
from pystray import Icon, Menu, MenuItem
from signal import signal, SIGTERM, SIGINT
from utils import keep_ssh_alive, httpProxy

filterwarnings("ignore", category=DeprecationWarning)

config = ConfigParser()
config.read_file(open('settings.ini'))
stop_event = Event()

icon_path = path.join(path.dirname(__file__), "icon.png")
image = Image.open(icon_path)

def on_quit(icon, item):
    icon.stop()
    cleanup()

def setup_tray():
    icon = Icon("TCP OVER SSL TUNNEL", image, "TCP SSL Tunnel")
    icon.menu = Menu(
        MenuItem("Quit", on_quit)
    )
    icon.run()

Thread(target=setup_tray, daemon=True).start()

def cleanup(*args):
    print("[+] Exiting, cleaning up...")
    stop_event.set()
    if tunnel:
        tunnel.stop()
    if httpProxyProc:
        httpProxyProc.kill()
        httpProxyProc.wait()
    print("[+] Cleanup complete. Exiting.")
    exit(0)

if __name__ == '__main__':
    sshProc = None
    httpProxyProc = None
    tunnel = None

    signal(SIGINT, cleanup)
    signal(SIGTERM, cleanup)

    while not stop_event.is_set():
        try:
            sshProc = Thread(target=keep_ssh_alive, args=(config, stop_event), daemon=True)
            sshProc.start()

            tunnel = Tunnel(config=config, stopEvent=stop_event)
            connection = Thread(target=tunnel.create_connection, daemon=True)
            connection.start()

            if config["http_proxy"]["enable"] == "true":
                httpProxyProc = httpProxy(config)

            while not stop_event.is_set():
                sleep(2)

        except KeyboardInterrupt:
            cleanup()
