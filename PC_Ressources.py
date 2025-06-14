import os, datetime as dt
from collections import deque
import matplotlib.pyplot as plt, matplotlib
from matplotlib.patches import Rectangle  # Ajout de cet import explicite
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import wmi
import psutil
import logging
import tkinter as tk
from tkinter import ttk
import subprocess
import winreg
import shutil
import threading
import time


class SystemMonitorGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Moniteur Système Avancé")
        self.root.state('zoomed')  # Plein écran

        # Configuration du style
        self.style = ttk.Style()
        self.style.configure('Nav.TButton', padding=5)

        # Création de la barre de navigation
        self.create_navbar()

        # Création du conteneur principal
        self.main_container = ttk.Frame(self.root)
        self.main_container.pack(fill=tk.BOTH, expand=True)

        # Initialisation des pages
        self.pages = {}
        self.create_pages()

        # Afficher la page principale par défaut
        self.show_page('main')

    def create_navbar(self):
        navbar = ttk.Frame(self.root)
        navbar.pack(fill=tk.X, padx=5, pady=5)

        # Boutons de navigation
        ttk.Button(navbar, text="Moniteur Principal",
                   command=lambda: self.show_page('main'),
                   style='Nav.TButton').pack(side=tk.LEFT, padx=5)

        ttk.Button(navbar, text="Optimisation Stockage",
                   command=lambda: self.show_page('storage'),
                   style='Nav.TButton').pack(side=tk.LEFT, padx=5)

        ttk.Button(navbar, text="Optimisation RAM",
                   command=lambda: self.show_page('ram'),
                   style='Nav.TButton').pack(side=tk.LEFT, padx=5)

        ttk.Button(navbar, text="Performances",
                   command=lambda: self.show_page('performance'),
                   style='Nav.TButton').pack(side=tk.LEFT, padx=5)

    def create_pages(self):
        # Page principale (avec les graphiques existants)
        self.pages['main'] = MainPage(self.main_container)

        # Page d'optimisation du stockage
        self.pages['storage'] = StoragePage(self.main_container)

        # Page d'optimisation de la RAM
        self.pages['ram'] = RAMPage(self.main_container)

        # Page des performances
        self.pages['performance'] = PerformancePage(self.main_container)

    def show_page(self, page_name):
        # Cacher toutes les pages
        for page in self.pages.values():
            page.hide()

        # Afficher la page demandée
        self.pages[page_name].show()


class BasePage:
    def __init__(self, container):
        self.frame = ttk.Frame(container)
        self.frame.pack(fill=tk.BOTH, expand=True)
        self.create_widgets()

    def show(self):
        self.frame.pack(fill=tk.BOTH, expand=True)

    def hide(self):
        self.frame.pack_forget()

    def create_widgets(self):
        pass


class MainPage(BasePage):
    def create_widgets(self):
        # Configuration initiale
        self.INTERVAL_MS = 5000
        self.WINDOW = 60 * 30
        self.MAXPTS = self.WINDOW // (self.INTERVAL_MS // 1000)

        # Création des buffers pour les données
        self.ts, self.ram_vals, self.disk_vals = (deque(maxlen=self.MAXPTS) for _ in range(3))

        # Création de la figure principale
        self.fig = Figure(figsize=(12, 8))
        self.gs = self.fig.add_gridspec(3, 2, height_ratios=[0.2, 3, 1])

        # Zone des boutons rapides
        self.button_ax = self.fig.add_subplot(self.gs[0, :])
        self.button_ax.set_visible(False)

        # Graphiques RAM et Disque
        self.ax_ram = self.fig.add_subplot(self.gs[1, :])
        self.ax_disk = self.ax_ram.twinx()

        # Cases CPU et Température
        self.ax_cpu = self.fig.add_subplot(self.gs[2, 0])
        self.ax_temp = self.fig.add_subplot(self.gs[2, 1])

        # Configuration des lignes
        self.ln_ram, = self.ax_ram.plot([], [], "o-", color="tab:red", label="RAM")
        self.ln_disk, = self.ax_disk.plot([], [], "s--", color="tab:blue", label="Disque")

        # Configuration des axes
        self.setup_axes()
        self.setup_indicators()

        # Création du canvas Matplotlib
        self.canvas = FigureCanvasTkAgg(self.fig, self.frame)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        # Démarrage de la mise à jour
        self.start_update()

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
        self.cpu_rect = Rectangle((0.1, 0.2), 0.8, 0.6, facecolor='lightgray')  # Ajusté pour laisser de l'espace en bas
        self.temp_rect = Rectangle((0.1, 0.2), 0.8, 0.6,
                                   facecolor='lightgray')  # Ajusté pour laisser de l'espace en bas
        self.ax_cpu.add_patch(self.cpu_rect)
        self.ax_temp.add_patch(self.temp_rect)

        self.cpu_text = self.ax_cpu.text(0.5, 0.5, "CPU: ---%",
                                         horizontalalignment='center',
                                         verticalalignment='center')
        self.temp_text = self.ax_temp.text(0.5, 0.5, "Temp: ---°C",
                                           horizontalalignment='center',
                                           verticalalignment='center')

        # Déplacer les titres en bas
        self.ax_cpu.set_title("Utilisation CPU", pad=30, y=-0.2)  # y=-0.2 place le titre en dessous
        self.ax_temp.set_title("Température", pad=30, y=-0.2)  # pad=30 ajoute de l'espace

    def update(self):
        now = dt.datetime.now()
        self.ts.append(now)
        self.ram_vals.append(self.get_ram())
        self.disk_vals.append(self.get_disk())

        current_cpu = self.get_cpu_usage()
        current_temp = self.get_temperature()

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
            self.ax_ram.set_ylim(*self.auto_lim(self.ram_vals))
        if self.disk_vals:
            self.ax_disk.set_ylim(*self.auto_lim(self.disk_vals))

        # Mise à jour CPU et Température
        self.update_indicators(current_cpu, current_temp)

        self.canvas.draw_idle()
        self.frame.after(self.INTERVAL_MS, self.update)

    def start_update(self):
        self.update()
        self.frame.after(self.INTERVAL_MS, self.update)

    @staticmethod
    def get_ram():
        return psutil.virtual_memory().available / (1024 ** 3)

    @staticmethod
    def get_disk():
        return psutil.disk_usage(os.path.abspath(os.sep)).free / (1024 ** 3)

    @staticmethod
    def get_cpu_usage():
        return psutil.cpu_percent(interval=None)

    @staticmethod
    def get_temperature():
        try:
            w = wmi.WMI(namespace="root/wmi")
            temperature_info = w.MSAcpi_ThermalZoneTemperature()[0]
            return float(temperature_info.CurrentTemperature) / 10 - 273.15
        except Exception:
            return None

    def update_indicators(self, cpu_value, temp_value):
        self.cpu_text.set_text(f"CPU: {cpu_value:.1f}%")
        if temp_value is not None:
            self.temp_text.set_text(f"Temp: {temp_value:.1f}°C")
            temp_val = min(max(temp_value - 40, 0) / 40, 1)
            temp_color = f"#{int(255 * temp_val):02x}ff{int(255 * (1 - temp_val)):02x}"
            self.temp_rect.set_facecolor(temp_color)
        else:
            self.temp_text.set_text("Temp: N/A")
            self.temp_rect.set_facecolor('lightgray')

        cpu_color = f"#{int(255 * cpu_value / 100):02x}ff{int(255 * (1 - cpu_value / 100)):02x}"
        self.cpu_rect.set_facecolor(cpu_color)

    @staticmethod
    def auto_lim(v, pad=0.10, min_pad=1):
        if not v:
            return 0, 1
        lo, hi = min(v), max(v)
        eps = max((hi - lo) * pad, min_pad)
        return max(0, lo - eps), hi + eps


class StoragePage(BasePage):
    def create_widgets(self):
        # Frame pour les contrôles
        control_frame = ttk.LabelFrame(self.frame, text="Optimisation du stockage")
        control_frame.pack(fill=tk.X, padx=10, pady=5)

        # Boutons d'action
        ttk.Button(control_frame, text="Nettoyer WinSxS",
                   command=self.clean_winsxs).pack(side=tk.LEFT, padx=5, pady=5)

        ttk.Button(control_frame, text="Nettoyer Prefetch",
                   command=self.clean_prefetch).pack(side=tk.LEFT, padx=5, pady=5)

        ttk.Button(control_frame, text="Analyser gros fichiers",
                   command=self.analyze_large_files).pack(side=tk.LEFT, padx=5, pady=5)

        # Zone de résultats
        self.result_text = tk.Text(self.frame, height=20)
        self.result_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

    def clean_winsxs(self):
        try:
            os.system('Dism.exe /online /Cleanup-Image /StartComponentCleanup')
            self.result_text.insert(tk.END, "Nettoyage WinSxS terminé\n")
        except Exception as e:
            self.result_text.insert(tk.END, f"Erreur: {str(e)}\n")

    def clean_prefetch(self):
        prefetch_path = "C:\\Windows\\Prefetch"
        try:
            files = os.listdir(prefetch_path)
            for file in files:
                try:
                    os.remove(os.path.join(prefetch_path, file))
                except:
                    continue
            self.result_text.insert(tk.END, "Nettoyage Prefetch terminé\n")
        except Exception as e:
            self.result_text.insert(tk.END, f"Erreur: {str(e)}\n")

    def analyze_large_files(self):
        self.result_text.delete(1.0, tk.END)
        self.result_text.insert(tk.END, "Analyse en cours...\n")

        def scan_directory(path):
            large_files = []
            for root, dirs, files in os.walk(path):
                for file in files:
                    try:
                        file_path = os.path.join(root, file)
                        size = os.path.getsize(file_path)
                        if size > 100_000_000:  # 100 MB
                            large_files.append((file_path, size))
                    except:
                        continue
            return sorted(large_files, key=lambda x: x[1], reverse=True)[:20]

        results = scan_directory("C:\\")
        self.result_text.delete(1.0, tk.END)
        self.result_text.insert(tk.END, "Les 20 plus gros fichiers:\n\n")
        for path, size in results:
            size_gb = size / (1024 ** 3)
            self.result_text.insert(tk.END, f"{path}: {size_gb:.2f} GB\n")


class RAMPage(BasePage):
    def create_widgets(self):
        # Frame pour les contrôles
        control_frame = ttk.LabelFrame(self.frame, text="Optimisation de la RAM")
        control_frame.pack(fill=tk.X, padx=10, pady=5)

        # Boutons d'action
        ttk.Button(control_frame, text="Optimiser Buffer Système",
                   command=self.optimize_system_buffer).pack(side=tk.LEFT, padx=5, pady=5)

        ttk.Button(control_frame, text="Nettoyer Cache Navigateurs",
                   command=self.clean_browser_cache).pack(side=tk.LEFT, padx=5, pady=5)

        ttk.Button(control_frame, text="Analyser Consommation RAM",
                   command=self.analyze_ram_usage).pack(side=tk.LEFT, padx=5, pady=5)

        # Zone de résultats
        self.result_text = tk.Text(self.frame, height=20)
        self.result_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

    def optimize_system_buffer(self):
        try:
            # Vider le cache système
            os.system('ipconfig /flushdns')  # Cache DNS
            # Autres optimisations du buffer...
            self.result_text.insert(tk.END, "Optimisation du buffer système terminée\n")
        except Exception as e:
            self.result_text.insert(tk.END, f"Erreur: {str(e)}\n")

    def clean_browser_cache(self):
        browsers = {
            'Chrome': os.path.expanduser('~\\AppData\\Local\\Google\\Chrome\\User Data\\Default\\Cache'),
            'Firefox': os.path.expanduser('~\\AppData\\Local\\Mozilla\\Firefox\\Profiles'),
            'Edge': os.path.expanduser('~\\AppData\\Local\\Microsoft\\Edge\\User Data\\Default\\Cache')
        }

        for browser, path in browsers.items():
            try:
                if os.path.exists(path):
                    shutil.rmtree(path)
                    self.result_text.insert(tk.END, f"Cache {browser} nettoyé\n")
            except Exception as e:
                self.result_text.insert(tk.END, f"Erreur {browser}: {str(e)}\n")

    def analyze_ram_usage(self):
        self.result_text.delete(1.0, tk.END)
        processes = []
        for proc in psutil.process_iter(['pid', 'name', 'memory_info']):
            try:
                processes.append({
                    'name': proc.info['name'],
                    'memory': proc.info['memory_info'].rss
                })
            except:
                continue

        processes.sort(key=lambda x: x['memory'], reverse=True)
        self.result_text.insert(tk.END, "Top 20 processus par utilisation RAM:\n\n")
        for proc in processes[:20]:
            mem_mb = proc['memory'] / (1024 ** 2)
            self.result_text.insert(tk.END, f"{proc['name']}: {mem_mb:.1f} MB\n")


class PerformancePage(BasePage):
    def create_widgets(self):
        # Frame principal
        main_frame = ttk.Frame(self.frame)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        # Frame pour les graphiques de performance
        self.fig = Figure(figsize=(12, 8))

        # Créer un GridSpec avec plus d'espace entre les rangées
        gs = self.fig.add_gridspec(2, 2, height_ratios=[1, 1], hspace=0.4)  # hspace=0.4 ajoute plus d'espace vertical

        # Graphique CPU par cœur
        self.ax_cpu_cores = self.fig.add_subplot(gs[0, 0])
        self.ax_cpu_cores.set_title("Utilisation CPU par cœur")
        self.ax_cpu_cores.set_ylabel("Utilisation (%)")

        # Graphique Mémoire détaillé
        self.ax_memory = self.fig.add_subplot(gs[0, 1])
        self.ax_memory.set_title("Utilisation détaillée de la mémoire")

        # Graphique E/S Disque
        self.ax_disk_io = self.fig.add_subplot(gs[1, 0])
        self.ax_disk_io.set_title("Activité Disque (MB/s)")

        # Graphique Réseau
        self.ax_network = self.fig.add_subplot(gs[1, 1])
        self.ax_network.set_title("Activité Réseau (MB/s)")

        # Ajuster les espacements globaux de la figure
        self.fig.tight_layout(h_pad=3.0)  # Augmente l'espacement horizontal entre les sous-graphiques

        # Création du canvas
        self.canvas = FigureCanvasTkAgg(self.fig, main_frame)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        # Frame pour les contrôles
        control_frame = ttk.LabelFrame(main_frame, text="Contrôles de performance")
        control_frame.pack(fill=tk.X, pady=5)

        # Boutons de contrôle avec plus d'espacement
        ttk.Button(control_frame, text="Optimiser Services",
                   command=self.optimize_services).pack(side=tk.LEFT, padx=10, pady=5)  # padx augmenté

        ttk.Button(control_frame, text="Mode Performance",
                   command=self.enable_performance_mode).pack(side=tk.LEFT, padx=10, pady=5)  # padx augmenté

        ttk.Button(control_frame, text="Analyser démarrage",
                   command=self.analyze_startup).pack(side=tk.LEFT, padx=10, pady=5)  # padx augmenté

        # Zone de résultats avec plus de marge
        self.result_text = tk.Text(main_frame, height=6)
        self.result_text.pack(fill=tk.X, pady=10)  # pady augmenté

        # Démarrer la mise à jour
        self.start_update()

    def update_graphs(self):
        # Mise à jour CPU par cœur
        cpu_percent = psutil.cpu_percent(percpu=True)
        self.ax_cpu_cores.clear()
        self.ax_cpu_cores.bar(range(len(cpu_percent)), cpu_percent)
        self.ax_cpu_cores.set_title("Utilisation CPU par cœur")
        self.ax_cpu_cores.set_ylim(0, 100)

        # Mise à jour Mémoire - Version Windows
        mem = psutil.virtual_memory()
        labels = ['En utilisation', 'Disponible']
        total_gb = mem.total / (1024 ** 3)
        used_gb = (mem.total - mem.available) / (1024 ** 3)
        available_gb = mem.available / (1024 ** 3)

        sizes = [
            (mem.total - mem.available) / mem.total * 100,  # Utilisé
            mem.available / mem.total * 100  # Disponible
        ]

        self.ax_memory.clear()
        self.ax_memory.pie(sizes, labels=labels, autopct='%1.1f%%')
        self.ax_memory.set_title(f"Mémoire totale: {total_gb:.1f} GB\n"
                                 f"Utilisé: {used_gb:.1f} GB\n"
                                 f"Disponible: {available_gb:.1f} GB")

        # Mise à jour E/S Disque
        try:
            disk_io = psutil.disk_io_counters()
            read_mb = disk_io.read_bytes / 1048576
            write_mb = disk_io.write_bytes / 1048576
        except Exception:
            read_mb = write_mb = 0

        self.ax_disk_io.clear()
        self.ax_disk_io.bar(['Lecture', 'Écriture'], [read_mb, write_mb])
        self.ax_disk_io.set_title("Activité Disque (MB/s)")

        # Mise à jour Réseau
        try:
            net_io = psutil.net_io_counters()
            sent_mb = net_io.bytes_sent / 1048576
            recv_mb = net_io.bytes_recv / 1048576
        except Exception:
            sent_mb = recv_mb = 0

        self.ax_network.clear()
        self.ax_network.bar(['Envoyé', 'Reçu'], [sent_mb, recv_mb])
        self.ax_network.set_title("Activité Réseau (MB)")

        # Ajout d'une grille et des étiquettes d'axes pour les graphiques en barre
        for ax in [self.ax_disk_io, self.ax_network]:
            ax.grid(True, axis='y')
            ax.set_ylabel('MB')

        for ax in [self.ax_cpu_cores]:
            ax.grid(True, axis='y')
            ax.set_ylabel('%')
            ax.set_xlabel('Cœurs CPU')

        self.canvas.draw_idle()
        self.frame.after(1000, self.update_graphs)

    def start_update(self):
        self.update_graphs()

    def optimize_services(self):
        """Optimise les services Windows non essentiels"""
        services_to_optimize = [
            "SysMain",  # Superfetch
            "DiagTrack",  # Service de diagnostics
            "WSearch"  # Windows Search
        ]

        results = []
        for service in services_to_optimize:
            try:
                status = subprocess.run(['sc', 'query', service],
                                        capture_output=True,
                                        text=True)
                if "RUNNING" in status.stdout:
                    subprocess.run(['sc', 'stop', service],
                                   check=True,
                                   capture_output=True)
                    results.append(f"Service {service} arrêté")
            except Exception as e:
                results.append(f"Erreur avec {service}: {str(e)}")

        self.result_text.delete(1.0, tk.END)
        self.result_text.insert(tk.END, "\n".join(results))

    def enable_performance_mode(self):
        """Active le mode haute performance"""
        try:
            # Désactive les effets visuels
            subprocess.run(['powershell',
                            'Set-ItemProperty -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\VisualEffects" -Name "VisualFXSetting" -Value 2'])

            # Configure le plan d'alimentation
            subprocess.run(['powercfg', '/setactive', '8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c'])

            self.result_text.delete(1.0, tk.END)
            self.result_text.insert(tk.END, "Mode performance activé")
        except Exception as e:
            self.result_text.delete(1.0, tk.END)
            self.result_text.insert(tk.END, f"Erreur: {str(e)}")

    def analyze_startup(self):
        """Analyse les programmes au démarrage"""
        try:
            startup_items = []

            # Analyse du registre
            keys = [
                r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run",
                r"SOFTWARE\Microsoft\Windows\CurrentVersion\RunOnce"
            ]

            for key_path in keys:
                try:
                    key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path)
                    i = 0
                    while True:
                        try:
                            name, value, _ = winreg.EnumValue(key, i)
                            startup_items.append(f"HKLM\\{key_path}\\{name}")
                            i += 1
                        except WindowsError:
                            break
                except WindowsError:
                    continue

            self.result_text.delete(1.0, tk.END)
            self.result_text.insert(tk.END, "Programmes au démarrage:\n\n")
            for item in startup_items:
                self.result_text.insert(tk.END, f"{item}\n")

        except Exception as e:
            self.result_text.delete(1.0, tk.END)
            self.result_text.insert(tk.END, f"Erreur: {str(e)}")


def main():
    app = SystemMonitorGUI()
    app.root.mainloop()


if __name__ == "__main__":
    main()