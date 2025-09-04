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
startThread = None

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

def cleanup(icon=None):
    global sshProc, httpProxyProc, tunnel, stop_event, window
    stop_event.set()
    if window:
        sys.stdout = sys.__stdout__
        window.after(0, window.destroy)
    if httpProxyProc:
        httpProxyProc.kill()
        httpProxyProc.wait()
    if tunnel:
        tunnel.stop()
    if icon:
        icon.stop()
    print("[+] Cleanup complete. Exiting.")
    sys.exit(0)

def restart():
    global startThread, httpProxyProc, tunnel, stop_event, running
    stop_event.set()
    if httpProxyProc:
        httpProxyProc.kill()
        httpProxyProc.wait()
        httpProxyProc = None
    if tunnel:
        tunnel.stop()
        tunnel = None   
    running = False

def start():
    global sshProc, httpProxyProc, tunnel, running
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

    finally:
        print("[*] Start thread exiting")
        running = False

def run():
    global running, startThread
    if not running:
        start_button.config(text="Stop")
        startThread = Thread(target=start, daemon=True)
        startThread.start()
    else:
        restart()
        start_button.config(text="Start")
        startThread = Thread(target=start, daemon=True)
        startThread.start()
        #cleanup()

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

    if not running:
        run()

    signal(SIGINT, cleanup)
    signal(SIGTERM, cleanup)

    window.withdraw()
    window.mainloop() 

except Exception as e:
    messagebox.showerror("Error", e)
    cleanup()

