"use strict";
(() => {
  const $ = selector => document.querySelector(selector);
  const $$ = selector => [...document.querySelectorAll(selector)];
  const svgNS = "http://www.w3.org/2000/svg";
  const clamp = value => Math.max(0, Math.min(1, value));
  const process = $("#process");
  const navigation = $(".process-nav");
  const stage = $(".process-stage");
  const painting = $("#painting");
  const beats = $$(".process-beat");
  const links = $$("[data-beat-link]");
  const reducedPreference = matchMedia("(prefers-reduced-motion: reduce)");
  const smallScreen = matchMedia("(max-width: 650px)");
  let reduced = reducedPreference.matches;
  let explicitMotionChoice = false;
  let seal = "";
  let scheduled = 0;
  let navHeight = 78;

  // Registered to the actual 1024×1536 Mazu portrait, projected into 1000×1500.
  // Mask strokes uncover raster detail in the area touched by the brush.
  const inkRoutes = [
    {d:"M399 76 L600 76 L584 189 Q501 167 419 199 Z",w:45},
    {d:"M499 62 C475 104 533 119 498 152 C467 179 542 198 498 219",w:62},
    {d:"M410 82 L418 191 M432 84 L439 185 M461 83 L462 179 M490 83 L490 177 M519 83 L519 180 M549 83 L545 184 M578 84 L571 190",w:24},
    {d:"M415 211 C422 184 459 187 499 184 C545 184 574 195 584 227 C601 264 584 291 565 307 M423 213 C401 247 409 282 432 303",w:55},
    {d:"M439 223 C425 261 437 313 459 341 Q499 381 539 344 C565 318 579 267 559 226",w:46},
    {d:"M454 268 Q470 253 487 268 M518 268 Q535 253 548 266 M498 272 L488 301 Q500 314 511 300 M481 326 Q500 319 519 326 Q499 340 481 326",w:28},
    {d:"M383 146 C378 209 386 273 389 329 M608 145 C621 212 615 273 614 329 M426 318 C411 368 421 438 430 509 M571 318 C588 382 577 447 575 514",w:59},
    {d:"M441 351 L448 377 L497 430 L547 378 L549 349 M417 386 C329 409 300 485 243 591 Q294 612 373 634 M579 386 C674 416 702 496 758 591 Q711 607 623 633",w:70},
    {d:"M478 460 L500 447 L523 460 L520 715 L479 715 Z M439 641 Q462 609 499 616 Q537 609 562 639 L548 678 Q522 662 500 652 Q471 674 438 682 Z",w:47},
    {d:"M412 627 C391 741 384 841 337 940 C297 1031 262 1161 204 1297 M586 627 C610 754 622 850 665 943 C709 1051 740 1170 801 1294",w:95},
    {d:"M321 435 C273 466 379 491 315 535 S363 583 282 601 M682 435 C742 476 627 498 691 541 S647 583 732 605",w:114},
    {d:"M242 602 C191 663 226 706 187 731 C197 819 161 901 147 978 C169 1069 115 1141 121 1214 M759 602 C812 667 785 704 812 731 C819 817 847 904 854 979 C839 1068 885 1140 879 1213",w:86},
    {d:"M343 670 C228 723 362 787 251 839 S341 921 231 969 S334 1043 217 1107 S277 1183 177 1234",w:158},
    {d:"M657 670 C775 722 639 787 749 840 S660 921 768 968 S667 1046 784 1104 S723 1182 820 1235",w:158},
    {d:"M481 730 C435 808 552 843 490 911 C442 972 551 1031 488 1090 C438 1160 552 1243 490 1335",w:172},
    {d:"M357 967 C443 1005 305 1050 379 1114 C441 1176 304 1239 385 1299 M643 967 C557 1005 695 1050 621 1114 C559 1176 696 1239 615 1299",w:139},
    {d:"M246 1309 Q493 1293 752 1309 M129 1231 C116 1301 41 1309 25 1396 Q90 1436 161 1414 C279 1490 359 1418 439 1454 Q501 1482 561 1454 C652 1411 735 1491 845 1415 Q922 1436 975 1395 C958 1321 879 1305 869 1235",w:136},
  ];
  const washRoutes = [
    {d:"M458 236 C548 224 437 282 544 279 C563 306 454 301 468 337 Q501 374 540 333",w:66},
    {d:"M401 118 Q499 93 595 119 M415 181 Q500 153 583 180",w:74},
    {d:"M397 421 Q285 462 361 494 T308 580 M603 421 Q715 465 640 496 T692 582",w:133},
    {d:"M486 480 L493 603 M467 646 Q503 623 548 645 M495 685 L500 715",w:53},
    {d:"M317 664 C199 773 340 811 263 896 S239 1090 181 1219 M683 664 C801 773 660 811 737 896 S761 1090 819 1219",w:164},
    {d:"M418 716 C396 905 282 1023 266 1224 M582 716 C604 905 718 1023 734 1224",w:84},
    {d:"M500 761 L498 1306 M354 965 C467 1060 308 1169 379 1288 M646 965 C533 1060 692 1169 621 1288",w:190},
    {d:"M110 1331 C270 1309 282 1401 500 1373 S776 1321 895 1367",w:210},
  ];
  const colorRoutes = [
    {d:"M415 101 L584 102 M440 176 Q497 142 566 176",w:97},
    {d:"M433 226 Q500 193 567 225 M461 278 L542 278 M471 332 L534 332",w:95},
    {d:"M333 435 C407 464 305 489 375 519 S298 559 341 592 M667 435 C593 464 695 489 625 519 S702 559 659 592",w:150},
    {d:"M331 651 C211 731 340 837 244 908 C183 971 259 1112 181 1206 M669 651 C789 731 660 837 756 908 C817 971 741 1112 819 1206",w:207},
    {d:"M419 690 C393 913 280 1078 245 1251 M581 690 C607 913 720 1078 755 1251",w:121},
    {d:"M500 441 L500 1254 M360 978 C434 1053 324 1181 395 1285 M640 978 C566 1053 676 1181 605 1285",w:216},
    {d:"M99 1368 Q277 1307 501 1389 Q748 1310 910 1368",w:240},
  ];
  const goldRoutes = [
    {d:"M400 76 H600 M410 85 L419 190 M435 85 L440 183 M462 84 L464 181 M491 84 L490 179 M520 84 L520 181 M548 84 L547 184 M577 85 L574 190",w:17},
    {d:"M499 63 C471 106 537 116 497 151 C469 174 540 190 498 213 M421 198 Q497 173 582 198",w:27},
    {d:"M383 146 L390 328 M614 146 L616 328 M427 322 L430 509 M575 322 L575 509",w:28},
    {d:"M245 591 Q313 611 375 632 M758 591 Q689 611 625 632 M410 634 C392 804 343 973 251 1238 M590 634 C608 804 657 973 748 1238",w:23},
    {d:"M312 731 C396 700 304 804 289 802 C231 842 329 877 358 829 M681 731 C601 703 697 805 711 802 C768 842 671 877 642 829",w:55},
    {d:"M478 737 L459 1320 Q498 1343 551 1320 L528 735 M246 1309 Q365 1327 457 1307 M551 1307 Q653 1329 753 1309",w:23},
    {d:"M399 1049 C299 992 394 1114 346 1143 C320 1166 414 1211 407 1143 M601 1049 C701 992 606 1114 654 1143 C680 1166 586 1211 593 1143",w:54},
  ];
  const sketchRoutes = [
    {d:"M499 63 L499 1458",w:1.2},
    {d:"M396 76 H602 L582 199 Q499 178 419 199 Z",w:1.5},
    {d:"M440 218 C416 273 442 353 499 365 C556 353 582 273 561 218",w:1.5},
    {d:"M426 387 Q334 417 244 591 M573 387 Q665 417 759 591",w:1.5},
    {d:"M437 649 Q499 605 563 649 M477 460 H523 V715 H477 Z",w:1.3},
    {d:"M244 591 L143 989 L106 1278 L25 1397 Q252 1482 499 1458 Q754 1481 975 1397 L894 1278 L855 989 L759 591",w:1.4},
  ];

  function makeSet(id, routes, widthOverride) {
    const parent = document.getElementById(id);
    return routes.map(route => {
      const path = document.createElementNS(svgNS, "path");
      path.setAttribute("d", route.d);
      path.setAttribute("stroke-width", String(widthOverride || route.w));
      parent.append(path);
      const length = Math.max(1, path.getTotalLength());
      path.style.strokeDasharray = `${length} ${length}`;
      path.style.strokeDashoffset = String(length);
      return {path, length};
    });
  }
  const sets = {
    sketch: makeSet("sketch-lines", sketchRoutes),
    ink: makeSet("ink-mask-paths", inkRoutes),
    inkTrace: makeSet("ink-traces", inkRoutes, 1.3),
    wash: makeSet("wash-mask-paths", washRoutes),
    color: makeSet("color-mask-paths", colorRoutes),
    gold: makeSet("gold-mask-paths", goldRoutes),
    goldTrace: makeSet("gold-traces", goldRoutes, 1.8),
  };
  goldRoutes.forEach(route => {
    const path = document.createElementNS(svgNS, "path");
    path.setAttribute("d", route.d);
    path.setAttribute("stroke-width", "4");
    $("#gold-reserved-paths").append(path);
  });

  function stroke(set, amount) {
    let remaining = clamp(amount) * set.reduce((sum, item) => sum + item.length, 0);
    let cursor = null;
    set.forEach(item => {
      const length = Math.max(0, Math.min(item.length, remaining));
      item.path.style.strokeDashoffset = String(item.length - length);
      if (remaining >= 0 && remaining <= item.length) cursor = {item, length};
      remaining -= item.length;
    });
    return cursor || {item:set[set.length - 1], length:set[set.length - 1].length};
  }
  function draw(cursor, index) {
    const phase = cursor - index;
    const ink = clamp(cursor - 1);
    const wash = clamp(cursor - 2);
    const color = clamp((cursor - 3) / .7);
    const gold = clamp((cursor - 3 - .48) / .52);
    const pens = [stroke(sets.sketch, clamp(cursor)), stroke(sets.ink, ink), stroke(sets.wash, wash), stroke(sets.color, color)];
    stroke(sets.inkTrace, ink);
    const goldPen = stroke(sets.gold, gold);
    stroke(sets.goldTrace, gold);
    $("#sketch-lines").style.opacity = String(.5 * (1 - ink));
    $("#ink-traces").style.opacity = String(.35 * (1 - wash));
    $("#gold-traces").style.opacity = cursor >= 4 ? "0" : ".7";
    [["ink",ink],["wash",wash],["color",color],["gold",gold]].forEach(([name,amount]) => {
      document.getElementById(`${name}-complete`).setAttribute("opacity", amount === 1 ? "1" : "0");
      painting.dataset[name] = amount.toFixed(4);
    });
    const brush = $("#brush");
    if (cursor > .025 && cursor < 4) {
      const pen = index === 3 && gold > 0 ? goldPen : pens[Math.min(index, 3)];
      const point = pen.item.path.getPointAtLength(pen.length);
      const next = pen.item.path.getPointAtLength(Math.min(pen.item.length, pen.length + 3));
      const angle = Math.atan2(next.y-point.y,next.x-point.x) * 180 / Math.PI + 35;
      brush.setAttribute("transform", `translate(${point.x} ${point.y}) rotate(${angle})`);
      brush.setAttribute("opacity", "1");
    } else brush.setAttribute("opacity", "0");
    $("#visitor-seal").setAttribute("opacity", cursor >= 4 && seal ? "1" : "0");
    $(".painting-progress span").style.width = `${clamp(cursor/5)*100}%`;
    painting.dataset.beat = String(index);
    painting.dataset.phase = phase.toFixed(4);
  }

  function measure() {
    navHeight = navigation.getBoundingClientRect().height;
    document.documentElement.style.setProperty("--nav-height", `${navHeight}px`);
  }
  function currentBeat() {
    let index = 0;
    beats.forEach((beat,i) => { if (beat.getBoundingClientRect().top <= navHeight + 2) index = i; });
    return index;
  }
  function paint() {
    scheduled = 0;
    measure();
    const index = currentBeat();
    const rect = beats[index].getBoundingClientRect();
    const cursor = index + clamp((navHeight - rect.top) / Math.max(1,rect.height));
    links.forEach((link,i) => {
      if (i === index) link.setAttribute("aria-current", "step");
      else link.removeAttribute("aria-current");
    });
    draw(cursor,index);
    $("#stage-technique").textContent = beats[index].dataset.technique;
    $("#stage-count").textContent = `${["一","二","三","四","五"][index]} / 五`;
    $("#mobile-eyebrow").textContent = beats[index].querySelector(".eyebrow").textContent;
    $("#mobile-title").textContent = beats[index].querySelector("h2").textContent;
    $("#mobile-copy").textContent = beats[index].querySelector(".beat-copy > p").textContent;
    $(".mobile-seals").hidden = index !== 4 || reduced;
    $(".mobile-end-actions").hidden = index !== 4 || reduced;
  }
  function schedule() { if (!scheduled) scheduled = requestAnimationFrame(paint); }
  function mode(preserve = false) {
    const bounds = process.getBoundingClientRect();
    const keep = preserve && bounds.top < innerHeight && bounds.bottom > 0 ? beats[currentBeat()] : null;
    document.body.dataset.motion = reduced ? "off" : "on";
    stage.hidden = reduced;
    $$(".motion-toggle").forEach(button => {
      button.hidden = false;
      button.textContent = reduced ? "開啟動態" : "靜態閱讀";
      button.setAttribute("aria-pressed",String(reduced));
    });
    // The same source text stays in the accessibility tree on small screens.
    // Only controls inside its visually hidden duplicate are disabled there.
    const hideDuplicates = !reduced && smallScreen.matches;
    $$(".process-beat button").forEach(button => {
      button.disabled = hideDuplicates;
      button.hidden = hideDuplicates || (button.hasAttribute("data-open-art") && typeof $("#art-dialog").showModal !== "function");
    });
    $$(".process-beat .beat-copy a").forEach(link => { link.hidden = hideDuplicates; });
    measure();
    if (keep) keep.scrollIntoView({block:"start",behavior:"instant"});
    schedule();
  }
  $$(".motion-toggle").forEach(button => button.addEventListener("click", () => {
    explicitMotionChoice = true; reduced = !reduced; mode(true);
  }));
  reducedPreference.addEventListener("change", () => {
    if (!explicitMotionChoice) { reduced = reducedPreference.matches; mode(true); }
  });
  smallScreen.addEventListener("change", () => mode(false));

  const endings = {"安":"把安穩，\n留給今天。","定":"讓心先定下來，\n再往前走。","願":"願有所向，\n也記得眼前。"};
  function chooseSeal(value) {
    seal = value;
    $$("[data-seal]").forEach(button => button.setAttribute("aria-pressed",String(button.dataset.seal === value)));
    $("#seal-character").textContent = value || "安";
    $$("[data-seal-mark]").forEach(mark => { mark.hidden = !value; mark.textContent = value; });
    $(".seal-status").textContent = value ? `已在畫角留下「${value}」字訪客印。` : "尚未選擇訪客印。";
    $("#ending-text").textContent = endings[value] || "看完一幅畫，\n也留一點安靜。";
    schedule();
  }
  $$("[data-seal]").forEach(button => {
    button.hidden = false;
    button.addEventListener("click", () => chooseSeal(button.dataset.seal));
  });
  $(".seal-status").hidden = false;
  $$("[data-replay]").forEach(link => link.addEventListener("click", () => chooseSeal("")));

  const dialog = $("#art-dialog");
  let opener = null;
  if (typeof dialog.showModal === "function") {
    $$("[data-open-art]").forEach(button => {
      button.hidden = false;
      button.addEventListener("click", () => { opener = button; dialog.showModal(); });
    });
    $$(".image-fallback").forEach(link => { link.hidden = true; });
    $("#close-art").addEventListener("click", () => dialog.close());
    dialog.addEventListener("close", () => { if (opener && !opener.disabled) opener.focus({preventScroll:true}); });
    dialog.addEventListener("click", event => {
      const bounds = dialog.getBoundingClientRect();
      if (event.target === dialog && (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom)) dialog.close();
    });
  }
  addEventListener("scroll",schedule,{passive:true});
  addEventListener("resize",schedule,{passive:true});
  addEventListener("hashchange",schedule);
  addEventListener("load",schedule,{once:true});
  mode();
})();
