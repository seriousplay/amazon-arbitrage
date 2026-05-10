#!/usr/bin/env python3
"""健康检查脚本"""
import subprocess, sys
from pathlib import Path

def check_database():
    try:
        from app.services.storage import StorageService
        from app.config import settings
        import asyncio
        async def test():
            storage = StorageService(settings.DATABASE_URL)
            await storage.initialize()
            await storage.close()
            return True
        return asyncio.run(test())
    except:
        return False

def check_playwright():
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            browser.close()
            return True
    except:
        return False

if __name__ == "__main__":
    results = {"database": check_database(), "playwright": check_playwright()}
    print("Health Check:")
    for s, ok in results.items():
        print(f"  {'✓' if ok else '✗'} {s}: {'healthy' if ok else 'unhealthy'}")
    sys.exit(0 if all(results.values()) else 1)
