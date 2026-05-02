import tkinter as tk
from tkinter import ttk, messagebox
import requests
import threading
import time
from datetime import datetime
import matplotlib
matplotlib.use("TkAgg")
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

# ---------------------------------------------------------
# CONFIG
# ---------------------------------------------------------
API_URL = "https://www.alphavantage.co/query"

UPDATE_INTERVAL = 60

# ---------------------------------------------------------
# App
# ---------------------------------------------------------
class StockTrackerApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Python Stock Price Tracker")
        self.geometry("800x550")
        self.resizable(False, False)

        self.api_key = tk.StringVar()
        self.symbol = tk.StringVar(value="AAPL")
        self.status_text = tk.StringVar(value="Stopped")
        self.latest_price = tk.StringVar(value="N/A")
        self.is_running = False

        # Data storage for plotting
        self.times = []
        self.prices = []

        self._build_ui()
        self.worker_thread = None

    def _build_ui(self):
        # Top frame: inputs and controls
        top_frame = ttk.Frame(self, padding=10)
        top_frame.pack(side=tk.TOP, fill=tk.X)

        # API Key
        ttk.Label(top_frame, text="Alpha Vantage API Key:").grid(row=0, column=0, sticky=tk.W)
        api_entry = ttk.Entry(top_frame, textvariable=self.api_key, width=40, show="*")
        api_entry.grid(row=0, column=1, columnspan=3, sticky=tk.W, padx=5)

        # Show/Hide API key checkbox
        self.show_key_var = tk.BooleanVar(value=False)
        def toggle_show_key():
            api_entry.config(show="" if self.show_key_var.get() else "*")
        ttk.Checkbutton(top_frame, text="Show key", variable=self.show_key_var, command=toggle_show_key).grid(row=0, column=4, padx=5)

        # Stock symbol
        ttk.Label(top_frame, text="Symbol:").grid(row=1, column=0, sticky=tk.W, pady=(8,0))
        ttk.Entry(top_frame, textvariable=self.symbol, width=12).grid(row=1, column=1, sticky=tk.W, pady=(8,0))

        # Update interval (seconds)
        ttk.Label(top_frame, text="Interval (s):").grid(row=1, column=2, sticky=tk.W, padx=(10,0), pady=(8,0))
        self.interval_var = tk.IntVar(value=UPDATE_INTERVAL)
        ttk.Entry(top_frame, textvariable=self.interval_var, width=6).grid(row=1, column=3, sticky=tk.W, pady=(8,0))

        # Start / Stop buttons
        start_btn = ttk.Button(top_frame, text="Start", command=self.start)
        start_btn.grid(row=1, column=4, padx=(10,5), pady=(8,0))
        stop_btn = ttk.Button(top_frame, text="Stop", command=self.stop)
        stop_btn.grid(row=1, column=5, pady=(8,0))

        # Status and latest price
        status_frame = ttk.Frame(self, padding=(10,5))
        status_frame.pack(side=tk.TOP, fill=tk.X)
        ttk.Label(status_frame, text="Status:").pack(side=tk.LEFT)
        ttk.Label(status_frame, textvariable=self.status_text).pack(side=tk.LEFT, padx=(5,20))
        ttk.Label(status_frame, text="Latest Price:").pack(side=tk.LEFT)
        ttk.Label(status_frame, textvariable=self.latest_price, font=("Helvetica", 12, "bold")).pack(side=tk.LEFT, padx=(5,0))

        # Plot area
        plot_frame = ttk.Frame(self, padding=10, relief=tk.GROOVE)
        plot_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=10, pady=10)

        self.fig = Figure(figsize=(8,4.5), dpi=100)
        self.ax = self.fig.add_subplot(111)
        self.ax.set_title("Price history")
        self.ax.set_xlabel("Time")
        self.ax.set_ylabel("Price")
        self.line, = self.ax.plot([], [], marker='o')

        self.canvas = FigureCanvasTkAgg(self.fig, master=plot_frame)
        self.canvas.draw()
        self.canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=True)

    # -----------------------------------------------------
    # Start/Stop
    # -----------------------------------------------------
    def start(self):
        key = self.api_key.get().strip()
        if not key:
            messagebox.showwarning("API Key required", "Please enter your Alpha Vantage API key.")
            return

        if self.is_running:
            return
        self.is_running = True
        self.status_text.set("Running")
        # reset data
        self.times.clear()
        self.prices.clear()
        self._clear_plot()
        self.worker_thread = threading.Thread(target=self._run_loop, daemon=True)
        self.worker_thread.start()

    def stop(self):
        if not self.is_running:
            return
        self.is_running = False
        self.status_text.set("Stopping...")

    # -----------------------------------------------------
    # Worker loop (running in a separate thread)
    # -----------------------------------------------------
    def _run_loop(self):
        while self.is_running:
            try:
                interval = max(5, int(self.interval_var.get()))  # minimum 5s to prevent flooding
            except Exception:
                interval = UPDATE_INTERVAL

            price = self._fetch_latest_price(self.symbol.get().strip(), self.api_key.get().strip())
            if isinstance(price, float):
                now = datetime.now().strftime("%H:%M:%S")
                self.times.append(now)
                self.prices.append(price)
                # Keep only last 60 points to avoid huge memory usage
                if len(self.times) > 60:
                    self.times.pop(0)
                    self.prices.pop(0)
                # update UI in main thread
                self.after(0, self._update_ui, price)
            else:
                # price is an error string, update UI to show it
                self.after(0, self._update_error_ui, price)

            # Respect the interval
            # If user changed interval, we honor it on next loop
            # But if the request failed and returned an error, still wait interval seconds
            sleep_seconds = interval
            for _ in range(int(sleep_seconds)):
                if not self.is_running:
                    break
                time.sleep(1)

        # update final status
        self.after(0, lambda: self.status_text.set("Stopped"))

    # -----------------------------------------------------
    # Fetch price from Alpha Vantage
    # -----------------------------------------------------
    def _fetch_latest_price(self, symbol, api_key):
        if not symbol:
            return "Error: Empty symbol"

        params = {
            "function": "TIME_SERIES_INTRADAY",
            "symbol": symbol,
            "interval": "1min",
            "apikey": api_key,
            "outputsize": "compact"
        }

        try:
            resp = requests.get(API_URL, params=params, timeout=10)
            data = resp.json()
        except Exception as e:
            return f"Network error: {e}"

        # Check for common error messages from Alpha Vantage
        if "Note" in data:
            # Rate limit or other note
            return "API Note: Rate limit reached. Try increasing interval."
        if "Error Message" in data:
            return "API Error: Invalid symbol or request."
        if "Time Series (1min)" not in data:
            # Unexpected structure
            return "API Error: Unexpected response."

        try:
            time_keys = sorted(list(data["Time Series (1min)"].keys()), reverse=True)
            latest_time = time_keys[0]
            latest_price_str = data["Time Series (1min)"][latest_time]["1. open"]
            price = float(latest_price_str)
            return price
        except Exception as e:
            return f"Parse error: {e}"

    # -----------------------------------------------------
    # UI update methods
    # -----------------------------------------------------
    def _update_ui(self, price):
        self.latest_price.set(f"{price:.2f}")
        self.status_text.set(f"Running — last update {datetime.now().strftime('%H:%M:%S')}")
        self._update_plot()

    def _update_error_ui(self, error_message):
        self.status_text.set(error_message)
        # leave previous price as-is

    def _clear_plot(self):
        self.ax.cla()
        self.ax.set_title("Price history")
        self.ax.set_xlabel("Time")
        self.ax.set_ylabel("Price")
        self.canvas.draw()

    def _update_plot(self):
        self.ax.cla()
        self.ax.set_title(f"{self.symbol.get().upper()} Price history")
        self.ax.set_xlabel("Time")
        self.ax.set_ylabel("Price")
        if self.times and self.prices:
            self.ax.plot(self.times, self.prices, marker='o', linestyle='-')
            # rotate x labels for readability
            for label in self.ax.get_xticklabels():
                label.set_rotation(45)
                label.set_ha('right')
        self.canvas.draw()


if __name__ == "__main__":
    app = StockTrackerApp()
    app.mainloop()
