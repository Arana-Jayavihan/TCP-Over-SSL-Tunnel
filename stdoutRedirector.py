import tkinter as tk
class StdoutRedirector:
    def __init__(self, text_widget):
        self.text_widget = text_widget
        self.buffer = ""

    def write(self, message):
        self.buffer += message

        while "\n" in self.buffer:
            line, self.buffer = self.buffer.split("\n", 1)
            self._append(line + "\n")

        if "\r" in self.buffer:
            line = self.buffer.split("\r")[-1]
            self.buffer = ""
            self._replace_last_line(line)

    def flush(self):
        if self.buffer:
            self._append(self.buffer)
            self.buffer = ""

    def _append(self, message):
        self.text_widget.config(state="normal")
        self.text_widget.insert(tk.END, message)
        self.text_widget.see(tk.END)
        self.text_widget.config(state="disabled")

    def _replace_last_line(self, message):
        self.text_widget.config(state="normal")
        self.text_widget.delete("end-2l", "end-1l")
        self.text_widget.insert(tk.END, message)
        self.text_widget.see(tk.END)
        self.text_widget.config(state="disabled")