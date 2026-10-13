"""Exercise real pointer grabs instead of moving GridStack nodes through its API."""

import threading

import pytest
from playwright.sync_api import sync_playwright

from dashboard_runtime.demo import executive_document
from dashboard_runtime.http_server import RuntimeHTTPServer
from dashboard_runtime.service import Service


@pytest.mark.parametrize("grab", ["icon-center", "button-edge", "touch-center"])
def test_drag_handle_moves_and_saves_without_resizing(tmp_path, grab):
    service = Service(tmp_path / "state")
    before = service.store.create("drag", "Drag", executive_document())
    server = RuntimeHTTPServer(service, 0, "drag-test")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    touch = grab == "touch-center"
    breakpoint = "mobile" if touch else "desktop"
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(
                viewport={"width": 390 if touch else 1440, "height": 1100},
                has_touch=touch,
                is_mobile=touch,
            )
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(f"http://127.0.0.1:{server.server_port}/?board=drag#drag-test")
            page.get_by_role("button", name="编辑", exact=True).click()
            handle = page.locator("[data-component-id=total] .layout-handle")
            target = page.locator("[data-component-id=load] .layout-handle")
            start, end = handle.bounding_box(), target.bounding_box()
            assert start is not None and end is not None
            assert start["width"] >= 44 and start["height"] >= 44
            offset = 3 if grab == "button-edge" else start["width"] / 2
            x, y = start["x"] + offset, start["y"] + start["height"] / 2
            dx, dy = end["x"] - start["x"], end["y"] - start["y"]
            assert page.evaluate(
                "([x,y])=>document.elementFromPoint(x,y).classList.contains('layout-handle')",
                [x, y],
            )
            if touch:
                session = page.context.new_cdp_session(page)
                session.send("Input.dispatchTouchEvent", {
                    "type": "touchStart", "touchPoints": [{"x": x, "y": y}],
                })
                for step in range(1, 21):
                    session.send("Input.dispatchTouchEvent", {
                        "type": "touchMove",
                        "touchPoints": [{"x": x + dx * step / 20, "y": y + dy * step / 20}],
                    })
                session.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})
            else:
                page.mouse.move(x, y)
                page.mouse.down()
                page.mouse.move(x + dx, y + dy, steps=25)
                page.mouse.up()
            page.wait_for_function("document.querySelector('#notice').textContent.includes('v2')")
            after = service.store.get("drag")
            old_layout = before["manifest"]["layout"][breakpoint]
            new_layout = after["manifest"]["layout"][breakpoint]
            assert {n["id"]: (n["x"], n["y"]) for n in new_layout} != {
                n["id"]: (n["x"], n["y"]) for n in old_layout
            }
            assert {n["id"]: (n["w"], n["h"]) for n in new_layout} == {
                n["id"]: (n["w"], n["h"]) for n in old_layout
            }
            assert after["manifest"]["components"] == before["manifest"]["components"]
            if not touch:
                page.get_by_role("button", name="撤销", exact=True).click()
                page.wait_for_function("document.querySelector('#notice').textContent.includes('v3')")
                assert service.store.get("drag")["manifest"]["layout"][breakpoint] == old_layout
            page.reload()
            page.locator("[data-component-id=total] canvas, [data-component-id=trend] canvas").first.wait_for()
            assert page.locator(".layout-handle").count() == 0
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            assert not errors, errors
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
