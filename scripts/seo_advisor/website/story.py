"""Render a declarative scene journey; static chapter text is the source of truth."""

import html
from pathlib import Path

from seo_advisor.website.images import read_raster
from seo_advisor.website.models import ActorPose, Hero, ScenePoint, WebsiteBrief


def collect_story_assets(brief: WebsiteBrief, base: Path) -> list[dict]:
    base = base.resolve()
    specs = [(f"scene-{i:02d}", scene.image) for i, scene in enumerate(brief.story_scenes, 1)]
    if brief.story_actor:
        specs.append(("actor", brief.story_actor))
    assets = []
    for identifier, asset in specs:
        path = (base / asset.path).resolve()
        if not path.is_relative_to(base) or not path.is_file():
            raise ValueError(f"{identifier} 圖片必須是 brief 目錄內現有的檔案")
        raw, size = read_raster(path)
        assets.append(
            {
                "id": identifier,
                "path": f"assets/{identifier}{path.suffix.lower()}",
                "raw": raw,
                "size": size,
                "spec": asset,
            }
        )
    return assets


def _e(value: str) -> str:
    return html.escape(value, quote=True)


def _image(asset: dict, class_name: str, *, decorative: bool = False) -> str:
    source: Hero = asset["spec"]
    # Decorative stage duplicates are aria-hidden; static chapter figures retain their alt.
    hidden = ' aria-hidden="true"' if decorative else ""
    return f'<img class="{class_name}" src="{asset["path"]}" alt="{_e(source.alt)}" width="{asset["size"][0]}" height="{asset["size"][1]}" loading="lazy" decoding="async"{hidden}>'


def _effects(effect: str, points: list[ScenePoint]) -> str:
    if effect == "mist":
        return '<div class="fx-mist fx-mist-left"></div><div class="fx-mist fx-mist-right"></div>'
    if effect == "wind":
        return (
            '<div class="fx-wind">'
            + "".join(f'<i style="--strand:{i}"></i>' for i in range(6))
            + "</div>"
        )
    if effect == "lanterns":
        lamps = points or [ScenePoint(x=62, y=33), ScenePoint(x=74, y=29), ScenePoint(x=86, y=37)]
        return (
            '<div class="fx-lanterns">'
            + "".join(
                f'<i class="fx-lantern" data-effect-x="{point.x}" data-effect-y="{point.y}" style="left:{point.x}%;top:{point.y}%;--lamp:{i}"></i>'
                for i, point in enumerate(lamps)
            )
            + "</div>"
        )
    if effect == "steam":
        origin = points[0] if points else ScenePoint(x=70, y=68)
        return f'<div class="fx-steam" data-effect-x="{origin.x}" data-effect-y="{origin.y}" style="left:{origin.x}%;top:{origin.y}%"><svg viewBox="0 0 160 200" aria-hidden="true"><path d="M42 195 C8 155 86 137 45 100 S72 34 58 4"/><path d="M80 199 C126 158 44 138 88 97 S61 33 86 1"/><path d="M117 196 C145 161 91 132 120 99 S104 39 124 8"/></svg></div>'
    return ""


def render_story(brief: WebsiteBrief, assets: list[dict]) -> str:
    by_id = {asset["id"]: asset for asset in assets}
    actor = by_id.get("actor")
    layers, chapters, links = [], [], []
    for index, (scene, chapter) in enumerate(zip(brief.story_scenes, brief.chapters), 1):
        asset = by_id[f"scene-{index:02d}"]
        pose = scene.actor_pose
        layers.append(
            f'<div class="scene-layer" data-scene="{index}" data-effect="{scene.effect}" data-position-x="{scene.image_position.x}" data-position-y="{scene.image_position.y}" style="--image-x:{scene.image_position.x}%;--image-y:{scene.image_position.y}%" aria-hidden="true">{_image(asset, "scene-background", decorative=True)}<div class="scene-effects">{_effects(scene.effect, scene.effect_points)}</div></div>'
        )
        static_actor = ""
        if actor:
            static_actor = f'<span class="static-actor" style="left:{pose.x}%;top:{pose.y}%;transform:translate(-50%,-50%) rotate({pose.rotation}deg) scale({pose.scale})">{_image(actor, "actor-image", decorative=True)}</span>'
        chapters.append(
            f'<article class="chapter story-beat" id="chapter-{index}" tabindex="-1" data-x="{pose.x}" data-y="{pose.y}" data-rotation="{pose.rotation}" data-scale="{pose.scale}" data-effect="{scene.effect}"><figure class="beat-static"><div class="static-scene-frame" style="aspect-ratio:{asset["size"][0]}/{asset["size"][1]}">{_image(asset, "beat-background")}{static_actor}</div><figcaption>{_e(scene.image.alt)}</figcaption></figure><div class="beat-copy"><span class="eyebrow">第 {index:02d} 幕 / {len(brief.story_scenes):02d}</span><h2>{_e(chapter.title)}</h2><p>{_e(chapter.body)}</p></div></article>'
        )
        links.append(
            f'<li><a href="#chapter-{index}" data-chapter-link="{index}" aria-label="第 {index} 幕：{_e(chapter.title)}"><span>{index:02d}</span><span class="chapter-label">{_e(chapter.title)}</span></a></li>'
        )
    action = brief.story_action
    action_button = f'<button class="story-action" type="button" aria-pressed="false" data-idle-label="{_e(action.label)}" data-active-label="{_e(action.active_label)}" hidden><span class="action-spark" aria-hidden="true">✦</span><span class="action-label">{_e(action.label)}</span></button>'
    first_pose = brief.story_scenes[0].actor_pose
    start = brief.story_start_pose or ActorPose(
        x=min(100, first_pose.x + 8),
        y=min(100, first_pose.y + 10),
        rotation=max(-180, first_pose.rotation - 15),
        scale=max(0.2, first_pose.scale * 0.75),
    )
    actor_markup = (
        f'<div class="stage-actor">{_image(actor, "actor-image", decorative=True)}<span class="actor-aura"></span></div>'
        if actor
        else ""
    )
    return f"""<section class="story story-cinematic" id="story" aria-label="品牌故事" data-story-scenes="{len(brief.story_scenes)}" data-start-x="{start.x}" data-start-y="{start.y}" data-start-rotation="{start.rotation}" data-start-scale="{start.scale}">
  <nav class="story-navigation" aria-label="故事章節"><ol>{"".join(links)}</ol><div class="story-tools"><button type="button" data-story-motion hidden>靜態閱讀</button><a href="#chapter-1" data-story-replay>重看故事</a><a href="#selection">略過故事 →</a></div></nav>
  <div class="story-stage" aria-hidden="true" data-awake="false" hidden>{"".join(layers)}<div class="scene-shade"></div>{actor_markup}<span class="scene-counter"><span id="chapter-progress">01</span> / {len(brief.story_scenes):02d}</span><div class="journey-line"><span></span></div></div>
  <div class="story-action-panel">{action_button}<p class="story-action-status" role="status" aria-live="polite" hidden>{_e(action.prompt)}</p><noscript><p>目前以靜態圖文閱讀，完整故事仍可往下查看。</p></noscript></div>
  <div class="chapters story-beats">{"".join(chapters)}</div>
  <div class="journey-ending"><span class="eyebrow">旅程的終點</span>{action_button}<p class="journey-result" data-active-result="{_e(action.result_text)}" data-idle-result="{_e(action.inactive_result_text)}">{_e(action.inactive_result_text)}</p><div><a href="#chapter-1" data-story-replay>再走一次 ↑</a><a href="#selection">繼續往下 →</a></div></div>
</section>"""
