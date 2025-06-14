import os, datetime as dt
from collections import deque
import matplotlib.pyplot as plt, matplotlib
from matplotlib.patches import Rectangle
import wmi
import psutil
import logging
import sys

# Ajout de la gestion du chemin d'exécution
if getattr(sys, 'frozen', False):
    application_path = sys._MEIPASS
else:
    application_path = os.path.dirname(os.path.abspath(__file__))

# Configuration du logging avec chemin absolu
log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '../ram_cleaner.log')
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_path),
        logging.StreamHandler()
    ]
)

# Définir le backend Matplotlib explicitement
matplotlib.use('TkAgg')

# ---------- paramètres ----------
INTERVAL_MS = 5_000  # 5 s en millisecondes
WINDOW = 60 * 30  # historique 30 min
MAXPTS = WINDOW // (INTERVAL_MS // 1_000)

# ---------- helpers ----------
gb = lambda b: b / 1024 ** 3
ram = lambda: gb(psutil.virtual_memory().available)
disk = lambda: gb(psutil.disk_usage(os.path.abspath(os.sep)).free)
cpu_usage = lambda: psutil.cpu_percent(interval=None)


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


# ---------- buffers ----------
ts, ram_vals, disk_vals = (deque(maxlen=MAXPTS) for _ in range(3))

# ---------- figure ----------
plt.style.use("ggplot")
fig = plt.figure(figsize=(12, 8))
gs = fig.add_gridspec(2, 2, height_ratios=[3, 1])

# Graphique principal (RAM et Disque)
ax_ram = fig.add_subplot(gs[0, :])
ax_disk = ax_ram.twinx()

# Cases pour CPU et Température
ax_cpu = fig.add_subplot(gs[1, 0])
ax_temp = fig.add_subplot(gs[1, 1])

# Configuration des lignes
ln_ram, = ax_ram.plot([], [], "o-", color="tab:red", label="RAM")
ln_disk, = ax_disk.plot([], [], "s--", color="tab:blue", label="Disque")

# Configuration des axes
ax_ram.set_xlabel("Heure")
ax_ram.set_ylabel("RAM libre (Go)", color="tab:red")
ax_disk.set_ylabel("Stockage libre (Go)", color="tab:blue")
lines = [ln_ram, ln_disk]
labels = [l.get_label() for l in lines]
ax_ram.legend(lines, labels, loc="upper right")

# Configuration des cases CPU et Température
for ax in [ax_cpu, ax_temp]:
    ax.set_xticks([])
    ax.set_yticks([])

# Rectangles et textes
cpu_rect = Rectangle((0.1, 0.1), 0.8, 0.8, facecolor='lightgray')
temp_rect = Rectangle((0.1, 0.1), 0.8, 0.8, facecolor='lightgray')
ax_cpu.add_patch(cpu_rect)
ax_temp.add_patch(temp_rect)

cpu_text = ax_cpu.text(0.5, 0.5, "CPU: ---%",
                       horizontalalignment='center',
                       verticalalignment='center')
temp_text = ax_temp.text(0.5, 0.5, "Temp: ---°C",
                         horizontalalignment='center',
                         verticalalignment='center')

ax_cpu.set_title("Utilisation CPU")
ax_temp.set_title("Température")

# Format des dates
ax_ram.xaxis.set_major_formatter(matplotlib.dates.DateFormatter('%H:%M:%S'))
fig.autofmt_xdate()
fig.canvas.manager.set_window_title("Moniteur Système")


def update(event=None):
    now = dt.datetime.now()
    ts.append(now)
    ram_vals.append(ram())
    disk_vals.append(disk())

    current_cpu = cpu_usage()
    current_temp = get_temperature()

    # Mise à jour RAM et Disque
    ln_ram.set_data(ts, ram_vals)
    ln_disk.set_data(ts, disk_vals)

    # Mise à jour des limites des axes
    if len(ts) >= 2:
        ax_ram.set_xlim(ts[0], ts[-1])
    else:
        pad = dt.timedelta(seconds=1)
        ax_ram.set_xlim(ts[0] - pad, ts[0] + pad)

    if ram_vals:
        ax_ram.set_ylim(*auto_lim(ram_vals))
    if disk_vals:
        ax_disk.set_ylim(*auto_lim(disk_vals))

    # Mise à jour CPU et Température
    cpu_text.set_text(f"CPU: {current_cpu:.1f}%")
    if current_temp is not None:
        temp_text.set_text(f"Temp: {current_temp:.1f}°C")
        temp_val = min(max(current_temp - 40, 0) / 40, 1)
        temp_color = f"#{int(255 * temp_val):02x}ff{int(255 * (1 - temp_val)):02x}"
        temp_rect.set_facecolor(temp_color)
    else:
        temp_text.set_text("Temp: N/A")
        temp_rect.set_facecolor('lightgray')

    cpu_color = f"#{int(255 * current_cpu / 100):02x}ff{int(255 * (1 - current_cpu / 100)):02x}"
    cpu_rect.set_facecolor(cpu_color)

    fig.canvas.draw_idle()


def main():
    try:
        # Timer Matplotlib
        timer = fig.canvas.new_timer(interval=INTERVAL_MS)
        timer.add_callback(update)
        timer.start()

        print("⌛ Monitoring… Fermez la fenêtre ou Ctrl-C pour quitter.")
        print(f"Nombre de cœurs CPU : {psutil.cpu_count()}")
        update()  # premier point immédiat
        plt.show()  # boucle GUI
    except Exception as e:
        logging.error(f"Erreur : {e}")
        input("Appuyez sur Entrée pour quitter...")


if __name__ == "__main__":
    main()