import multiprocessing
import sys


if __name__ == "__main__":
    multiprocessing.freeze_support()

    import threading
    import time
    import http.server
    import socketserver
    import os
    import subprocess
    import shutil
    import traceback
    import tempfile
    import json
    import urllib.request
    from pathlib import Path

    PORT = 8765
    FRONTEND_PORT = 8766
    LOG = Path(tempfile.gettempdir()) / "stem_app.log"
    backend_holder = {"proc": None}

    def log(msg):
        try:
            import datetime
            ts = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
            with open(LOG, "a") as f:
                f.write(f"[{ts}] {msg}\n")
                f.flush()
        except Exception:
            pass

    def get_base_dir():
        if getattr(sys, "frozen", False):
            return Path(sys._MEIPASS)
        return Path(__file__).resolve().parent

    BASE_DIR = get_base_dir()
    # Frozen: _MEIPASS/app_root holds frontend/ + backend/ (kept away from the
    # extraction root, which also holds PyInstaller-collected packages that must
    # not leak into the child interpreter's sys.path via uvicorn's cwd app-dir).
    # Dev: desktop/ has python-embed/, but frontend/ + backend/ live one level up.
    if (BASE_DIR / "app_root" / "backend").exists():
        PROJECT_ROOT = BASE_DIR / "app_root"
    elif (BASE_DIR / "backend").exists():
        PROJECT_ROOT = BASE_DIR
    else:
        PROJECT_ROOT = BASE_DIR.parent
    FRONTEND_DIR = PROJECT_ROOT / "frontend" / "dist"
    BACKEND_DIR = PROJECT_ROOT / "backend"

    def probe_backend():
        """Return True if a healthy instance of THIS app already serves PORT."""
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/api/health", timeout=1) as r:
                data = json.loads(r.read())
            return data.get("status") == "ok"
        except Exception:
            return False

    def _listening_pids(port):
        import subprocess as sp
        pids = set()
        try:
            out = sp.run(["netstat", "-ano"], capture_output=True, text=True,
                         creationflags=getattr(sp, "CREATE_NO_WINDOW", 0), timeout=5).stdout
            for line in out.splitlines():
                parts = line.split()
                if len(parts) >= 5 and parts[0] == "TCP" and parts[3] == "LISTENING":
                    if parts[1].endswith(f":{port}"):
                        try:
                            pids.add(int(parts[4]))
                        except ValueError:
                            pass
        except Exception as e:
            log(f"netstat port {port}: {e}")
        return pids

    def cleanup_stale():
        """Remove leftovers from a previous force-killed run (orphaned backend
        child / stale exe holding the frontend port) so this launch owns both."""
        if sys.platform != "win32":
            return
        me = os.getpid()
        try:
            # 1. A stale copy of this app holding the frontend port?
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{FRONTEND_PORT}/", timeout=1) as r:
                    html = r.read(4096).decode("utf-8", "replace")
                ours = "AI STEM Research Assistant" in html
            except Exception:
                ours = False
            if ours:
                for pid in _listening_pids(FRONTEND_PORT):
                    if pid != me:
                        try:
                            os.kill(pid, 9)
                            log(f"cleanup: killed stale app instance PID {pid}")
                        except Exception as e:
                            log(f"cleanup: kill {pid}: {e}")
            # 2. Orphaned backend child from a previous run? (only if it is ours)
            if probe_backend():
                for pid in _listening_pids(PORT):
                    if pid != me:
                        try:
                            os.kill(pid, 9)
                            log(f"cleanup: killed stale backend PID {pid}")
                        except Exception as e:
                            log(f"cleanup: kill {pid}: {e}")
                time.sleep(1)
        except Exception:
            log("CLEANUP ERROR:\n" + traceback.format_exc())

    def find_python():
        # Prefer the bundled embeddable Python (self-contained exe)
        embed = BASE_DIR / "python-embed" / "python.exe"
        if embed.is_file():
            return str(embed)
        # Fallback: system Python (dev mode / missing bundle)
        p = shutil.which("python") or shutil.which("python3")
        if p and os.path.isfile(p):
            return p
        import glob
        for pattern in [
            r"C:\Users\*\AppData\Local\Programs\Python\Python*\python.exe",
            r"C:\Python*\python.exe",
            r"C:\Program Files\Python*\python.exe",
        ]:
            for c in glob.glob(pattern):
                if os.path.isfile(c):
                    return c
        return None

    def start_backend():
        try:
            if probe_backend():
                log("backend: healthy instance already serving, reusing")
                return

            py = find_python()
            if not py:
                log("backend: no Python interpreter found")
                return
            log(f"backend: using Python {py}")

            env = os.environ.copy()
            project_root = str(PROJECT_ROOT)
            env["PYTHONPATH"] = project_root

            # Persistent storage outside the temp extraction dir
            import platform
            if platform.system() == "Windows":
                data_dir = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "STEMResearchAssistant" / "storage"
            else:
                data_dir = Path.home() / ".stem-research-assistant" / "storage"
            data_dir.mkdir(parents=True, exist_ok=True)
            env["DATABASE_URL"] = f"sqlite:///{data_dir / 'app.db'}"
            env["UPLOAD_DIR"] = str(data_dir / "uploads")
            log(f"backend: storage at {data_dir}")

            out_log = Path(tempfile.gettempdir()) / "stem_backend.log"
            out_f = open(out_log, "w")

            proc = subprocess.Popen(
                [py, "-m", "uvicorn", "backend.app.main:app",
                 "--host", "127.0.0.1", "--port", str(PORT),
                 "--log-level", "warning"],
                cwd=project_root,
                env=env,
                stdout=out_f,
                stderr=out_f,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            backend_holder["proc"] = proc
            log(f"backend: subprocess started PID={proc.pid}")
            time.sleep(3)
            rc = proc.poll()
            if rc is not None:
                out_f.close()
                err_text = out_log.read_text(errors="replace") if out_log.exists() else "(empty)"
                log(f"backend: process died code={rc}, output:\n{err_text}")
            else:
                proc.wait()
                log(f"backend: subprocess exited code={proc.returncode}")
        except Exception:
            log("BACKEND ERROR:\n" + traceback.format_exc())

    def start_frontend_server():
        try:
            os.chdir(FRONTEND_DIR)
            log(f"frontend: serving {FRONTEND_DIR}")
            handler = http.server.SimpleHTTPRequestHandler
            with socketserver.TCPServer(("", FRONTEND_PORT), handler) as httpd:
                httpd.serve_forever()
        except Exception:
            log("FRONTEND ERROR:\n" + traceback.format_exc())

    def wait_for_backend():
        for i in range(60):
            if probe_backend():
                log(f"backend: healthy after {i * 0.5:.1f}s")
                return True
            time.sleep(0.5)
        log("backend: health check timed out")
        return False

    def stop_backend():
        proc = backend_holder.get("proc")
        if proc is None or proc.poll() is not None:
            return
        try:
            proc.terminate()
            proc.wait(timeout=5)
            log("backend: terminated")
        except Exception:
            try:
                proc.kill()
                proc.wait(timeout=5)
                log("backend: killed")
            except Exception as e:
                log(f"backend: stop failed: {e}")

    try:
        log("=" * 40)
        log(f"APP START frozen={getattr(sys, 'frozen', False)}")
        log(f"BASE_DIR={BASE_DIR} PROJECT_ROOT={PROJECT_ROOT}")
        log(f"FRONTEND exists={FRONTEND_DIR.exists()} BACKEND exists={BACKEND_DIR.exists()}")

        cleanup_stale()

        t1 = threading.Thread(target=start_backend, daemon=True)
        t1.start()

        if not wait_for_backend():
            log("exiting: backend failed")
            sys.exit(1)

        t2 = threading.Thread(target=start_frontend_server, daemon=True)
        t2.start()
        time.sleep(1)

        import webview
        log("creating webview window")
        webview.create_window(
            "STEM Research Assistant",
            f"http://127.0.0.1:{FRONTEND_PORT}",
            width=1400,
            height=900,
            min_size=(1024, 700),
        )
        webview.start()
    except Exception:
        log("MAIN ERROR:\n" + traceback.format_exc())
        raise
    finally:
        stop_backend()
