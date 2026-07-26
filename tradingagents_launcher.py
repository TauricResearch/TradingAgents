import os
import subprocess
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox


def app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent / "dist-nxp"


def default_results_dir() -> Path:
    return app_dir().parent / "run_logs"


class Launcher(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("TradingAgents Launcher")
        self.geometry("720x360")
        self.resizable(False, False)

        self.exe_path = app_dir() / "tradingagents.exe"
        self.api_key = tk.StringVar(value=os.environ.get("OPENAI_API_KEY", ""))
        self.results_dir = tk.StringVar(
            value=os.environ.get("TRADINGAGENTS_RESULTS_DIR", str(default_results_dir()))
        )

        self._build_ui()

    def _build_ui(self):
        outer = tk.Frame(self, padx=22, pady=18)
        outer.pack(fill=tk.BOTH, expand=True)

        title = tk.Label(
            outer,
            text="TradingAgents",
            font=("Segoe UI", 18, "bold"),
            anchor="w",
        )
        title.pack(fill=tk.X)

        subtitle = tk.Label(
            outer,
            text="Double-click launcher for the interactive CLI. Results are written to the folder below.",
            font=("Segoe UI", 10),
            anchor="w",
        )
        subtitle.pack(fill=tk.X, pady=(2, 18))

        exe_status = "Found" if self.exe_path.exists() else "Missing"
        self.status_label = tk.Label(
            outer,
            text=f"CLI executable: {self.exe_path} ({exe_status})",
            anchor="w",
            fg="#0f766e" if self.exe_path.exists() else "#b91c1c",
        )
        self.status_label.pack(fill=tk.X, pady=(0, 14))

        key_row = tk.Frame(outer)
        key_row.pack(fill=tk.X, pady=(0, 12))
        tk.Label(key_row, text="OpenAI API key", width=16, anchor="w").pack(side=tk.LEFT)
        tk.Entry(key_row, textvariable=self.api_key, show="*", width=72).pack(side=tk.LEFT, fill=tk.X, expand=True)

        dir_row = tk.Frame(outer)
        dir_row.pack(fill=tk.X, pady=(0, 18))
        tk.Label(dir_row, text="Results folder", width=16, anchor="w").pack(side=tk.LEFT)
        tk.Entry(dir_row, textvariable=self.results_dir, width=58).pack(side=tk.LEFT, fill=tk.X, expand=True)
        tk.Button(dir_row, text="Browse", command=self.choose_results_dir).pack(side=tk.LEFT, padx=(8, 0))

        hint = tk.Label(
            outer,
            text="The API key is passed only to the launched process. It is not saved by this launcher.",
            anchor="w",
            fg="#475569",
        )
        hint.pack(fill=tk.X, pady=(0, 22))

        buttons = tk.Frame(outer)
        buttons.pack(fill=tk.X)
        tk.Button(buttons, text="Start TradingAgents", width=22, height=2, command=self.start_cli).pack(side=tk.LEFT)
        tk.Button(buttons, text="Open Results Folder", width=22, height=2, command=self.open_results).pack(side=tk.LEFT, padx=12)
        tk.Button(buttons, text="Exit", width=12, height=2, command=self.destroy).pack(side=tk.RIGHT)

    def choose_results_dir(self):
        selected = filedialog.askdirectory(initialdir=self.results_dir.get() or str(default_results_dir()))
        if selected:
            self.results_dir.set(selected)

    def open_results(self):
        path = Path(self.results_dir.get()).expanduser()
        path.mkdir(parents=True, exist_ok=True)
        os.startfile(path)

    def start_cli(self):
        if not self.exe_path.exists():
            messagebox.showerror("Missing executable", f"Cannot find:\n{self.exe_path}")
            return

        results = Path(self.results_dir.get()).expanduser()
        results.mkdir(parents=True, exist_ok=True)

        env = os.environ.copy()
        key = self.api_key.get().strip()
        if key:
            env["OPENAI_API_KEY"] = key
        env["TRADINGAGENTS_RESULTS_DIR"] = str(results)

        command = f'cd /d "{self.exe_path.parent}" && "{self.exe_path}"'
        subprocess.Popen(
            ["cmd.exe", "/k", command],
            env=env,
            creationflags=subprocess.CREATE_NEW_CONSOLE,
        )


if __name__ == "__main__":
    Launcher().mainloop()
