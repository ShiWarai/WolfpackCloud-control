#!/usr/bin/env python3
"""Смок: Keycloak login → dashboard → страница оркестрации (Selenium)."""

from __future__ import annotations

import os
import sys

from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

SKIP_ENV = "WPC_E2E_SKIP"
BASE_ENV = "WPC_UI_BASE_URL"
USER_ENV = "KEYCLOAK_TEST_USER"
PASS_ENV = "KEYCLOAK_TEST_PASSWORD"


def _env_credential(*names: str) -> str:
    for name in names:
        value = (os.environ.get(name) or "").strip()
        if value:
            return value
    return ""


def main() -> int:
    if os.environ.get(SKIP_ENV):
        print(f"{SKIP_ENV} set — skipping E2E.")
        return 0

    base = _env_credential(BASE_ENV, "WPC_STAGING_UI_BASE_URL").rstrip("/")
    user = _env_credential(USER_ENV, "KEYCLOAK_USERNAME", "LOADTEST_USERNAME")
    password = _env_credential(PASS_ENV, "KEYCLOAK_PASSWORD", "LOADTEST_PASSWORD")

    if not base or not user or not password:
        print(
            f"Missing env: need {BASE_ENV} (or WPC_STAGING_UI_BASE_URL), "
            f"{USER_ENV} (or KEYCLOAK_USERNAME / LOADTEST_USERNAME), "
            f"{PASS_ENV} (or KEYCLOAK_PASSWORD / LOADTEST_PASSWORD); "
            f"staging defaults: loadtest-admin from Secret loadtest-credentials. "
            f"Or set {SKIP_ENV} to skip.",
            file=sys.stderr,
        )
        return 2

    opts = Options()
    if os.environ.get("HEADLESS", "1").strip() != "0":
        opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--window-size=1400,900")

    driver = webdriver.Chrome(options=opts)
    wait = WebDriverWait(driver, 45)

    try:
        driver.get(f"{base}/login")

        login_btn = wait.until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, '[data-testid="login-keycloak"]'))
        )
        login_btn.click()

        # Keycloak form (типовые id)
        user_el = wait.until(EC.visibility_of_element_located((By.ID, "username")))
        user_el.clear()
        user_el.send_keys(user)
        pwd_el = driver.find_element(By.ID, "password")
        pwd_el.clear()
        pwd_el.send_keys(password)

        submit = driver.find_element(By.ID, "kc-login")
        submit.click()

        wait.until(EC.url_contains("/dashboard"))

        nav = wait.until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, '[data-testid="nav-orchestration"]'))
        )
        nav.click()

        wait.until(
            EC.visibility_of_element_located(
                (By.CSS_SELECTOR, '[data-testid="orchestration-heading"]')
            )
        )
        print("E2E smoke OK: orchestration heading visible.")
        return 0
    except TimeoutException as e:
        print(f"E2E timeout: {e}", file=sys.stderr)
        driver.save_screenshot("/tmp/wpc-e2e-failure.png")
        print("Screenshot: /tmp/wpc-e2e-failure.png", file=sys.stderr)
        return 1
    finally:
        driver.quit()


if __name__ == "__main__":
    sys.exit(main())
