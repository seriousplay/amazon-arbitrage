#!/usr/bin/env python3
"""数据备份"""
import shutil, sys
from datetime import datetime
from pathlib import Path
src = Path("data/arbitrage.db")
if src.exists():
    backup_dir = Path("backups")
    backup_dir.mkdir(exist_ok=True)
    dst = backup_dir / f"arbitrage-{datetime.now():%Y%m%d_%H%M%S}.db"
    shutil.copy2(src, dst)
    print(f"✓ Backup: {dst}")
else:
    print("No database to backup")
