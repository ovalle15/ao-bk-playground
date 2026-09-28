"""Browser journeys through Nginx, Express, and the local NASA stub."""

import os
import re
import socket
import time
from urllib.error import URLError
from urllib.request import urlopen

import pytest


if os.environ.get("RUN_E2E_TESTS") != "1":
    pytest.skip("requires docker-compose.test.yml", allow_module_level=True)

from playwright.sync_api import expect, sync_playwright


APP_URL = os.environ.get("APP_URL", "http://app").rstrip("/")
BROWSER_URL = "http://{}".format(socket.gethostbyname("app"))


def step(description):
    print("    → " + description, flush=True)


@pytest.fixture(scope="session")
def browser():
    # Wait for the complete app -> API -> NASA stub path before opening a page.
    for _ in range(60):
        try:
            with urlopen(APP_URL + "/api/nasaimage?date=2024-01-01", timeout=2) as response:
                if response.status == 200:
                    break
        except URLError:
            pass
        time.sleep(0.5)
    else:
        pytest.fail("Containerized app did not become ready")

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            executable_path="/usr/bin/chromium",
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        try:
            yield browser
        finally:
            browser.close()


@pytest.fixture
def page(browser):
    context = browser.new_context(viewport={"width": 1280, "height": 900})
    page = context.new_page()
    try:
        yield page
    finally:
        context.close()


def test_homepage_renders_apod_image_metadata_and_high_resolution_link(page):
    step("Open the homepage and wait for its APOD image")
    page.goto(BROWSER_URL)

    expect(page.get_by_role("heading", name="A galaxy")).to_be_visible()
    step("Check loaded image pixels, date, credit, explanation, and full-size link")
    image = page.locator("#nasa-image")
    expect(image).to_be_visible()
    assert image.evaluate("image => image.naturalWidth") == 1
    expect(page.locator("#nasa-video")).to_be_hidden()
    expect(page.locator("#apod-date")).to_have_value("2024-01-01")
    expect(page.locator("#image-attribution")).to_have_text("Credit: A. Astronomer")
    expect(page.locator("#image-explanation")).to_have_text("Spiral arms")
    expect(page.locator("#high-res-link")).to_have_attribute("href", re.compile(r"/media/large\.png$"))


def test_date_search_switches_from_image_to_embedded_video(page):
    step("Open the homepage and confirm the initial image is visible")
    page.goto(BROWSER_URL)
    expect(page.locator("#nasa-image")).to_be_visible()

    step("Choose January 2, 2024 and submit the date search")
    page.locator("#apod-date").fill("2024-01-02")
    page.get_by_role("button", name="View image").click()

    step("Check the embedded video loads and the image is replaced")
    expect(page.get_by_role("heading", name="A launch")).to_be_visible()
    expect(page.locator("#nasa-video")).to_be_visible()
    expect(page.frame_locator("#nasa-video").get_by_role("heading", name="Launch footage")).to_be_visible()
    expect(page.locator("#nasa-image")).to_be_hidden()
    expect(page.locator("#high-res-link")).to_have_attribute("href", re.compile(r"/media/video\.html$"))


def test_retry_recovers_after_nasa_api_failure(page):
    step("Open the homepage and confirm the initial image is visible")
    page.goto(BROWSER_URL)
    expect(page.locator("#nasa-image")).to_be_visible()

    step("Search January 4, 2024; the stub makes this request fail once")
    page.locator("#apod-date").fill("2024-01-04")
    page.get_by_role("button", name="View image").click()

    step("Check the error message and retry control are visible")
    expect(page.locator("#image-error")).to_contain_text("Request failed with status 502")
    expect(page.locator("#nasa-image")).to_be_hidden()
    expect(page.locator("#retry-image")).to_be_visible()

    step("Click Refresh image and check that the image appears and error clears")
    page.get_by_role("button", name="Refresh image").click()

    expect(page.locator("#nasa-image")).to_be_visible()
    expect(page.locator("#image-error")).to_be_empty()
    expect(page.locator("#apod-date")).to_have_value("2024-01-04")
