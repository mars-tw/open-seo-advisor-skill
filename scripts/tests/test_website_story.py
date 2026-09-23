"""Scene integrity, offline narrative and deterministic reverse-scroll behavior."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from bs4 import BeautifulSoup
from PIL import Image

from seo_advisor.website.builder import build_site, demo_brief, load_brief
from seo_advisor.website.check import check_site
from seo_advisor.website.models import WebsiteBrief


def scene_brief(tmp_path):
    data = demo_brief("experience").model_dump()
    data["chapters"].append({"title": "最後一幕", "body": "旅程抵達，故事中的選擇留下了結果。"})
    scenes = []
    for i, (effect, color) in enumerate(
        zip(["mist", "wind", "lanterns", "steam"], ["blue", "green", "purple", "orange"])
    ):
        path = tmp_path / f"scene{i}.png"
        Image.new("RGB", (160, 90), color).save(path)
        scenes.append(
            {
                "image": {"path": path.name, "alt": f"第 {i + 1} 幕場景示意", "source": "provided"},
                "effect": effect,
                "actor_pose": {
                    "x": 65 + i * 3,
                    "y": 60 + i,
                    "rotation": i * 8,
                    "scale": 0.45 if i == 3 else 1,
                },
                "effect_points": [{"x": 74, "y": 63}],
                "image_position": {"x": 85, "y": 50},
            }
        )
    Image.new("RGBA", (32, 32), (255, 200, 0, 120)).save(tmp_path / "actor.png")
    data.update(
        story_scenes=scenes,
        story_actor={"path": "actor.png", "alt": "持續前進的角色示意"},
        story_start_pose={"x": 82, "y": 83, "rotation": -38, "scale": 0.65},
    )
    data["assets"] = {"hero": scenes[0]["image"]}
    return WebsiteBrief.model_validate(data)


def test_four_scenes_ship_with_semantic_static_content_and_dedup_hero(tmp_path):
    brief = scene_brief(tmp_path)
    out = tmp_path / "story"
    report = build_site(brief, out, base_dir=tmp_path)
    assert report["status"] == "scaffold", report
    assert report["errors"] == []
    doc = BeautifulSoup((out / "public/index.html").read_text(encoding="utf-8"), "html.parser")
    assert len(doc.select(".scene-layer")) == 4
    assert len(doc.select(".stage-actor")) == 1
    assert [a["href"] for a in doc.select("[data-chapter-link]")] == [
        f"#chapter-{i}" for i in range(1, 5)
    ]
    assert len(doc.select(".beat-static")) == 4
    assert doc.select_one(".story-stage").has_attr("hidden")
    assert doc.select_one(".story-action-status").has_attr("hidden")
    actions = doc.select(".story-action")
    assert len(actions) == 2
    assert doc.select_one(".journey-ending > .story-action") is not None
    assert all(button.has_attr("hidden") and button["type"] == "button" for button in actions)
    assert (
        actions[0]["data-idle-label"] == actions[1]["data-idle-label"] == brief.story_action.label
    )
    assert (
        actions[0]["data-active-label"]
        == actions[1]["data-active-label"]
        == brief.story_action.active_label
    )
    assert all(
        not figure.has_attr("aria-hidden") and not figure.has_attr("hidden")
        for figure in doc.select(".beat-static")
    )
    for chapter, expected in zip(doc.select(".story-beat"), brief.chapters):
        assert chapter.h2.get_text() == expected.title
        assert expected.body in chapter.get_text()
    assert doc.select_one(".hero-image img")["src"] == "assets/scene-01.png"
    assert not (out / "public/assets/hero.png").exists()
    manifest = json.loads((out / "asset-manifest.json").read_text(encoding="utf-8"))
    assert [item["id"] for item in manifest["assets"]] == [
        "hero",
        "scene-01",
        "scene-02",
        "scene-03",
        "scene-04",
        "actor",
    ]
    assert all((out / item["path"]).is_file() for item in manifest["assets"])
    assert (
        build_site(load_brief(out / "brief.json"), tmp_path / "rebuilt", base_dir=out)["errors"]
        == []
    )


def test_story_assets_and_nav_are_checked_after_tampering(tmp_path):
    out = tmp_path / "story"
    build_site(scene_brief(tmp_path), out, base_dir=tmp_path)
    (out / "public/assets/scene-03.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    page = out / "public/index.html"
    page.write_text(
        page.read_text(encoding="utf-8").replace(
            'href="#chapter-3" data-chapter-link', 'href="#missing" data-chapter-link'
        ),
        encoding="utf-8",
    )
    report = check_site(out)
    assert report["status"] == "invalid"
    assert not report["checks"]["scene_3_decodable"]
    assert not report["checks"]["story_navigation"]


def test_large_story_scene_is_bounded_before_delivery(tmp_path):
    brief = scene_brief(tmp_path)
    source = tmp_path / "large-scene.png"
    Image.effect_noise((1400, 900), 30).save(source)
    brief.story_scenes[0].image.path = source.name
    brief.assets.hero.path = source.name
    out = tmp_path / "story"
    report = build_site(brief, out, base_dir=tmp_path)
    assert report["status"] == "scaffold", report["errors"]
    scene = out / "public/assets/scene-01.webp"
    assert scene.is_file() and scene.stat().st_size <= 500_000
    assert report["checks"]["scene_1_budget"] is True


@pytest.mark.parametrize("mutation", ["count", "path", "effect", "pose", "nan"])
def test_story_declarations_reject_unsafe_or_incomplete_inputs(tmp_path, mutation):
    data = scene_brief(tmp_path).model_dump()
    if mutation == "count":
        data["story_scenes"].pop()
    elif mutation == "path":
        data["story_scenes"][0]["image"]["path"] = "../other.png"
    elif mutation == "effect":
        data["story_scenes"][0]["effect"] = "<script>alert(1)</script>"
    elif mutation == "pose":
        data["story_scenes"][0]["actor_pose"]["x"] = 200
    else:
        data["story_start_pose"]["rotation"] = float("nan")
    with pytest.raises(ValueError):
        WebsiteBrief.model_validate(data)


def test_story_copy_and_action_are_escaped(tmp_path):
    brief = scene_brief(tmp_path)
    attack = '<img src=x onerror="alert(1)">'
    brief.story_action.label = attack
    brief.story_action.result_text = attack
    brief.story_scenes[0].image.alt = attack
    out = tmp_path / "story"
    build_site(brief, out, base_dir=tmp_path)
    doc = BeautifulSoup((out / "public/index.html").read_text(encoding="utf-8"), "html.parser")
    assert not doc.select("[onerror]")
    assert doc.select_one(".action-label").get_text() == attack
    assert doc.select_one(".journey-result")["data-active-result"] == attack


def test_story_timeline_reverses_exactly_and_projects_mobile_cover(tmp_path):
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is required for the JavaScript timeline verification")
    timeline = Path(__file__).parents[1] / "seo_advisor/website/templates/story-timeline.js"
    program = r"""
const assert = require("node:assert/strict");
const timeline = require(process.argv[1]);
const poses = [{x:66,y:62,rotation:-20,scale:1},{x:77,y:42,rotation:32,scale:1},{x:72,y:59,rotation:-15,scale:1},{x:74,y:61.5,rotation:0,scale:.45}];
const effects = ["mist","wind","lanterns","steam"];
const start = {x:82,y:83,rotation:-38,scale:.65};
const sample = position => timeline.sample(position, poses, effects, true, start);
assert.equal(sample(0).x,82);
assert.ok(sample(.5).x < 82 && sample(.5).x > 66);
assert.equal(sample(1).x,66);
assert.equal(sample(2).x,77);
assert.equal(sample(4).x,74);
assert.equal(sample(4).y,61.5);
assert.equal(sample(4).scale,.45);
assert.equal(sample(3.45).x,74);
assert.equal(sample(3.45).scale,.45);
assert.deepEqual([sample(3.5).x,sample(3.5).y,sample(3.5).scale],[sample(4).x,sample(4).y,sample(4).scale]);
assert.equal(sample(4).progress,1);
assert.ok(sample(.9).reveal > 0);
assert.ok(sample(1.5).y < (62+42)/2);
const forward = [.15,.9,1.3,2.65,3.6,4].map(sample);
[4,3.6,2.65,1.3,.9,.15].forEach((position,index) => assert.deepEqual(sample(position),forward[forward.length-1-index]));
assert.equal(timeline.sample(3.5,poses,effects,false,start).warmth,.2);
assert.equal(timeline.sample(3.5,poses,effects,true,start).warmth,1);
const point = timeline.project({x:74,y:61.5}, {width:1672,height:941}, {width:390,height:844}, {x:85,y:50});
const scale = 844/941;
assert.ok(Math.abs(point.x - (((390-1672*scale)*.85+1672*scale*.74)/390*100)) < 1e-10);
assert.ok(point.x > 0 && point.x < 100);
assert.ok(Math.abs(point.y-61.5) < 1e-10);
console.log("deterministic path, departure, landing, action and mobile projection passed");
"""
    result = subprocess.run(
        [node, "-e", program, str(timeline)],
        capture_output=True,
        text=True,
        check=False,
        # Shared Windows CI runners can take longer to start Node under load.
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
