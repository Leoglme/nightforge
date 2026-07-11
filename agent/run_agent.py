"""
PyInstaller entry point for the NightForge agent sidecar.

PyInstaller cannot run ``nightforge_agent/__main__.py`` with relative imports — use this
script as the onefile bundle entry instead of ``python -m nightforge_agent``.
"""
from nightforge_agent.__main__ import main

if __name__ == "__main__":
    main()
