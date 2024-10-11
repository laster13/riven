import threading
from .file_watcher import start_watching_yaml_file

def start_background_tasks():
    # Lancer la surveillance du fichier YAML dans un thread séparé
    watcher_thread = threading.Thread(target=start_watching_yaml_file)
    watcher_thread.daemon = True  # S'assurer que le thread se termine avec l'application
    watcher_thread.start()
