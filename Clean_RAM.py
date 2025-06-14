import os
import psutil
import subprocess
import winreg
import ctypes
import logging
import shutil
import threading
import time
import sys


class RAMCleaner:
    def __init__(self):
        self.is_admin = ctypes.windll.shell32.IsUserAnAdmin() != 0
        if not self.is_admin:
            logging.warning(
                "⚠️ Le script n'est pas exécuté en tant qu'administrateur. Certaines fonctions seront limitées.")

    def print_memory_status(self):
        """Affiche l'état actuel de la mémoire"""
        mem = psutil.virtual_memory()
        logging.info(f"Mémoire totale: {mem.total / (1024 ** 3):.2f} GB")
        logging.info(f"Mémoire utilisée: {mem.used / (1024 ** 3):.2f} GB")
        logging.info(f"Mémoire disponible: {mem.available / (1024 ** 3):.2f} GB")
        logging.info(f"Pourcentage utilisé: {mem.percent}%")

    def clear_dns_cache(self):
        """Vide le cache DNS"""
        try:
            subprocess.run(['ipconfig', '/flushdns'], check=True, capture_output=True)
            logging.info("✔️ Cache DNS vidé avec succès")
        except subprocess.CalledProcessError as e:
            logging.error(f"❌ Erreur lors du vidage du cache DNS: {e}")

    def clear_temp_files(self):
        """Nettoie les fichiers temporaires"""
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
                        except Exception as e:
                            continue
                except Exception as e:
                    logging.error(f"❌ Erreur lors du nettoyage de {temp_path}: {e}")

        logging.info(f"✔️ {files_removed} fichiers temporaires supprimés")

    def clear_working_set(self):
        """Libère la mémoire de travail des processus"""
        try:
            for proc in psutil.process_iter(['pid', 'name', 'memory_info']):
                try:
                    # Obtient le handle du processus
                    handle = ctypes.windll.kernel32.OpenProcess(
                        0x1000,  # PROCESS_QUERY_INFORMATION
                        False,
                        proc.info['pid']
                    )
                    if handle:
                        # Tente de réduire le working set
                        ctypes.windll.psapi.EmptyWorkingSet(handle)
                        # Ferme le handle
                        ctypes.windll.kernel32.CloseHandle(handle)
                except Exception:
                    continue
            logging.info("✔️ Working sets des processus vidés")
        except Exception as e:
            logging.error(f"❌ Erreur lors du vidage des working sets: {e}")

    def optimize_startup(self):
        """Analyse et affiche les programmes au démarrage"""
        if not self.is_admin:
            logging.warning("⚠️ Droits administrateur requis pour modifier le démarrage")
            return

        startup_paths = [
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            r"Software\Microsoft\Windows\CurrentVersion\RunOnce"
        ]

        for path in startup_paths:
            try:
                key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path, 0, winreg.KEY_READ)
                count = winreg.QueryInfoKey(key)[1]
                logging.info(f"\nProgrammes au démarrage dans {path}:")
                for i in range(count):
                    try:
                        name, value, _ = winreg.EnumValue(key, i)
                        logging.info(f"- {name}: {value}")
                    except WindowsError:
                        continue
            except Exception as e:
                logging.error(f"❌ Erreur lors de la lecture de {path}: {e}")

    def clear_standby_list(self):
        """Vide la liste standby de la mémoire"""
        try:
            # Nécessite EmptyStandbyList.exe (à télécharger séparément)
            if os.path.exists("EmptyStandbyList.exe"):
                subprocess.run(['EmptyStandbyList.exe'], check=True, capture_output=True)
                logging.info("✔️ Liste standby vidée avec succès")
            else:
                logging.warning("⚠️ EmptyStandbyList.exe non trouvé")
        except subprocess.CalledProcessError as e:
            logging.error(f"❌ Erreur lors du vidage de la liste standby: {e}")

    def optimize_system_services(self):
        """Optimise les services système"""
        optional_services = [
            "SysMain",  # Superfetch
            "DiagTrack",  # Service de suivi des diagnostics
            "WSearch"  # Windows Search
        ]

        if not self.is_admin:
            logging.warning("⚠️ Droits administrateur requis pour modifier les services")
            return

        for service in optional_services:
            try:
                status = subprocess.run(
                    ['sc', 'query', service],
                    capture_output=True,
                    text=True
                )
                if "RUNNING" in status.stdout:
                    subprocess.run(
                        ['sc', 'stop', service],
                        check=True,
                        capture_output=True
                    )
                    logging.info(f"✔️ Service {service} arrêté")
            except subprocess.CalledProcessError:
                logging.error(f"❌ Erreur lors de l'arrêt du service {service}")

    def monitor_memory(self, duration=10):
        """Surveille l'utilisation de la mémoire pendant une durée donnée"""
        start_time = time.time()
        while time.time() - start_time < duration:
            mem = psutil.virtual_memory()
            logging.info(f"RAM utilisée: {mem.percent}% - "
                         f"Disponible: {mem.available / (1024 ** 3):.2f} GB")
            time.sleep(1)

    def clean_all(self):
        """Exécute toutes les optimisations disponibles"""
        logging.info("\n=== Début du nettoyage de la RAM ===")
        self.print_memory_status()

        # Démarrage de la surveillance dans un thread séparé
        monitor_thread = threading.Thread(target=self.monitor_memory)
        monitor_thread.daemon = True
        monitor_thread.start()

        # Exécution des différentes optimisations
        steps = [
            (self.clear_dns_cache, "Nettoyage du cache DNS"),
            (self.clear_temp_files, "Nettoyage des fichiers temporaires"),
            (self.clear_working_set, "Libération de la mémoire de travail"),
            (self.optimize_startup, "Analyse des programmes au démarrage"),
            (self.clear_standby_list, "Nettoyage de la liste standby"),
            (self.optimize_system_services, "Optimisation des services")
        ]

        for func, description in steps:
            logging.info(f"\n>> {description}...")
            func()
            time.sleep(1)  # Pause entre chaque étape

        logging.info("\n=== État final de la mémoire ===")
        self.print_memory_status()
        logging.info("\n✨ Nettoyage terminé")


def main():
    # Vérifie si Windows
    if os.name != 'nt':
        logging.error("❌ Ce script ne fonctionne que sous Windows")
        sys.exit(1)

    try:
        cleaner = RAMCleaner()
        cleaner.clean_all()
    except Exception as e:
        logging.error(f"❌ Erreur critique: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()