import subprocess
import os
import time
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from plyer import notification


# === CONFIG ===
REMOTE_USER = "pi"
#REMOTE_HOST = "192.168.1.105"
REMOTE_HOST = "10.35.113.70"
REMOTE_HOST = "192.168.4.1"
REMOTE_PATH = "/home/pi/sunmirror"
WATCH_PATH = "./"
INCLUDE_EXTENSIONS = {".py", ".txt", ".json", ".html"}  # only sync these file types (optional)

class SCPSyncHandler(FileSystemEventHandler):
    def on_modified(self, event):
        if event.is_directory:
            return

        filepath = event.src_path
        _, ext = os.path.splitext(filepath)
        #if INCLUDE_EXTENSIONS and ext not in INCLUDE_EXTENSIONS:
        #    return

        print(f"[MODIFIED] {filepath} → syncing...")
        self.sync_file(filepath)

    def sync_file(self, filepath):
        try:
            subprocess.run([
                "scp", filepath,
                f"{REMOTE_USER}@{REMOTE_HOST}:{REMOTE_PATH}"
            ], check=True)

            filename = os.path.basename(filepath)


            print(f"✅ Synced {filename}")

            # ✅ Show popup
            notification.notify(
                title="File Synced",
                message=f"{filename} → {REMOTE_HOST}",
                timeout=3  # seconds
            )
        except subprocess.CalledProcessError as e:
            print(f"❌ SCP failed: {e}")
            notification.notify(
                title="Sync Failed",
                message=f"{filepath}",
                timeout=4
            )

def sync_all_files():
    print("🔄 Syncing all files...")
    for root, _, files in os.walk(WATCH_PATH):
        for file in files:
            if file.endswith('.py'):  # Only sync Python files
                filepath = os.path.join(root, file)
                print(f"[SYNC] {file}")
                subprocess.run([
                    "scp", filepath,
                    f"{REMOTE_USER}@{REMOTE_HOST}:{REMOTE_PATH}"
                ], check=True)
    print("✅ Initial sync complete")

if __name__ == "__main__":
    try:
        sync_all_files()
    except subprocess.CalledProcessError as e:
        print(f"❌ Initial sync failed: {e}")
        
    print(f"📡 Watching '{WATCH_PATH}' for changes...")
    event_handler = SCPSyncHandler()
    observer = Observer()
    observer.schedule(event_handler, path=WATCH_PATH, recursive=True)
    observer.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
        print("👋 Stopped.")
    observer.join()

