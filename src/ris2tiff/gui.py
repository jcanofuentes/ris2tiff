"""Simple GUI for ris2tiff converter."""

import tkinter as tk
from tkinter import filedialog, scrolledtext
from pathlib import Path
import threading
import time

from ris2tiff.converter import convert_ris_to_tiff


class App:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("RIS2TIFF - Written by: J.Cano, Head of Technology at Factum Foundation ver.0.1.0")
        self.root.geometry("600x400")
        self.root.resizable(True, True)
        self.files: list[Path] = []
        self._build_ui()

    def _build_ui(self):
        # Top frame: file selection + width
        top = tk.Frame(self.root, padx=10, pady=10)
        top.pack(fill=tk.X)

        tk.Button(top, text="Select RIS files...", command=self._select_files).pack(
            side=tk.LEFT
        )

        self.file_label = tk.Label(top, text="No files selected")
        self.file_label.pack(side=tk.LEFT, padx=10)

        # Width setting
        right = tk.Frame(top)
        right.pack(side=tk.RIGHT)
        tk.Label(right, text="Rotate:").pack(side=tk.LEFT, padx=(0, 2))
        self.rotate_var = tk.StringVar(value="90")
        rotate_menu = tk.OptionMenu(right, self.rotate_var, "0", "90", "180", "270")
        rotate_menu.config(width=3)
        rotate_menu.pack(side=tk.LEFT, padx=(0, 10))
        tk.Label(right, text="Width:").pack(side=tk.LEFT)
        self.width_var = tk.StringVar(value="auto")
        tk.Entry(right, textvariable=self.width_var, width=6).pack(side=tk.LEFT)

        # Light settings row
        light = tk.Frame(self.root, padx=10)
        light.pack(fill=tk.X)
        tk.Label(light, text="Azimuth:").pack(side=tk.LEFT)
        self.azimuth_var = tk.StringVar(value="315")
        tk.Entry(light, textvariable=self.azimuth_var, width=5).pack(side=tk.LEFT, padx=(0, 10))
        tk.Label(light, text="Elevation:").pack(side=tk.LEFT)
        self.elevation_var = tk.StringVar(value="45")
        tk.Entry(light, textvariable=self.elevation_var, width=5).pack(side=tk.LEFT, padx=(0, 10))
        tk.Label(light, text="Z exagg:").pack(side=tk.LEFT)
        self.exaggeration_var = tk.StringVar(value="1.0")
        tk.Entry(light, textvariable=self.exaggeration_var, width=5).pack(side=tk.LEFT)

        # Convert button
        mid = tk.Frame(self.root, padx=10)
        mid.pack(fill=tk.X)
        self.convert_btn = tk.Button(
            mid, text="Convert", command=self._convert, state=tk.DISABLED
        )
        self.convert_btn.pack(fill=tk.X)

        # Log area
        self.log = scrolledtext.ScrolledText(
            self.root, height=15, state=tk.DISABLED, font=("Consolas", 9)
        )
        self.log.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

    def _select_files(self):
        paths = filedialog.askopenfilenames(
            title="Select RIS files",
            filetypes=[("RIS files", "*.ris *.RIS"), ("All files", "*.*")],
        )
        if paths:
            self.files = [Path(p) for p in paths]
            n = len(self.files)
            # Update label and button first, force paint so user sees it immediately
            self.file_label.config(text=f"{n} file{'s' if n > 1 else ''} selected")
            self.convert_btn.config(state=tk.NORMAL)
            self.root.update()  # flush all pending events so the new label/button are drawn now
            self._log(f"{n} file{'s' if n > 1 else ''} selected. Click Convert to start.")

    def _log(self, text: str):
        self.log.config(state=tk.NORMAL)
        self.log.insert(tk.END, text + "\n")
        self.log.see(tk.END)
        self.log.config(state=tk.DISABLED)

    def _convert(self):
        self.convert_btn.config(state=tk.DISABLED)
        threading.Thread(target=self._convert_thread, daemon=True).start()

    def _convert_thread(self):
        try:
            width_str = self.width_var.get().strip().lower()
            width = None if width_str == "auto" else int(width_str)
        except ValueError:
            self.root.after(0, self._log, "[ERROR] Invalid width value (use 'auto' or a number)")
            self.root.after(0, lambda: self.convert_btn.config(state=tk.NORMAL))
            return

        rotate = int(self.rotate_var.get())

        try:
            azimuth = float(self.azimuth_var.get())
            elevation = float(self.elevation_var.get())
            exaggeration = float(self.exaggeration_var.get())
        except ValueError:
            self.root.after(0, self._log, "[ERROR] Invalid azimuth/elevation/exaggeration value")
            self.root.after(0, lambda: self.convert_btn.config(state=tk.NORMAL))
            return

        self.root.after(0, self._log, "Starting conversion...")
        time.sleep(0.25)  # let the UI refresh so the user sees the message

        import io
        import contextlib

        for f in self.files:
            self.root.after(0, self._log, f"--- {f.name} ---")
            time.sleep(0.15)  # let the UI update before heavy work

            try:
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    convert_ris_to_tiff(f, width=width, rotate=rotate, azimuth=azimuth, elevation=elevation, exaggeration=exaggeration)
                output = buf.getvalue()
                for line in output.strip().splitlines():
                    self.root.after(0, self._log, line)
            except Exception as e:
                self.root.after(0, self._log, f"[ERROR] {e}")

        self.root.after(0, self._log, "--- Done ---")
        self.root.after(0, lambda: self.convert_btn.config(state=tk.NORMAL))

    def run(self):
        self.root.mainloop()


def main():
    App().run()


if __name__ == "__main__":
    main()
