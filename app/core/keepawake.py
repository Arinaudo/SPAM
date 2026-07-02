"""
Empeche la mise en veille du PC pendant un envoi (cross-platform).

- Windows : SetThreadExecutionState (le systeme reste actif, l'ecran peut
  s'eteindre).
- macOS   : processus 'caffeinate' (lie au PID de l'app, donc pas d'orphelin).
- Linux   : best effort (sans effet si rien de dispo).

Usage :
    ka = KeepAwake()
    ka.start()   # au debut de l'envoi
    ka.stop()    # a la fin / a l'arret
"""

import os
import sys
import subprocess

# Constantes Windows
_ES_CONTINUOUS = 0x80000000
_ES_SYSTEM_REQUIRED = 0x00000001


class KeepAwake:
    def __init__(self):
        self._active = False
        self._proc = None  # caffeinate (macOS)

    def start(self):
        if self._active:
            return
        try:
            if sys.platform.startswith("win"):
                import ctypes
                ctypes.windll.kernel32.SetThreadExecutionState(
                    _ES_CONTINUOUS | _ES_SYSTEM_REQUIRED)
                self._active = True
            elif sys.platform == "darwin":
                # -i : empeche la veille systeme ; -w : s'arrete avec l'app
                self._proc = subprocess.Popen(
                    ["caffeinate", "-i", "-w", str(os.getpid())])
                self._active = True
            else:
                self._active = False
        except Exception:
            self._active = False

    def stop(self):
        try:
            if sys.platform.startswith("win"):
                import ctypes
                ctypes.windll.kernel32.SetThreadExecutionState(_ES_CONTINUOUS)
            elif sys.platform == "darwin" and self._proc:
                self._proc.terminate()
                self._proc = None
        except Exception:
            pass
        self._active = False

    def is_active(self) -> bool:
        return self._active
