import subprocess
import os
import time
from watchdog.observers.polling import PollingObserver
from watchdog.events import FileSystemEventHandler
try:
    from plyer import notification
    NOTIFY = True
except ImportError:
    NOTIFY = False


# === CONFIG ===
REMOTE_USER = "pi"
REMOTE_HOST = "192.168.4.1"
REMOTE_PATH = "/home/pi/sunmirror"

# Only these files will be synced to the Pi (relative to the project root)
SYNC_FILES = [
    "main.py",
    "servo_controller.py",
    "movement_generator.py",
    "sector_animation.py",
    "animation-tool/server.py",
    "animation-tool/index.html",
    "animation-tool/start-wave.json",
    "animation-tool/shutdown-wave.json",
]

# Derive the project root from this script's location
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

# Remote subdirectory mapping: files inside animation-tool/ go to a subdir on the Pi
ANIMATION_TOOL_REMOTE = "/home/pi/sunmirror"  # server.py, index.html, etc. live flat next to main.py


def remote_path_for(rel_path):
    """Return the full remote path for a relative file path."""
    # Files inside animation-tool/ are placed directly in REMOTE_PATH on the Pi
    # (server.py is at /home/pi/sunmirror/server.py, not in a subdir)
    if rel_path.startswith("animation-tool/"):
        filename = os.path.basename(rel_path)
        return f"{REMOTE_USER}@{REMOTE_HOST}:{REMOTE_PATH}/{filename}"
    return f"{REMOTE_USER}@{REMOTE_HOST}:{REMOTE_PATH}/{os.path.basename(rel_path)}"


def scp_file(abs_path, rel_path):
    """Upload a single file via SCP."""
    dest = remote_path_for(rel_path)
    try:
        subprocess.run(["scp", abs_path, dest], check=True)
        print(f"✅ Synced {rel_path} → {dest}")
        if NOTIFY:
            notification.notify(
                title="File Synced",
                message=f"{rel_path} → {REMOTE_HOST}",
                timeout=3,
            )
    except subprocess.CalledProcessError as e:
        print(f"❌ SCP failed for {rel_path}: {e}")
        if NOTIFY:
            notification.notify(
                title="Sync Failed",
                message=f"{rel_path}",
                timeout=4,
            )


def sync_all():
    """Upload all tracked files once (called at startup)."""
    print("🔄 Syncing tracked files...")
    for rel_path in SYNC_FILES:
        abs_path = os.path.join(PROJECT_ROOT, rel_path)
        if os.path.isfile(abs_path):
            print(f"[SYNC] {rel_path}")
            scp_file(abs_path, rel_path)
        else:
            print(f"[SKIP] {rel_path} — not found locally")
    print("✅ Initial sync complete")


class TrackedFileHandler(FileSystemEventHandler):
    """Only react to modifications of files in SYNC_FILES."""

    def __init__(self):
        # Build a set of absolute paths for fast lookup
        self._tracked = {
            os.path.normpath(os.path.join(PROJECT_ROOT, f)): f
            for f in SYNC_FILES
        }

    def on_modified(self, event):
        if event.is_directory:
            return
        norm = os.path.normpath(event.src_path)
        if norm in self._tracked:
            rel = self._tracked[norm]
            print(f"[MODIFIED] {rel} → syncing...")
            scp_file(norm, rel)

    # Also handle moves/renames into a tracked path
    def on_moved(self, event):
        norm = os.path.normpath(event.dest_path)
        if norm in self._tracked:
            rel = self._tracked[norm]
            print(f"[MOVED→] {rel} → syncing...")
            scp_file(norm, rel)


if __name__ == "__main__":
    try:
        sync_all()
    except subprocess.CalledProcessError as e:
        print(f"❌ Initial sync failed: {e}")

    print(f"📡 Watching {len(SYNC_FILES)} tracked files for changes...")

    event_handler = TrackedFileHandler()

    # PollingObserver watches the whole tree but requires ZERO inotify instances.
    # We filter to only our tracked files in the handler.
    observer = PollingObserver(timeout=2)
    observer.schedule(event_handler, path=PROJECT_ROOT, recursive=True)
    observer.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
        print("👋 Stopped.")
    observer.join()
