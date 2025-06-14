import os, datetime as dt
from collections import deque
import matplotlib.pyplot as plt, matplotlib
from matplotlib.patches import Rectangle
import wmi
import psutil
import logging
import sys
from matplotlib.widgets import Button
import ctypes
import subprocess
import winreg
import tempfile
import shutil
import threading
import time
import codecs


# Configuration du logging avec encodage UTF-8
class UTFStreamHandler(logging.StreamHandler):
    def emit(self, record):
        try:
            msg = self.format(record)
            stream = self.stream
            stream.write(msg + self.terminator)
            self.flush()
        except Exception:
            self.handleError(record)


# Configuration du logging
log_file = 'monitor.log'
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file, encoding='utf-8'),
        UTFStreamHandler()
    ]
)


class RAMCleaner:
    def __init__(self):
        self.is_admin = ctypes.windll.shell32.IsUserAnAdmin() != 0
        if not self.is_admin:
            logging.warning(
                "Le script n'est pas exécuté en tant qu'administrateur. Certaines fonctions seront limitées.")

    def clear_dns_cache(self):
        try:
            subprocess.run(['ipconfig', '/flushdns'], check=True, capture_output=True)
            logging.info("Cache DNS vidé avec succès")
            return True
        except subprocess.CalledProcessError as e:
            logging.error(f"Erreur lors du vidage du cache DNS: {e}")
            return False

    def clear_temp_files(self):
        temp_paths = [
            os.environ.get('TEMP'),
            os.environ.get('TMP'),
            os.path.join(os.environ.get('WINDIR'), 'Temp')
        ]

        files_removed = 0
        for temp_path in temp_paths:
            if temp_path and os.path.exists(temp_path):
                try:
                    for item in os.listdir(temp_path):
                        item_path = os.path.join(temp_path, item)
                        try:
                            if os.path.isfile(item_path):
                                os.unlink(item_path)
                            elif os.path.isdir(item_path):
                                shutil.rmtree(item_path)
                            files_removed += 1
                        except Exception:
                            continue
                except Exception as e:
                    logging.error(f"Erreur lors du nettoyage de {temp_path}: {e}")

        logging.info(f"{files_removed} fichiers temporaires supprimés")
        return files_removed > 0

    def clear_working_set(self):
        try:
            for proc in psutil.process_iter(['pid', 'name', 'memory_info']):
                try:
                    handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, proc.info['pid'])
                    if handle:
                        ctypes.windll.psapi.EmptyWorkingSet(handle)
                        ctypes.windll.kernel32.CloseHandle(handle)
                except Exception:
                    continue
            logging.info("Working sets des processus vidés")
            return True
        except Exception as e:
            logging.error(f"Erreur lors du vidage des working sets: {e}")
            return False


class SystemMonitor:
    def __init__(self):
        self.INTERVAL_MS = 5_000
        self.WINDOW = 60 * 30
        self.MAXPTS = self.WINDOW // (self.INTERVAL_MS // 1_000)

        self.ram_cleaner = RAMCleaner()
        self.setup_plot()
        self.setup_buttons()

    def setup_plot(self):
        self.ts, self.ram_vals, self.disk_vals = (deque(maxlen=self.MAXPTS) for _ in range(3))

        plt.style.use("ggplot")
        self.fig = plt.figure(figsize=(12, 8))

        # Ajustement de la mise en page pour les boutons
        gs = self.fig.add_gridspec(3, 2, height_ratios=[0.2, 3, 1])

        # Zone des boutons
        self.button_ax = self.fig.add_subplot(gs[0, :])
        self.button_ax.set_visible(False)

        # Graphique principal
        self.ax_ram = self.fig.add_subplot(gs[1, :])
        self.ax_disk = self.ax_ram.twinx()

        # Cases CPU et Température
        self.ax_cpu = self.fig.add_subplot(gs[2, 0])
        self.ax_temp = self.fig.add_subplot(gs[2, 1])

        # Configuration des lignes
        self.ln_ram, = self.ax_ram.plot([], [], "o-", color="tab:red", label="RAM")
        self.ln_disk, = self.ax_disk.plot([], [], "s--", color="tab:blue", label="Disque")

        self.setup_axes()
        self.setup_indicators()

    def setup_buttons(self):
        # Création des boutons
        button_width = 0.15
        button_height = 0.6
        button_y = 0.2

        # Positions des boutons
        positions = [0.05, 0.25, 0.45, 0.65, 0.85]

        # Création des boutons avec leurs callbacks
        self.buttons = []

        actions = [
            ("Vider DNS", self.ram_cleaner.clear_dns_cache),
            ("Vider Temp", self.ram_cleaner.clear_temp_files),
            ("Vider RAM", self.ram_cleaner.clear_working_set),
            ("Tout nettoyer", self.clean_all),
            ("Actualiser", self.force_update)
        ]

        for pos, (label, action) in zip(positions, actions):
            ax = plt.axes([pos, 0.92, button_width, button_height / 10])
            btn = Button(ax, label)
            btn.on_clicked(self.create_callback(action))
            self.buttons.append(btn)

    def create_callback(self, action):
        def callback(event):
            try:
                action()
                self.force_update()
            except Exception as e:
                logging.error(f"Erreur lors de l'exécution de {action.__name__}: {e}")

        return callback

    def clean_all(self):
        self.ram_cleaner.clear_dns_cache()
        self.ram_cleaner.clear_temp_files()
        self.ram_cleaner.clear_working_set()

    def force_update(self):
        self.update()
        self.fig.canvas.draw_idle()

    def setup_axes(self):
        self.ax_ram.set_xlabel("Heure")
        self.ax_ram.set_ylabel("RAM libre (Go)", color="tab:red")
        self.ax_disk.set_ylabel("Stockage libre (Go)", color="tab:blue")

        lines = [self.ln_ram, self.ln_disk]
        labels = [l.get_label() for l in lines]
        self.ax_ram.legend(lines, labels, loc="upper right")

        for ax in [self.ax_cpu, self.ax_temp]:
            ax.set_xticks([])
            ax.set_yticks([])

    def setup_indicators(self):
        self.cpu_rect = Rectangle((0.1, 0.1), 0.8, 0.8, facecolor='lightgray')
        self.temp_rect = Rectangle((0.1, 0.1), 0.8, 0.8, facecolor='lightgray')
        self.ax_cpu.add_patch(self.cpu_rect)
        self.ax_temp.add_patch(self.temp_rect)

        self.cpu_text = self.ax_cpu.text(0.5, 0.5, "CPU: ---%",
                                         horizontalalignment='center',
                                         verticalalignment='center')
        self.temp_text = self.ax_temp.text(0.5, 0.5, "Temp: ---°C",
                                           horizontalalignment='center',
                                           verticalalignment='center')

        self.ax_cpu.set_title("Utilisation CPU")
        self.ax_temp.set_title("Température")

        self.ax_ram.xaxis.set_major_formatter(matplotlib.dates.DateFormatter('%H:%M:%S'))
        self.fig.autofmt_xdate()
        self.fig.canvas.manager.set_window_title("Moniteur Système")

    def update(self, event=None):
        now = dt.datetime.now()
        self.ts.append(now)
        self.ram_vals.append(gb(psutil.virtual_memory().available))
        self.disk_vals.append(gb(psutil.disk_usage(os.path.abspath(os.sep)).free))

        current_cpu = psutil.cpu_percent(interval=None)
        current_temp = get_temperature()

        # Mise à jour des graphiques
        self.ln_ram.set_data(self.ts, self.ram_vals)
        self.ln_disk.set_data(self.ts, self.disk_vals)

        # Mise à jour des limites
        if len(self.ts) >= 2:
            self.ax_ram.set_xlim(self.ts[0], self.ts[-1])
        else:
            pad = dt.timedelta(seconds=1)
            self.ax_ram.set_xlim(self.ts[0] - pad, self.ts[0] + pad)

        if self.ram_vals:
            self.ax_ram.set_ylim(*auto_lim(self.ram_vals))
        if self.disk_vals:
            self.ax_disk.set_ylim(*auto_lim(self.disk_vals))

        # Mise à jour CPU et Température
        self.cpu_text.set_text(f"CPU: {current_cpu:.1f}%")
        if current_temp is not None:
            self.temp_text.set_text(f"Temp: {current_temp:.1f}°C")
            temp_val = min(max(current_temp - 40, 0) / 40, 1)
            temp_color = f"#{int(255 * temp_val):02x}ff{int(255 * (1 - temp_val)):02x}"
            self.temp_rect.set_facecolor(temp_color)
        else:
            self.temp_text.set_text("Temp: N/A")
            self.temp_rect.set_facecolor('lightgray')

        cpu_color = f"#{int(255 * current_cpu / 100):02x}ff{int(255 * (1 - current_cpu / 100)):02x}"
        self.cpu_rect.set_facecolor(cpu_color)

        self.fig.canvas.draw_idle()

    def run(self):
        timer = self.fig.canvas.new_timer(interval=self.INTERVAL_MS)
        timer.add_callback(self.update)
        timer.start()

        print("⌛ Monitoring… Fermez la fenêtre ou Ctrl-C pour quitter.")
        print(f"Nombre de cœurs CPU : {psutil.cpu_count()}")
        self.update()
        plt.show()


# Fonctions helper
gb = lambda b: b / 1024 ** 3


def get_temperature():
    try:
        w = wmi.WMI(namespace="root/wmi")
        temperature_info = w.MSAcpi_ThermalZoneTemperature()[0]
        temp_kelvin = float(temperature_info.CurrentTemperature) / 10
        return temp_kelvin - 273.15
    except Exception:
        try:
            w = wmi.WMI()
            temps = w.Win32_TemperatureProbe()
            if temps:
                return float(temps[0].CurrentReading)
        except Exception:
            return None
    return None


def auto_lim(v, pad=0.10, min_pad=1):
    if not v:
        return 0, 1
    lo, hi = min(v), max(v)
    eps = max((hi - lo) * pad, min_pad)
    return max(0, lo - eps), hi + eps


def main():
    try:
        monitor = SystemMonitor()
        monitor.run()
    except Exception as e:
        logging.error(f"Erreur critique : {e}")
        input("Appuyez sur Entrée pour quitter...")


if __name__ == "__main__":
    main()