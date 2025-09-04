import tkinter as tk
from queue import Queue

class StdoutRedirector:
    def __init__(self, text_widget):
        self.text_widget = text_widget
        self.queue = Queue()
        self.buffer = ""
        self._schedule_update()

    def write(self, message):
        self.buffer += message
        
        if "\r" in self.buffer:
            parts = self.buffer.split("\r")
            self.buffer = parts[-1]
            for part in parts[:-1]:
                if part:
                    self.queue.put(("replace", part))
        
        while "\n" in self.buffer:
            line, self.buffer = self.buffer.split("\n", 1)
            self.queue.put(("append", line + "\n"))
            
        if self.buffer and "\r" not in self.buffer and "\n" not in self.buffer:
            self.queue.put(("append", self.buffer))
            self.buffer = ""

    def flush(self):
        if self.buffer:
            self.queue.put(("append", self.buffer))
            self.buffer = ""

    def _schedule_update(self):
        self._process_queue()
        self.text_widget.after(50, self._schedule_update)

    def _process_queue(self):
        processed = 0
        while not self.queue.empty() and processed < 20:
            try:
                action, message = self.queue.get_nowait()
                if action == "append":
                    self._safe_append(message)
                elif action == "replace":
                    self._safe_replace(message)
                processed += 1
            except:
                break

    def _safe_append(self, message):
        try:
            self.text_widget.config(state="normal")
            self.text_widget.insert(tk.END, message)
            self.text_widget.see(tk.END)
            self.text_widget.config(state="disabled")
        except:
            pass

    def _safe_replace(self, message):
        try:
            self.text_widget.config(state="normal")
            self.text_widget.delete("1.0", tk.END)
            self.text_widget.insert(tk.END, message)
            self.text_widget.see(tk.END)
            self.text_widget.config(state="disabled")
        except:
            pass