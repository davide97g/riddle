// get-riddle: every line of handwriting here is a real stroke from the diary
// (apps/site/tools/make_strokes.py), drawn the way the pen draws it: one path
// at a time, at the speed of a hand, with a pause for the pen to lift.
//
// No scroll listeners: IntersectionObserver decides what is on screen, the
// Web Animations API draws, and prefers-reduced-motion turns every drawing
// into a finished page.

const NS = "http://www.w3.org/2000/svg";
const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
const PAUSE_MS = 3000;

const wait = (ms, signal) =>
  new Promise((done) => {
    if (signal?.aborted) return done();
    const t = setTimeout(done, ms);
    signal?.addEventListener("abort", () => { clearTimeout(t); done(); }, { once: true });
  });

const pathData = (pts) => "M" + pts.map(([x, y]) => `${x} ${y}`).join("L");

function addPaths(group, strokes) {
  return strokes.map((stroke) => {
    const p = document.createElementNS(NS, "path");
    p.setAttribute("d", typeof stroke === "string" ? stroke : pathData(stroke));
    group.appendChild(p);
    return p;
  });
}

function prime(paths) {
  for (const p of paths) {
    const len = p.getTotalLength();
    p.__len = len;
    p.style.strokeDasharray = `${len} ${len + 2}`;
    p.style.strokeDashoffset = `${len}`;
  }
}

function show(paths) {
  for (const p of paths) {
    p.style.strokeDasharray = "";
    p.style.strokeDashoffset = "";
  }
}

/** Keep the nib on the tip of the line being drawn. */
function follow(nib, path, anim) {
  if (!nib) return;
  const start = path.getPointAtLength(0);
  nib.setAttribute("cx", start.x);
  nib.setAttribute("cy", start.y);
  nib.classList.add("is-on");
  const tick = () => {
    if (anim.playState !== "running") return;
    const off = parseFloat(getComputedStyle(path).strokeDashoffset) || 0;
    const at = path.getPointAtLength(Math.max(0, path.__len - off));
    nib.setAttribute("cx", at.x);
    nib.setAttribute("cy", at.y);
    requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
}

/** Write strokes one after another. `speed` is page units per millisecond. */
async function write(paths, { speed = 1.2, nib = null, signal, lift = 55 } = {}) {
  if (!paths.length) return;
  if (reduce) return show(paths);
  prime(paths);
  for (let i = 0; i < paths.length; i++) {
    if (signal?.aborted) break;
    const p = paths[i];
    const anim = p.animate(
      [{ strokeDashoffset: p.__len }, { strokeDashoffset: 0 }],
      { duration: Math.max(70, p.__len / speed), easing: "cubic-bezier(.4,.08,.5,1)", fill: "forwards" },
    );
    follow(nib, p, anim);
    signal?.addEventListener("abort", () => anim.finish(), { once: true });
    await anim.finished.catch(() => {});
    p.style.strokeDashoffset = "0";
    // The pen lifts and travels to the start of the next stroke.
    const next = paths[i + 1];
    if (next) {
      const a = p.getPointAtLength(p.__len);
      const b = next.getPointAtLength(0);
      await wait(Math.min(lift * 4, lift + Math.hypot(b.x - a.x, b.y - a.y) / 6), signal);
    }
  }
  nib?.classList.remove("is-on");
}

/** Rub strokes out, last written first, the way an eraser pass reads. */
async function rubOut(paths) {
  if (!paths.length) return;
  if (reduce) return paths.forEach((p) => p.remove());
  const n = paths.length;
  const anims = paths.map((p, i) =>
    p.animate([{ opacity: 1 }, { opacity: 0 }], {
      duration: 520, delay: (n - 1 - i) * Math.min(14, 700 / n), easing: "ease-in", fill: "forwards",
    }),
  );
  await Promise.all(anims.map((a) => a.finished.catch(() => {})));
  paths.forEach((p) => p.remove());
}

/** The green line under the page that fills while nothing is written. */
function pauseClock(el, signal) {
  const bar = el.querySelector("span");
  el.classList.add("is-on");
  const anim = bar.animate([{ transform: "scaleX(0)" }, { transform: "scaleX(1)" }], {
    duration: reduce ? 0 : PAUSE_MS, easing: "linear", fill: "forwards",
  });
  const off = () => { el.classList.remove("is-on"); anim.cancel(); };
  signal?.addEventListener("abort", off, { once: true });
  return anim.finished.then(off, off);
}

function ruleLines(group) {
  for (let y = 300; y < 1780; y += 118) {
    const l = document.createElementNS(NS, "line");
    l.setAttribute("x1", 110); l.setAttribute("x2", 1300);
    l.setAttribute("y1", y); l.setAttribute("y2", y);
    group.appendChild(l);
  }
}

class Page {
  constructor(root) {
    this.svg = root.querySelector("svg.page");
    this.you = this.svg.querySelector(".ink-you");
    this.diary = this.svg.querySelector(".ink-diary");
    this.nib = this.svg.querySelector(".nib");
    this.clock = root.querySelector(".pause-clock");
    ruleLines(this.svg.querySelector(".rules"));
  }
  ink(group) { return [...group.querySelectorAll("path")]; }
  clearNow() {
    for (const g of [this.you, this.diary]) g.replaceChildren();
    this.diary.removeAttribute("transform");
    this.nib.removeAttribute("transform");
    this.nib.classList.remove("is-on");
  }
}

/* ---------- the hero: a page that answers ---------- */

function hero(data) {
  const root = document.querySelector("[data-demo]");
  if (!root) return;
  const page = new Page(root);
  const caption = root.querySelector("[data-demo-caption]");
  const said = caption.textContent;
  let loop = null;       // the demo playing by itself
  let idle = null;       // the three seconds after somebody wrote
  let resume = null;     // going back to playing by itself
  let visible = false;
  let touched = false;

  const play = async (signal) => {
    let i = 0;
    if (reduce) {
      addPaths(page.you, data.pairs[0].question).forEach((p) => (p.style.opacity = 0.3));
      addPaths(page.diary, data.pairs[0].answer);
      return;
    }
    await wait(700, signal);
    while (!signal.aborted) {
      const pair = data.pairs[i++ % data.pairs.length];
      const q = addPaths(page.you, pair.question);
      await write(q, { speed: 2.1, signal });
      if (signal.aborted) break;
      await pauseClock(page.clock, signal);
      if (signal.aborted) break;
      await rubOut(q);
      const a = addPaths(page.diary, pair.answer);
      await write(a, { speed: 1.25, nib: page.nib, signal });
      await wait(4200, signal);
      if (signal.aborted) break;
      await rubOut(a);
      await wait(900, signal);
    }
  };

  const start = () => {
    if (loop || touched || !visible) return;
    page.clearNow();
    loop = new AbortController();
    play(loop.signal);
  };
  const stop = () => { loop?.abort(); loop = null; };

  new IntersectionObserver(([e]) => {
    visible = e.isIntersecting;
    visible ? start() : stop();
  }, { threshold: 0.35 }).observe(root);
  document.addEventListener("visibilitychange", () => (document.hidden ? stop() : start()));

  // Somebody writes on it.
  const svg = page.svg;
  let current = null;
  let pts = [];
  const toPage = (e) => {
    const m = svg.getScreenCTM().inverse();
    const p = new DOMPoint(e.clientX, e.clientY).matrixTransform(m);
    return [Math.round(p.x * 10) / 10, Math.round(p.y * 10) / 10];
  };

  svg.addEventListener("pointerdown", (e) => {
    if (e.button > 0) return;
    e.preventDefault();
    svg.setPointerCapture(e.pointerId);
    idle?.abort(); resume?.abort();
    if (!touched || loop) {
      stop();
      page.clearNow();
    }
    touched = true;
    // An answer still on the page goes the moment the pen comes back.
    page.nib.classList.remove("is-on");
    rubOut(page.ink(page.diary)).then(() => {
      page.diary.removeAttribute("transform");
      page.nib.removeAttribute("transform");
    });
    caption.textContent = "Keep going, or stop for three seconds.";
    pts = [toPage(e)];
    current = document.createElementNS(NS, "path");
    current.setAttribute("d", pathData(pts.concat([pts[0]])));
    page.you.appendChild(current);
  });

  svg.addEventListener("pointermove", (e) => {
    if (!current) return;
    for (const ev of e.getCoalescedEvents?.() ?? [e]) pts.push(toPage(ev));
    current.setAttribute("d", pathData(pts));
  });

  const lift = async () => {
    if (!current) return;
    current = null;
    idle = new AbortController();
    const signal = idle.signal;
    await pauseClock(page.clock, signal);
    if (signal.aborted) return;
    const mine = page.ink(page.you);
    const lowest = Math.max(...mine.map((p) => p.getBBox()).map((b) => b.y + b.height));
    await rubOut(mine);
    if (signal.aborted) return;
    const reply = data.scribble[Math.floor(Math.random() * data.scribble.length)];
    // Under what was written, where the loop would put it; above it if the
    // page has run out.
    const ys = reply.answer.flatMap((line) => line.map(([, y]) => y));
    const top = Math.min(...ys);
    const tall = Math.max(...ys) - top;
    // Your writing has been rubbed out by now, so it goes just under where
    // it was, as far down as the page allows.
    const at = Math.min(Math.max(lowest + 110, 200), 1780 - tall);
    const shift = `translate(0 ${Math.round(at - top)})`;
    page.diary.setAttribute("transform", shift);
    page.nib.setAttribute("transform", shift); // the nib rides with the ink
    await write(addPaths(page.diary, reply.answer), { speed: 1.25, nib: page.nib, signal });
    caption.textContent = "A demo: this page cannot read you. The tablet can.";
    resume = new AbortController();
    await wait(9000, resume.signal);
    if (resume.signal.aborted) return;
    await rubOut(page.ink(page.diary));
    caption.textContent = said;
    touched = false;
    start();
  };
  svg.addEventListener("pointerup", lift);
  svg.addEventListener("pointercancel", lift);
}

/* ---------- the story: one page held still while the steps pass ---------- */

function story(data) {
  const stage = document.querySelector("[data-story-stage]");
  if (!stage) return;
  const page = new Page(stage);
  const pair = data.pairs[2];
  const steps = [...document.querySelectorAll(".story-steps [data-step]")];
  let run = null;
  let shown = null;

  const go = async (step) => {
    if (step === shown) return;
    shown = step;
    run?.abort();
    run = new AbortController();
    const signal = run.signal;
    page.clearNow();
    if (step === "write") {
      await write(addPaths(page.you, pair.question), { speed: 2, signal });
    } else if (step === "stop") {
      const q = addPaths(page.you, pair.question);
      show(q);
      await wait(250, signal);
      await pauseClock(page.clock, signal);
      if (!signal.aborted) await rubOut(q);
    } else {
      await write(addPaths(page.diary, pair.answer), { speed: 1.2, nib: page.nib, signal });
    }
  };

  if (reduce) {
    addPaths(page.diary, pair.answer);
    steps.forEach((s) => s.classList.add("is-active"));
    return;
  }
  const io = new IntersectionObserver((entries) => {
    for (const e of entries) {
      if (!e.isIntersecting) continue;
      steps.forEach((s) => s.classList.toggle("is-active", s === e.target));
      go(e.target.dataset.step);
    }
  }, { rootMargin: "-45% 0px -45% 0px" });
  steps.forEach((s) => io.observe(s));
}

/* ---------- lines drawn when they come into view ---------- */

function wordmarks(data) {
  const w = data.wordmark;
  for (const svg of document.querySelectorAll("[data-wordmark]")) {
    const pad = w.nib / 2;
    svg.setAttribute("viewBox", `${-pad} ${-pad} ${w.width + w.nib} ${w.height + w.nib}`);
    const g = document.createElementNS(NS, "g");
    g.setAttribute("stroke-width", w.nib);
    svg.appendChild(g);
    const paths = addPaths(g, w.strokes);
    const speed = Number(svg.dataset.speed || 0.5);
    if (svg.hasAttribute("data-on-view")) {
      prime(paths);
      once(svg, () => write(paths, { speed }));
    } else {
      write(paths, { speed });
    }
  }
}

function lines(data) {
  for (const svg of document.querySelectorAll("[data-line]")) {
    const line = data.lines[svg.dataset.line];
    if (!line) continue;
    svg.setAttribute("viewBox", `0 0 ${line.w} ${line.h}`);
    const paths = addPaths(svg, line.strokes);
    prime(paths);
    if (reduce) show(paths);
    once(svg, () => write(paths, { speed: Number(svg.dataset.speed || 0.9), lift: 18 }), 0.5);
  }
}

function once(el, fn, threshold = 0.35) {
  const io = new IntersectionObserver(([e]) => {
    if (!e.isIntersecting) return;
    io.disconnect();
    fn();
  }, { threshold });
  io.observe(el);
}

/* ---------- small things ---------- */

function reveals() {
  const io = new IntersectionObserver((entries) => {
    for (const e of entries) {
      if (!e.isIntersecting) continue;
      e.target.classList.add("is-in");
      io.unobserve(e.target);
    }
  }, { threshold: 0.12, rootMargin: "0px 0px -8% 0px" });
  document.querySelectorAll(".reveal").forEach((el) => io.observe(el));

  // Loops only run while they can be seen.
  const live = new IntersectionObserver((entries) => {
    for (const e of entries) e.target.classList.toggle("is-inview", e.isIntersecting);
  }, { threshold: 0.2 });
  document.querySelectorAll("[data-inview]").forEach((el) => live.observe(el));
}

function nav() {
  const bar = document.querySelector("[data-nav]");
  const mark = document.createElement("div");
  mark.style.cssText = "position:absolute;top:0;height:1px;width:1px;";
  document.body.prepend(mark);
  new IntersectionObserver(([e]) => bar.classList.toggle("is-stuck", !e.isIntersecting)).observe(mark);
}

function buttons() {
  // The fill spreads from where the pointer came in.
  for (const b of document.querySelectorAll(".btn")) {
    b.addEventListener("pointerenter", (e) => {
      const r = b.getBoundingClientRect();
      b.style.setProperty("--x", `${e.clientX - r.left}px`);
      b.style.setProperty("--y", `${e.clientY - r.top}px`);
    });
  }
  const copy = document.querySelector("[data-copy]");
  copy?.addEventListener("click", async () => {
    const text = document.querySelector("[data-copy-source]").textContent
      .split("\n").filter((l) => l.trim() && !l.trim().startsWith("#")).join("\n");
    try {
      await navigator.clipboard.writeText(text);
      copy.classList.add("is-done");
      copy.querySelector("[data-copy-label]").textContent = "Copied";
      copy.querySelector("[data-copy-icon]").setAttribute("href", "#i-check");
      setTimeout(() => {
        copy.classList.remove("is-done");
        copy.querySelector("[data-copy-label]").textContent = "Copy";
        copy.querySelector("[data-copy-icon]").setAttribute("href", "#i-copy");
      }, 2000);
    } catch {
      copy.querySelector("[data-copy-label]").textContent = "Select and copy";
    }
  });
}

nav();
reveals();
buttons();
fetch("/assets/strokes.json")
  .then((r) => r.json())
  .then((data) => {
    wordmarks(data);
    lines(data);
    hero(data);
    story(data);
  })
  .catch(() => {
    // Without the strokes the page is still the page; only the ink is missing.
    document.querySelector("[data-demo-caption]")?.remove();
  });
