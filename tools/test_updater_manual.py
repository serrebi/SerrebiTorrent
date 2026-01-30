"""
Manual test for hidden CMD window during update.

This script creates a visible test app window that you can use to trigger
an update and verify no CMD window appears during the update process.
"""
import os
import sys
import tempfile
import tkinter as tk
from pathlib import Path
import zipfile
import shutil


class UpdateTesterApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("SerrebiTorrent Update Tester")
        self.root.geometry("600x400")
        
        self.test_dir = None
        self.install_dir = None
        
        # Status label
        self.status_label = tk.Label(
            self.root,
            text="Click 'Setup Test Environment' to begin",
            wraplength=550,
            justify=tk.LEFT,
            font=("Arial", 10)
        )
        self.status_label.pack(pady=20, padx=20)
        
        # Buttons
        tk.Button(
            self.root,
            text="1. Setup Test Environment",
            command=self.setup_test,
            width=30,
            height=2
        ).pack(pady=10)
        
        tk.Button(
            self.root,
            text="2. Trigger Update (Watch for CMD window!)",
            command=self.trigger_update,
            width=30,
            height=2
        ).pack(pady=10)
        
        tk.Button(
            self.root,
            text="3. Check Results",
            command=self.check_results,
            width=30,
            height=2
        ).pack(pady=10)
        
        tk.Button(
            self.root,
            text="Cleanup",
            command=self.cleanup,
            width=30
        ).pack(pady=10)
        
    def update_status(self, text):
        self.status_label.config(text=text)
        self.root.update()
        
    def setup_test(self):
        self.update_status("Setting up test environment...")
        
        # Create test directory
        self.test_dir = Path(tempfile.mkdtemp(prefix="serrebi_update_test_"))
        self.install_dir = self.test_dir / "SerrebiTorrent"
        self.install_dir.mkdir()
        
        # Create mock v1.0.0 installation
        exe_path = self.install_dir / "SerrebiTorrent.exe"
        exe_path.write_text("Mock v1.0.0\n")
        
        # Copy real update helper
        script_root = Path(__file__).parent.parent
        helper_src = script_root / "update_helper.bat"
        helper_dst = self.install_dir / "update_helper.bat"
        shutil.copy2(helper_src, helper_dst)
        
        # Create some dummy files
        (self.install_dir / "dummy1.dll").write_text("DLL 1")
        (self.install_dir / "dummy2.dll").write_text("DLL 2")
        
        # Create staging folder with v2.0.0
        staging_root = self.test_dir / "SerrebiTorrent_Update_20260130_140000"
        staging_dir = staging_root / "SerrebiTorrent"
        staging_dir.mkdir(parents=True)
        
        (staging_dir / "SerrebiTorrent.exe").write_text("Mock v2.0.0\n")
        (staging_dir / "dummy1.dll").write_text("DLL 1 updated")
        (staging_dir / "dummy2.dll").write_text("DLL 2 updated")
        (staging_dir / "dummy3.dll").write_text("DLL 3 new")
        shutil.copy2(helper_src, staging_dir / "update_helper.bat")
        
        # Copy helper to staging root
        shutil.copy2(helper_src, staging_root / "update_helper.bat")
        
        self.staging_root = staging_root
        self.staging_dir = staging_dir
        
        self.update_status(
            f"✓ Test environment ready!\n\n"
            f"Install dir: {self.install_dir}\n"
            f"Staging dir: {self.staging_dir}\n\n"
            f"Click 'Trigger Update' and WATCH CAREFULLY for any CMD windows.\n"
            f"You should NOT see any CMD windows flash or appear!"
        )
        
    def trigger_update(self):
        if not self.install_dir:
            self.update_status("❌ Please setup test environment first!")
            return
            
        self.update_status(
            "🚀 Triggering update...\n\n"
            "WATCH YOUR SCREEN!\n"
            "You should NOT see any black CMD windows appear.\n\n"
            "The update will run in the background..."
        )
        self.root.update()
        
        import subprocess
        
        # Use the same launch method as the real updater
        helper_args = f'"{self.staging_root / "update_helper.bat"}" 999999 "{self.install_dir}" "{self.staging_dir}" "SerrebiTorrent.exe"'
        helper_cmd = [
            "powershell",
            "-WindowStyle", "Hidden",
            "-NoProfile",
            "-Command",
            f"Start-Process -FilePath cmd.exe -ArgumentList '/c', '{helper_args}' -WindowStyle Hidden -WorkingDirectory '{self.test_dir}'"
        ]
        
        # Set environment for immediate cleanup
        env = os.environ.copy()
        env["SERREBITORRENT_KEEP_BACKUPS"] = "0"
        
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0  # SW_HIDE
        
        flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
        
        proc = subprocess.Popen(
            helper_cmd,
            creationflags=flags,
            startupinfo=startupinfo,
            env=env
        )
        
        self.update_status(
            f"✓ Update process started (PID: {proc.pid})\n\n"
            f"Did you see any CMD window? (You shouldn't have!)\n\n"
            f"Wait 5 seconds, then click 'Check Results'..."
        )
        
    def check_results(self):
        if not self.install_dir:
            self.update_status("❌ Please setup test environment first!")
            return
            
        exe_path = self.install_dir / "SerrebiTorrent.exe"
        if not exe_path.exists():
            self.update_status("❌ Executable not found! Update may have failed.")
            return
            
        content = exe_path.read_text()
        
        # Check for backups
        backup_dirs = list(self.test_dir.glob("SerrebiTorrent_backup_*"))
        staging_exists = self.staging_root.exists()
        
        result = f"✓ Update Results:\n\n"
        result += f"Version: {'v2.0.0' if 'v2.0.0' in content else 'v1.0.0 (NOT UPDATED)'}\n"
        result += f"Backup folders: {len(backup_dirs)}\n"
        result += f"Staging folder exists: {staging_exists}\n\n"
        
        if "v2.0.0" in content and len(backup_dirs) == 0 and not staging_exists:
            result += "✅ PERFECT! Update succeeded and cleanup worked!\n"
            result += "And you didn't see any CMD windows, right? ✅"
        elif "v2.0.0" in content:
            result += "⚠ Update succeeded but cleanup may be delayed.\n"
            result += "(Backups cleaned after 5-minute grace period)"
        else:
            result += "❌ Update failed!"
            
        self.update_status(result)
        
    def cleanup(self):
        if self.test_dir and self.test_dir.exists():
            try:
                shutil.rmtree(self.test_dir)
                self.update_status("✓ Test environment cleaned up!")
                self.test_dir = None
                self.install_dir = None
            except Exception as e:
                self.update_status(f"⚠ Cleanup error: {e}")
        else:
            self.update_status("Nothing to clean up.")
            
    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    app = UpdateTesterApp()
    app.run()
