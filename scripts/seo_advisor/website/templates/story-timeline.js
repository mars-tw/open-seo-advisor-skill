/* A pure scroll timeline. Same position + action state always returns the same frame. */
"use strict";
((root) => {
  const clamp = (value, low = 0, high = 1) => Math.max(low, Math.min(high, value));
  const ease = value => value * value * (3 - 2 * value);
  const mix = (start, end, fraction) => fraction === 0 ? start : fraction === 1 ? end : start + (end - start) * fraction;
  function sample(position, poses, effects, awake = false, startPose = null) {
    const last = poses.length - 1;
    const cursor = clamp(position, 0, poses.length);
    const index = Math.min(last, Math.floor(cursor));
    const phase = cursor - index;
    const next = Math.min(last, index + 1);
    const travel = ease(index === last && effects[index] === "steam" ? clamp(phase / 0.45) : phase);
    const start = index === 0 ? (startPose || {...poses[0], y: poses[0].y + 6, scale: poses[0].scale * .75}) : poses[index - 1];
    const end = poses[index];
    const effect = effects[index];
    const windArc = effect === "wind" ? Math.sin(phase * Math.PI) : 0;
    return {
      index, next, phase,
      reveal: next === index ? 0 : ease(clamp((phase - 0.68) / 0.32)),
      progress: cursor / poses.length,
      x: mix(start.x, end.x, travel),
      y: mix(start.y, end.y, travel) - windArc * 5,
      rotation: mix(start.rotation, end.rotation, travel) + windArc * 24,
      scale: mix(start.scale, end.scale, travel),
      warmth: awake ? 1 : 0.2,
    };
  }
  function project(point, image, viewport, position = {x: 70, y: 50}) {
    const scale = Math.max(viewport.width / image.width, viewport.height / image.height);
    const width = image.width * scale;
    const height = image.height * scale;
    return {
      ...point,
      x: ((viewport.width - width) * position.x / 100 + width * point.x / 100) / viewport.width * 100,
      y: ((viewport.height - height) * position.y / 100 + height * point.y / 100) / viewport.height * 100,
    };
  }
  const api = Object.freeze({sample, project});
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.SeoStoryTimeline = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
