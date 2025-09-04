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
import tkinter.messagebox as messagebox
from pystray import Icon, Menu, MenuItem
from signal import signal, SIGTERM, SIGINT
from stdoutRedirector import StdoutRedirector
from tkinter.scrolledtext import ScrolledText
from utils import keep_ssh_alive, httpProxy, resource_path

filterwarnings("ignore", category=DeprecationWarning)

stop_event = Event()
isWindowShown = False
window = None
sshProc = None
httpProxyProc = None
tunnel = None
running = False
connection = None
mainThread = None

icon_path = resource_path("icon.png")
image = Image.open(icon_path)

def toggle(icon, item):
    global window, isWindowShown
    if isWindowShown:
        window.withdraw()
        isWindowShown = False
    else:
        window.deiconify()
        isWindowShown = True

def minimize_to_tray():
    global window, isWindowShown
    window.withdraw()
    isWindowShown = False

def stop():
    global sshProc, httpProxyProc, tunnel, stop_event, window, connection, mainThread
    stop_event.set()
    if mainThread and mainThread.is_alive():
        mainThread.join(timeout=5)
    if connection and connection.is_alive():
        connection.join(timeout=5)
    if sshProc and sshProc.is_alive():
        sshProc.join(timeout=5)
    if httpProxyProc:
        httpProxyProc.kill()
        httpProxyProc.wait()
    if tunnel:
        tunnel.stop()

def cleanup(icon=None):
    global sshProc, httpProxyProc, tunnel, stop_event, window, connection, mainThread
    stop_event.set()
    if window:
        sys.stdout = sys.__stdout__
        window.after(0, window.destroy)
    if mainThread and mainThread.is_alive():
        mainThread.join(timeout=5)
    if connection and connection.is_alive():
        connection.join(timeout=5)
    if sshProc and sshProc.is_alive():
        sshProc.join(timeout=5)
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
    global sshProc, httpProxyProc, tunnel, running, stop_event, connection
    try:
        running = True
        stop_event.clear()
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

def run():
    global running, mainThread
    if not running:
        print("[+] Starting Tunnel...")
        start_button.config(text="Stop")
        mainThread = Thread(target=start, daemon=True)
        mainThread.start()
    else:
        running = False
        start_button.config(text="Start")
        stop()

try:
    config = ConfigParser()
    config.read_file(open('settings.ini'))

    window = tk.Tk()
    window.title("TCP Over SSL Tunnel")
    window.geometry("550x500")
    window.protocol("WM_DELETE_WINDOW", minimize_to_tray)

    ico = tk.PhotoImage(file=icon_path)
    window.iconphoto(False, ico)

    text_area = ScrolledText(window, state="disabled", wrap=tk.WORD)
    text_area.pack(expand=True, fill=tk.BOTH)
    sys.stdout = StdoutRedirector(text_area)

    start_button = tk.Button(window, text="Start", command=run)
    start_button.pack(pady=5, padx=5)

    label = tk.Label(window, text="TCP Over SSL Tunnel", font=("Arial", 12))
    label.pack(expand=True)
    
    icon = Icon("name", image, "TCP OVER SSL TUNNEL",
        menu=Menu(
            MenuItem("Show/Hide", toggle, default=True),
            MenuItem("Quit", lambda icon, item: cleanup(icon))
        ))
    Thread(target=icon.run, daemon=True).start()

    if not running and config['settings']['auto_start'] == "true":
        run()

    signal(SIGINT, cleanup)
    signal(SIGTERM, cleanup)

    window.withdraw()
    window.mainloop() 

except Exception as e:
    messagebox.showerror("Error", e)
    cleanup()

