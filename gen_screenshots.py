#!/usr/bin/env python3
"""Automated screenshot generation for LOS terrain analysis app documentation."""

import os
import sys
import time
import threading
import http.server
import socketserver
from playwright.sync_api import sync_playwright, TimeoutError as PwTimeout

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(BASE_DIR, "screenshots")
os.makedirs(OUT_DIR, exist_ok=True)

# ── HTTP Server ──────────────────────────────────────────────────────
def find_free_port():
    sock = socketserver.TCPServer(("", 0), http.server.SimpleHTTPRequestHandler)
    port = sock.server_address[1]
    sock.server_close()
    return port

PORT = find_free_port()

def start_server():
    os.chdir(BASE_DIR)
    handler = http.server.SimpleHTTPRequestHandler
    with socketserver.TCPServer(("", PORT), handler) as httpd:
        httpd.serve_forever()

server_thread = threading.Thread(target=start_server, daemon=True)
server_thread.start()
time.sleep(0.5)
URL = f"http://localhost:{PORT}/index.html"


# ── Helpers ──────────────────────────────────────────────────────────
def wait_page_ready(page, timeout=120000):
    """Wait until the page is loaded, chart rendered, and terrain settled."""
    # Wait for cesium container
    page.wait_for_selector("#cesiumContainer", timeout=timeout)
    # Wait for TerrainSampler to be defined (app script loaded)
    page.wait_for_function("() => typeof TerrainSampler !== 'undefined'", timeout=timeout)
    # Wait for chart canvas
    page.wait_for_selector("#profileChart canvas", timeout=timeout)
    page.wait_for_timeout(2000)


def shot(page, name):
    path = os.path.join(OUT_DIR, f"{name}.png")
    page.screenshot(path=path, full_page=True)
    sz = os.path.getsize(path)
    print(f"  ✓ {name}.png  ({sz/1024:.0f} KB)")


def safe_goto(page, url, timeout=120000):
    try:
        page.goto(url, wait_until="load", timeout=timeout)
    except PwTimeout:
        print("  ⚠ goto timeout, continuing...")


# ── Main ─────────────────────────────────────────────────────────────
def main():
    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-gpu", "--disable-setuid-sandbox"]
        )
        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            locale="zh-CN",
            device_scale_factor=2
        )
        page = context.new_page()

        # Load page
        print("Loading page…")
        safe_goto(page, URL)
        wait_page_ready(page)
        # Give terrain extra time to load tiles and chart to fully render
        print("  waiting for terrain & chart…")
        page.wait_for_timeout(8000)

        # ═════════════════════════════════════════════════════════════
        # 1. Default interface
        # ═════════════════════════════════════════════════════════════
        print("\n[1/9] Default interface")
        shot(page, "01_default")

        # ═════════════════════════════════════════════════════════════
        # 2. Modified A/B antenna heights and frequency
        # ═════════════════════════════════════════════════════════════
        print("\n[2/9] Modified antenna heights & frequency")
        page.fill("#antA", "35")
        page.fill("#antB", "50")
        page.fill("#freqGHz", "2.4")
        # Wait for debounced update + chart render
        page.wait_for_timeout(5000)
        wait_page_ready(page)
        shot(page, "02_params")

        # ═════════════════════════════════════════════════════════════
        # 3. Air refraction (K=4/3)
        # ═════════════════════════════════════════════════════════════
        print("\n[3/9] Air refraction K=4/3")
        page.click("#kFactorToggle")
        page.wait_for_timeout(5000)
        wait_page_ready(page)
        shot(page, "03_refraction")

        # ═════════════════════════════════════════════════════════════
        # 4. Satellite imagery
        # ═════════════════════════════════════════════════════════════
        print("\n[4/9] Satellite imagery layer")
        page.evaluate("""() => {
            const vm = viewer.baseLayerPicker.viewModel;
            if (vm.imageryProviderViewModels.length > 1) {
                vm.selectedImagery = vm.imageryProviderViewModels[1];
            }
        }""")
        page.wait_for_timeout(5000)
        shot(page, "04_satellite")

        # Switch back to OSM for remaining screenshots
        page.evaluate("""() => {
            const vm = viewer.baseLayerPicker.viewModel;
            vm.selectedImagery = vm.imageryProviderViewModels[0];
        }""")
        page.wait_for_timeout(3000)

        # ═════════════════════════════════════════════════════════════
        # 5. Pick mode
        # ═════════════════════════════════════════════════════════════
        print("\n[5/9] Pick mode")
        page.click("#pickAB")
        page.wait_for_timeout(500)
        shot(page, "05_pickmode")
        page.click("#pickAB")  # deactivate

        # ═════════════════════════════════════════════════════════════
        # 6. Chromatogram enabled (no selection yet)
        # ═════════════════════════════════════════════════════════════
        print("\n[6/9] Chromatogram enabled, awaiting selection")
        page.click("#elevRampToggle")
        page.wait_for_timeout(1000)
        shot(page, "06_chromatogram_waiting")

        # ═════════════════════════════════════════════════════════════
        # 7. Rectangle selection + chromatogram active
        # ═════════════════════════════════════════════════════════════
        print("\n[7/9] Chromatogram with rectangle selection")
        page.evaluate("""() => {
            const centerLon = (111.270049 + 112.944868) / 2;
            const centerLat = (22.272179 + 22.176439) / 2;
            selectionRegion = Cesium.Rectangle.fromDegrees(
                centerLon - 0.5, centerLat - 0.3,
                centerLon + 0.5, centerLat + 0.3
            );
            viewer.scene.globe.material = heightRampMaterial;
            viewer.scene.globe.material.uniforms.uMinHeight = viewMinHeight;
            viewer.scene.globe.material.uniforms.uMaxHeight = viewMaxHeight;
            viewer.scene.globe.material.uniforms.uGamma = 1.5;
            status.spectrum = '进行中';
            updateStatusBar();
            updateViewHeightRange();
        }""")
        page.wait_for_timeout(3000)
        # Wait for sampling to finish
        try:
            page.wait_for_function(
                "() => document.getElementById('statusBar').innerText.includes('色谱')",
                timeout=60000
            )
        except PwTimeout:
            print("  ⚠ chromatogram status wait timeout")
        page.wait_for_timeout(3000)
        shot(page, "07_chromatogram_active")

        # ═════════════════════════════════════════════════════════════
        # 8. Chart hover sync
        # ═════════════════════════════════════════════════════════════
        print("\n[8/9] Chart hover sync")
        # Get chart canvas position and hover over it
        try:
            chart_canvas = page.locator("#profileChart canvas").first
            box = chart_canvas.bounding_box()
            if box:
                # Hover near the middle of the chart area (0.4 from left, 0.45 from top)
                page.mouse.move(
                    box["x"] + box["width"] * 0.4,
                    box["y"] + box["height"] * 0.45
                )
                page.wait_for_timeout(1500)
                shot(page, "08_hover_sync")
            else:
                print("  ⚠ chart canvas bounding box not found")
                shot(page, "08_hover_sync")
        except Exception as e:
            print(f"  ⚠ chart hover failed: {e}")
            shot(page, "08_hover_sync")

        # ═════════════════════════════════════════════════════════════
        # 9. Control panel close-up
        # ═════════════════════════════════════════════════════════════
        print("\n[9/9] Control panel close-up")
        try:
            cp = page.locator("#controlPanel").bounding_box()
            if cp:
                # Add some padding
                clip = {
                    "x": cp["x"] - 5, "y": cp["y"] - 5,
                    "width": cp["width"] + 10, "height": cp["height"] + 10
                }
                path = os.path.join(OUT_DIR, "09_control_panel.png")
                page.screenshot(path=path, clip=clip)
                sz = os.path.getsize(path)
                print(f"  ✓ 09_control_panel.png  ({sz/1024:.0f} KB)")
            else:
                print("  ⚠ control panel bounding box not found")
                shot(page, "09_control_panel")
        except Exception as e:
            print(f"  ⚠ control panel clip failed: {e}")
            shot(page, "09_control_panel")

        # Done
        browser.close()
        files = [f for f in os.listdir(OUT_DIR) if f.endswith(".png")]
        print(f"\n✅ Done! {len(files)} screenshots saved to: {OUT_DIR}/")


if __name__ == "__main__":
    main()
