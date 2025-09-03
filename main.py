import sys
from os import path
import tkinter as tk
from PIL import Image
from time import sleep
from tunnel import Tunnel
from threading import Thread, Event
from warnings import filterwarnings
from threading import Event, Thread
from configparser import ConfigParser
from pystray import Icon, Menu, MenuItem
from signal import signal, SIGTERM, SIGINT
from utils import keep_ssh_alive, httpProxy
from stdoutRedirector import StdoutRedirector
from tkinter.scrolledtext import ScrolledText

filterwarnings("ignore", category=DeprecationWarning)

config = ConfigParser()
config.read_file(open('settings.ini'))

stop_event = Event()
isWindowShown = False
root = None
sshProc = None
httpProxyProc = None
tunnel = None
running = False

icon_path = path.join(path.dirname(__file__), "icon.png")
image = Image.open(icon_path)

def toggle(icon, item):
    global root, isWindowShown
    if isWindowShown:
        root.withdraw()
        isWindowShown = False
    else:
        root.deiconify()
        isWindowShown = True

def minimize_to_tray():
    global root, isWindowShown
    root.withdraw()
    isWindowShown = False

def cleanup(icon=None):
    global sshProc, httpProxyProc, tunnel, stop_event, root
    stop_event.set()
    if root:
        sys.stdout = sys.__stdout__
        root.after(0, root.destroy)
    if httpProxyProc:
        httpProxyProc.kill()
        httpProxyProc.wait()
    if tunnel:
        tunnel.stop()
    if icon:
        icon.stop()
    print("[+] Cleanup complete. Exiting.")
    sys.exit(0)

def start():
    global sshProc, httpProxyProc, tunnel, running
    while not stop_event.is_set():
        try:
            running = True
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

def init():
    global running
    if not running:
        running = True
        start_button.config(text="Stop")
        Thread(target=start, daemon=True).start()
    else:
        cleanup()

# --- Tkinter GUI ---
while not stop_event.is_set():
    root = tk.Tk()
    root.title("TCP Over SSL Tunnel")
    root.geometry("550x500")
    root.protocol("WM_DELETE_WINDOW", minimize_to_tray)

    ico = tk.PhotoImage(file="icon.png")
    root.iconphoto(False, ico)

    text_area = ScrolledText(root, state="disabled", wrap=tk.WORD)
    text_area.pack(expand=True, fill=tk.BOTH)
    sys.stdout = StdoutRedirector(text_area)

    start_button = tk.Button(root, text="Start", command=init)
    start_button.pack(pady=10)

    label = tk.Label(root, text="TCP Over SSL Tunnel", font=("Arial", 12))
    label.pack(expand=True)
    
    icon = Icon("name", image, "TCP OVER SSL TUNNEL",
        menu=Menu(
            MenuItem("Show/Hide", toggle, default=True),
            MenuItem("Quit", lambda icon, item: cleanup(icon))
        ))
    Thread(target=icon.run, daemon=True).start()

    if not running:
        init()

    signal(SIGINT, cleanup)
    signal(SIGTERM, cleanup)

    root.withdraw()
    root.mainloop()