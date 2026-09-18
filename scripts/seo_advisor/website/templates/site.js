"use strict";
(() => {
  const body = document.body;
  const media = window.matchMedia("(prefers-reduced-motion: reduce)");
  const toggle = document.getElementById("motion-toggle");
  const story = document.getElementById("story");
  const chapters = [...document.querySelectorAll(".chapter")];
  const progress = document.getElementById("chapter-progress");
  const timeline = window.SeoStoryTimeline;
  const cinematic = Boolean(story.classList.contains("story-cinematic") && timeline);
  const stage = story.querySelector(".story-stage");
  const layers = [...story.querySelectorAll(".scene-layer")];
  const actor = story.querySelector(".stage-actor");
  const navigation = story.querySelector(".story-navigation");
  const chapterLinks = [...story.querySelectorAll("[data-chapter-link]")];
  const actions = [...story.querySelectorAll(".story-action")];
  const actionPanel = story.querySelector(".story-action-panel");
  const journeyEnding = story.querySelector(".journey-ending");
  const motionControls = [toggle, ...story.querySelectorAll("[data-story-motion]")];
  const poses = chapters.map(chapter => ({
    x: Number(chapter.dataset.x), y: Number(chapter.dataset.y),
    rotation: Number(chapter.dataset.rotation), scale: Number(chapter.dataset.scale),
  }));
  const effects = chapters.map(chapter => chapter.dataset.effect);
  const startPose = {x:Number(story.dataset.startX), y:Number(story.dataset.startY), rotation:Number(story.dataset.startRotation), scale:Number(story.dataset.startScale)};
  let reduced = media.matches;
  let userChoice = false;
  let awake = false;
  let frame = 0;
  const clamp = value => Math.max(0, Math.min(1, value));
  function readingChapter() {
    let index = 0;
    chapters.forEach((chapter, i) => {
      if (chapter.getBoundingClientRect().top < innerHeight * 0.6) index = i;
    });
    return index;
  }
  const applyMotion = (preserve = false) => {
    const bounds = story.getBoundingClientRect();
    const keep = preserve && bounds.top < innerHeight && bounds.bottom > 0 ? chapters[readingChapter()] : null;
    body.dataset.motion = reduced ? "off" : "on";
    body.dataset.storyMotion = cinematic && !reduced ? "on" : "off";
    if (stage) stage.hidden = reduced || !cinematic;
    motionControls.forEach(control => {
      control.hidden = false;
      control.textContent = control === toggle ? (reduced ? "動畫：關閉" : "動畫：開啟") : (reduced ? "開啟動態" : "靜態閱讀");
      control.setAttribute("aria-pressed", String(reduced));
    });
    // Changing reading mode preserves the current chapter; ordinary scrolling is untouched.
    if (keep) keep.scrollIntoView({block: "start", behavior: "instant"});
    schedule();
  };
  motionControls.forEach(control => control.addEventListener("click", () => {
    userChoice = true; reduced = !reduced; applyMotion(true);
  }));
  const systemChange = () => { if (!userChoice) { reduced = media.matches; applyMotion(true); } };
  if (media.addEventListener) media.addEventListener("change", systemChange);
  function project(point, index, viewport) {
    const layer = layers[index];
    const image = layer.querySelector(".scene-background");
    return timeline.project(point,
      {width: Number(image.getAttribute("width")), height: Number(image.getAttribute("height"))}, viewport,
      {x: Number(layer.dataset.positionX), y: Number(layer.dataset.positionY)});
  }
  const paint = () => {
    frame = 0;
    let active = readingChapter();
    if (actionPanel && journeyEnding) {
      const endingBounds = journeyEnding.getBoundingClientRect();
      const endingVisible = endingBounds.top < innerHeight && endingBounds.bottom > 0;
      actionPanel.style.visibility = cinematic && !reduced && endingVisible ? "hidden" : "visible";
    }
    if (cinematic && !reduced) {
      const navHeight = navigation.getBoundingClientRect().height;
      let index = 0;
      chapters.forEach((chapter, i) => { if (chapter.getBoundingClientRect().top <= navHeight) index = i; });
      const bounds = chapters[index].getBoundingClientRect();
      const cursor = index + clamp((navHeight - bounds.top) / Math.max(1, bounds.height));
      const viewport = {width: stage.clientWidth, height: stage.clientHeight};
      const projected = poses.map((pose, i) => project(pose, i, viewport));
      const state = timeline.sample(cursor, projected, effects, awake, project(startPose, 0, viewport));
      active = state.index;
      stage.dataset.scene = String(active + 1);
      stage.dataset.phase = state.phase.toFixed(4);
      stage.style.setProperty("--warmth", String(state.warmth));
      stage.style.setProperty("--journey-progress", String(state.progress));
      if (actor) {
        actor.style.left = `${state.x}%`;
        actor.style.top = `${state.y}%`;
        actor.style.transform = `translate(-50%,-50%) rotate(${state.rotation}deg) scale(${state.scale})`;
      }
      layers.forEach((layer, i) => {
        const current = i === state.index;
        const entering = i === state.next && i !== state.index;
        layer.style.opacity = current || (entering && state.reveal > 0) ? "1" : "0";
        layer.style.clipPath = entering ? `circle(${state.reveal * 160}% at ${state.x}% ${state.y}%)` : "none";
        layer.style.setProperty("--effect-progress", String(i < state.index ? 1 : current ? state.phase : 0));
        layer.querySelectorAll("[data-effect-x]").forEach(effect => {
          const point = project({x: Number(effect.dataset.effectX), y: Number(effect.dataset.effectY)}, i, viewport);
          effect.style.left = `${point.x}%`;
          effect.style.top = `${point.y}%`;
        });
      });
    }
    progress.textContent = String(active + 1).padStart(2, "0");
    chapterLinks.forEach((link, i) => {
      if (i === active) link.setAttribute("aria-current", "step");
      else link.removeAttribute("aria-current");
    });
  };
  function schedule() { if (!frame) frame = requestAnimationFrame(paint); }
  function setAwake(value) {
    awake = value;
    story.dataset.awake = String(value);
    if (stage) stage.dataset.awake = String(value);
    if (actions.length) {
      actions.forEach(action => {
        action.setAttribute("aria-pressed", String(value));
        action.querySelector(".action-label").textContent = value ? action.dataset.activeLabel : action.dataset.idleLabel;
      });
      story.querySelector(".story-action-status").textContent = value ? "你的選擇已留下，故事將帶著它繼續。" : story.querySelector(".story-action-status").dataset.prompt;
    }
    const ending = story.querySelector(".journey-result");
    if (ending) ending.textContent = value ? ending.dataset.activeResult : ending.dataset.idleResult;
    schedule();
  }
  if (actions.length) {
    actions.forEach(action => {
      action.hidden = false;
      action.addEventListener("click", () => setAwake(!awake));
    });
    const status = story.querySelector(".story-action-status");
    status.dataset.prompt = status.textContent;
    status.hidden = false;
    story.querySelectorAll("[data-story-replay]").forEach(link => link.addEventListener("click", () => setAwake(false)));
  }
  addEventListener("scroll", schedule, { passive: true });
  addEventListener("resize", schedule, { passive: true });
  addEventListener("hashchange", schedule);
  applyMotion();
  if ("IntersectionObserver" in window) {
    const observer = new IntersectionObserver(entries => {
      entries.forEach(entry => {
        if (entry.isIntersecting) { entry.target.classList.add("in-view"); observer.unobserve(entry.target); }
      });
    }, { threshold: 0.08 });
    body.dataset.reveal = "on";
    document.querySelectorAll(".reveal").forEach(element => observer.observe(element));
  }

  // Demo list only: no persistence, checkout calls, personal data or order status.
  const cart = new Map();
  const status = document.getElementById("cart-status");
  const list = document.getElementById("cart-items");
  const clear = document.getElementById("clear-cart");
  const renderCart = () => {
    list.replaceChildren();
    let count = 0;
    cart.forEach((quantity, name) => {
      count += quantity;
      const row = document.createElement("li");
      row.textContent = `${name} × ${quantity} `;
      const remove = document.createElement("button");
      remove.type = "button";
      remove.className = "text-button";
      remove.textContent = "移除";
      remove.setAttribute("aria-label", `移除 ${name}`);
      remove.addEventListener("click", () => { cart.delete(name); renderCart(); });
      row.append(remove);
      list.append(row);
    });
    status.textContent = count ? `示範清單共 ${count} 件；尚未建立訂單。` : "清單目前是空的。";
    clear.hidden = count === 0;
  };
  document.querySelectorAll(".demo-add").forEach(button => {
    button.hidden = false;
    button.addEventListener("click", () => {
      const name = button.dataset.product;
      cart.set(name, (cart.get(name) || 0) + 1);
      renderCart();
    });
  });
  if (clear) clear.addEventListener("click", () => { cart.clear(); renderCart(); });

  document.querySelectorAll("[data-mood]").forEach(button => {
    button.hidden = false;
    button.addEventListener("click", () => {
      document.querySelectorAll("[data-mood]").forEach(other => other.setAttribute("aria-pressed", String(other === button)));
      document.querySelectorAll(".mood-notes article").forEach(note => note.classList.toggle("selected", note.id === button.dataset.mood));
      document.getElementById("mood-status").textContent = `你選了「${button.textContent}」，也可以換一種感受。`;
    });
  });
})();
