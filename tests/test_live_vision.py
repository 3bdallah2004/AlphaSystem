"""Live check of the vision path against the real providers.

Skipped by default: it needs .env credentials and spends real quota. Run it with

    ALPHA_LIVE=1 python -m pytest tests/test_live_vision.py -q

Set ALPHA_LIVE_PROVIDER=3 to pin one provider (its index in LLM_PROVIDERS); the others are set
aside for the run.
"""
import base64
import io
import json
import os
import subprocess

import pytest
from PIL import Image, ImageDraw, ImageFont

import extract
import llm
import vision

live = pytest.mark.skipif(os.getenv("ALPHA_LIVE") != "1", reason="set ALPHA_LIVE=1 to run")


@pytest.fixture()
def pin_provider(monkeypatch):
    index = os.getenv("ALPHA_LIVE_PROVIDER")
    if index:
        for provider in llm.PROVIDERS:
            if provider["index"] != index:
                llm.set_aside(provider["index"])
    yield index
    llm.clear_exhausted()


def _scene_png():
    """A synthetic scene with a unique case number, so the answer is checkable."""
    img = Image.new("RGB", (900, 600), (245, 245, 242))
    d = ImageDraw.Draw(img)
    d.text((40, 40), "ALPHA TEST SCENE", fill=(20, 20, 20), font=ImageFont.load_default(size=48))
    d.text((40, 110), "CASE ALP-LIVE-1", fill=(120, 20, 20), font=ImageFont.load_default(size=30))
    d.rectangle([120, 330, 620, 470], fill=(190, 30, 30), outline=(60, 10, 10), width=4)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


@live
def test_live_image_description_names_the_visible_text(pin_provider):
    uri = "data:image/png;base64," + base64.b64encode(_scene_png()).decode()
    text, error = vision.describe_image("en", uri)
    assert error is None, error
    assert text.strip()
    assert "LIVE" in text.upper()


@live
def test_live_video_yields_frames_and_descriptions(pin_provider, database, case, tmp_path):
    import imageio_ffmpeg

    clip = tmp_path / "clip.mp4"
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-hide_banner", "-loglevel", "error",
                    "-f", "lavfi", "-i", "testsrc=duration=2:size=320x240:rate=10",
                    "-pix_fmt", "yuv420p", str(clip)], check=False, capture_output=True)
    if not clip.exists():
        pytest.skip("ffmpeg could not produce a test clip")

    class Uploaded:
        name, type = "clip.mp4", "video/mp4"

        def getvalue(self):
            return clip.read_bytes()

    import attachments

    attachments.save(case, Uploaded())
    row = database.list_attachments(case)[0]
    frames = extract.video_frames(row)
    assert frames, "no frames were extracted"

    described, errors = vision.describe_many("en", [(f"frame {i}", uri, row["id"])
                                                    for i, uri in enumerate(frames)])
    assert errors == [], errors
    assert len(described.split()) > 20
    # The description is cached on the attachment, so re-analysis does not pay for it again.
    assert database.get_attachment(row["id"])["description"]


@live
def test_live_full_analysis_with_an_attachment(pin_provider, database, case, monkeypatch):
    import analysis
    from config import WEBHOOK_URL

    monkeypatch.setattr(analysis, "WEBHOOK_URL", os.getenv("ALPHA_LIVE_WEBHOOK", WEBHOOK_URL))

    class Uploaded:
        name, type = "scene.png", "image/png"

        def getvalue(self):
            return _scene_png()

    import attachments

    attachments.save(case, Uploaded())
    analysis._run_analysis(case, "en")
    row = database.get_case(case)
    assert row["status"] == "analyzed", row["error"]
    report = analysis.parse_report(row["report_text"])
    assert report, "the workflow did not return a JSON report"
    assert json.dumps(report, ensure_ascii=False)
