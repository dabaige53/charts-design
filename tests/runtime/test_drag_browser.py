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
            card = page.locator("[data-component-id=total] .grid-stack-item-content")
            target = page.locator("[data-component-id=load] .grid-stack-item-content")
            start, end = card.bounding_box(), target.bounding_box()
            assert start is not None and end is not None
            assert page.locator(".layout-handle").count() == 0
            # Any non-control point of the card grabs it: the centre, or just inside the border.
            offset = 6 if grab == "button-edge" else start["width"] / 2
            x, y = start["x"] + offset, start["y"] + start["height"] / 2
            dx, dy = end["x"] - start["x"], end["y"] - start["y"]
            assert page.evaluate(
                "([x,y])=>!!document.elementFromPoint(x,y).closest('[data-component-id=total].is-draggable')",
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
            assert page.locator(".is-draggable").count() == 0
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            assert not errors, errors
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_second_drag_survives_inflight_layout_save(tmp_path):
    """A slow save must not rebuild the grid under a drag that is already in progress."""
    service = Service(tmp_path / "state")
    service.store.create("drag", "Drag", executive_document())
    call = service.call
    first_save_started = threading.Event()
    release_first_save = threading.Event()

    def delayed_call(tool, args):
        if tool == "dashboard_patch" and not first_save_started.is_set():
            first_save_started.set()
            if not release_first_save.wait(timeout=10):
                raise TimeoutError("First layout save was not released")
        return call(tool, args)

    service.call = delayed_call
    server = RuntimeHTTPServer(service, 0, "drag-test")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 1100})
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(f"http://127.0.0.1:{server.server_port}/?board=drag#drag-test")
            page.get_by_role("button", name="编辑", exact=True).click()

            def grab(source):
                box = page.locator(f"[data-component-id={source}] .grid-stack-item-content").bounding_box()
                assert box is not None, f"Cannot find the bounds for {source}"
                page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
                page.mouse.down()

            def drop_on(target):
                box = page.locator(f"[data-component-id={target}] .grid-stack-item-content").bounding_box()
                assert box is not None, f"Cannot find the bounds for {target}"
                page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2, steps=15)
                page.mouse.up()

            grab("total")
            drop_on("load")
            assert first_save_started.wait(timeout=10), "First layout save did not start"
            grab("trend")
            page.mouse.move(700, 600, steps=10)
            page.locator(".grid-stack-dragging").wait_for()
            release_first_save.set()
            page.wait_for_function("document.querySelector('#notice').textContent.includes('v2')")
            assert page.locator(".grid-stack-dragging").count() == 1
            drop_on("goal")
            page.wait_for_function("document.querySelector('#notice').textContent.includes('v3')")
            shown = page.eval_on_selector_all(
                ".grid-stack-item",
                "items=>items.map(e=>[e.dataset.componentId,+(e.getAttribute('gs-x')||0),+(e.getAttribute('gs-y')||0)])",
            )
            stored = service.store.get("drag")["manifest"]["layout"]["desktop"]
            assert sorted(map(tuple, shown)) == sorted((n["id"], n["x"], n["y"]) for n in stored)
            assert page.locator(".is-draggable").count() == len(stored)
            assert not errors, errors
            browser.close()
    finally:
        release_first_save.set()
        server.shutdown()
        server.server_close()
        thread.join()
