"""Record the bundled scene demonstrations using Chromium's native headless recorder.

Export BENCHMARK_EXAMPLES to JSON, then pass its path with --scenes. No credentials
are needed; recordings and MP4 conversions stay in the requested output directory.
"""

import argparse
import json
import subprocess
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--scenes", type=Path, required=True)
parser.add_argument("--output", type=Path, default=Path("/tmp/cad-videos"))
parser.add_argument("--url", default="http://localhost:5173")
parser.add_argument("--only")
args = parser.parse_args()
args.output.mkdir(parents=True, exist_ok=True)
scenes = json.loads(args.scenes.read_text())
with sync_playwright() as p:
    browser = p.chromium.launch(
        executable_path="/usr/bin/chromium", headless=True, args=["--no-sandbox"]
    )
    context = browser.new_context(
        viewport={"width": 1600, "height": 1000},
        record_video_dir=str(args.output / "raw"),
        record_video_size={"width": 1600, "height": 1000},
    )
    for scene in scenes:
        name = scene["name"]
        if args.only and name != args.only:
            continue
        print("Preparing", name, flush=True)
        start = time.monotonic()
        page = context.new_page()
        video = page.video
        data = {"id": "recording", "name": name, "body": scene["body"], "editedAt": 0}
        page.add_init_script(
            """if(location.hostname==='localhost'){
            localStorage.setItem('cad-detect-free-motions.files.v2',JSON.stringify([__SCENE__]));
            localStorage.setItem('cad-detect-free-motions.active.v1','recording');
            localStorage.setItem('cad-detect-free-motions.split.v1','32');
        }""".replace("__SCENE__", json.dumps(data))
        )
        page.goto(args.url)
        page.locator(".viewer strong").filter(has_text="numerical").wait_for(
            timeout=120000
        )
        page.wait_for_timeout(500)
        trim = max(0, time.monotonic() - start - 1)

        def caption(text, page=page):
            page.evaluate(
                """text=>{let el=document.getElementById('recording-caption');if(!el){el=document.createElement('div');el.id='recording-caption';el.style.cssText='position:fixed;left:14px;bottom:40px;width:460px;padding:12px;background:rgba(255,255,255,.95);border:1px solid #d3d5d9;border-radius:5px;font:14px system-ui;color:#333;z-index:80;pointer-events:none';document.body.append(el)}el.textContent=text}""",
                text,
            )

        def choose(label, option, page=page):
            page.get_by_role("button", name=label, exact=True).click()
            page.get_by_role("listbox", name=label, exact=True).get_by_role(
                "option", name=option, exact=True
            ).click()

        caption(name + " — exploring the current connected component")
        panel = page.locator(".exploration-panel")
        panel.locator("summary").first.click()
        page.wait_for_timeout(1200)
        panel.get_by_role("button", name="Explore", exact=True).click()
        page.wait_for_function(
            """()=>{const text=document.querySelector('.exploration-panel').textContent;return text.includes('frontier_exhausted')||text.includes('budget_limit')}""",
            timeout=180000,
        )
        print("Exploration finished", name, flush=True)
        panel.get_by_role("button", name="Roadmap (3D projection)", exact=True).click()
        page.wait_for_timeout(1500)
        build = panel.get_by_role("button", name="Sample & build tour", exact=True)
        isolated = build.is_disabled()
        if isolated:
            caption(
                name
                + " — this connected component is an isolated configuration; no continuous tour exists."
            )
            page.wait_for_timeout(2500)
            panel.locator("summary").first.click()
            caption(
                "The solid mechanism stays locked. The translucent drag preview shows constraint violations, not feasible motion."
            )
            joint = page.locator('[data-point="r1:b"]')
            box = joint.bounding_box()
            x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
            page.mouse.move(x, y)
            page.mouse.down()
            page.mouse.move(x + 20, y - 75, steps=25)
            page.wait_for_timeout(2500)
            page.mouse.up()
            caption(
                name
                + " — one feasible configuration in the explored connected component."
            )
            page.wait_for_timeout(1500)
        else:
            caption(
                "Choosing well-spaced configurations and preparing a closed tour along the traced graph paths."
            )
            build.click()
            panel.get_by_role("button", name="Play tour", exact=True).wait_for(
                timeout=240000
            )
            print("Tour prepared", name, flush=True)
            choose("Playback speed", "6×")
            page.wait_for_timeout(1000)
            panel.get_by_role("button", name="Play tour", exact=True).click()
            panel.locator("summary").first.click()
            page.get_by_role("button", name="Fit motion", exact=True).click()
            if "rings" not in name:
                page.get_by_role("button", name="⌖ Orbits", exact=True).click()
            else:
                tangents = page.get_by_role("button", name="∂² Tangents", exact=True)
                if tangents.get_attribute("aria-pressed") == "true":
                    tangents.click()
            caption(
                name
                + " — closed tour playback at 6×. Python prepared the feasible poses; the browser plays cached frames."
            )
            if "rings" in name:
                caption(
                    "Concentric rings — 2 DOFs: bar rotation and inner-ring rotation. Outer ring fixed. Closed configuration-space tour at 6×."
                )
            page.wait_for_timeout(15000)
        page.screenshot(path=str(args.output / (Path(name).stem + ".png")))
        duration = time.monotonic() - start - trim
        page.close()
        raw = Path(video.path())
        target = args.output / (Path(name).stem + ".mp4")
        subprocess.run(
            [
                "ffmpeg",
                "-nostdin",
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-ss",
                str(trim),
                "-i",
                str(raw),
                "-t",
                str(duration),
                "-c:v",
                "libx264",
                "-preset",
                "fast",
                "-crf",
                "24",
                "-pix_fmt",
                "yuv420p",
                "-r",
                "30",
                "-threads",
                "2",
                "-movflags",
                "+faststart",
                str(target),
            ],
            check=True,
        )
        print("Saved", target, "bytes", target.stat().st_size, flush=True)
    context.close()
    browser.close()
