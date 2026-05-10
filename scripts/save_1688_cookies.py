#!/usr/bin/env python3
"""
1688 Cookie 获取脚本
用法: python scripts/save_1688_cookies.py

1. 启动 Chromium 浏览器并打开 1688 登录页
2. 在浏览器中扫码/输入账号密码登录
3. 登录成功后按 Enter，脚本自动保存 cookies
"""

import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
COOKIE_FILE = PROJECT_ROOT / "data" / "cookies" / "1688_cookies.json"

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("请先安装 Playwright: pip install playwright && playwright install chromium")
    sys.exit(1)


def main():
    COOKIE_FILE.parent.mkdir(parents=True, exist_ok=True)

    print("=" * 55)
    print("  1688 Cookie 获取工具")
    print("=" * 55)
    print()
    print("即将打开浏览器，请在浏览器窗口中登录 1688。")
    print("登录成功后回到此处按 Enter，cookies 将自动保存。")
    print()
    input("按 Enter 开始...")

    with sync_playwright() as p:
        # 关键：禁用第三方 Cookie 阻止，1688 登录跨 taobao.com
        browser = p.chromium.launch(
            headless=False,
            args=[
                "--disable-features=ThirdPartyStoragePartitioning",
                "--disable-features=CookieDomainReject",
                "--disable-blink-features=StorageAccessAPI",
            ],
        )
        context = browser.new_context(
            viewport={"width": 1280, "height": 800},
            locale="zh-CN",
            ignore_https_errors=True,
            # 关键：接受所有第三方 cookie
            storage_state=None,
        )
        # 授予所有权限
        context.grant_permissions([], origin="https://www.1688.com")
        context.grant_permissions([], origin="https://login.1688.com")
        context.grant_permissions([], origin="https://login.taobao.com")
        context.grant_permissions([], origin="https://www.taobao.com")

        page = context.new_page()

        print("正在打开 1688 登录页...")
        page.goto(
            "https://login.1688.com/member/signin.htm",
            wait_until="domcontentloaded",
            timeout=60000,
        )
        print()
        print("请在浏览器中完成登录（扫码或账号密码均可）。")
        print("登录成功后（页面跳转到 1688 首页），回到此处按 Enter...")
        input()

        # 等 3 秒让所有 cookie 落地
        import time
        time.sleep(3)

        # 保存所有 cookies（1688 登录链跨 taobao.com，需要全部保存）
        all_cookies = context.cookies()
        target_domains = [c for c in all_cookies if any(
            d in c.get("domain", "") for d in [".1688.com", ".taobao.com", ".tmall.com"]
        )]

        saved = target_domains if target_domains else all_cookies
        with open(COOKIE_FILE, "w", encoding="utf-8") as f:
            json.dump(saved, f, ensure_ascii=False, indent=2)

        print()
        print(f"✓ 已保存 {len(saved)} 条 cookies → {COOKIE_FILE}")
        print(f"  域名分布: {set(c.get('domain','?') for c in saved)}")
        print()
        print("现在可以重启服务，匹配器将使用真实 1688 搜索。")

        browser.close()


if __name__ == "__main__":
    main()
