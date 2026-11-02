// Exhibit E: every hand from the back room merged into one tree.
//
// Lines come from the server already tokenised ("UTG R3", "FLOP", ..., "SD").
// The book keeps the last 10,000 and counts hands through each node. What gets
// drawn is picked best-first so the busiest line runs straight across like a
// chess opening book, and side lines hang off it below.

import { $, svg, fmt, miniCard } from "./util.js";

const WINDOW = 10000;
const CHANCE = new Set(["FLOP", "TURN", "RIVER"]);
const LEAF = new Set(["SD", "END"]);
const PER_SEC = { 1: 2, 4: 8, 8: 30, 16: Infinity };

// ---------------------------------------------------------------- the trie

function node(tok, parent) {
  return {
    tok, parent, key: parent ? parent.key + "/" + tok : "",
    depth: parent ? parent.depth + 1 : 0,
    count: 0, sd: 0, pot: 0, folds: 0, kids: new Map(),
  };
}

class Book {
  constructor(by) {
    this.by = by;
    this.root = node("", null);
    this.window = [];
    this.folds = 0;
    this.lines = 0;
  }

  apply(rec, s) {
    const toks = rec[this.by];
    let n = this.root;
    for (let k = 0; ; k++) {
      n.count += s;
      n.pot += s * rec.pot;
      n.sd += s * (rec.sd ? 1 : 0);
      n.folds += s * (rec.f[k] || 0);
      this.folds += s * (rec.f[k] || 0);
      if (k === toks.length) break;
      let c = n.kids.get(toks[k]);
      if (!c) {
        c = node(toks[k], n);
        n.kids.set(toks[k], c);
        if (LEAF.has(toks[k])) this.lines++;
      }
      if (s < 0 && c.count === 1) {
        // last hand through here, the whole branch goes
        n.kids.delete(toks[k]);
        this.lines -= countLeaves(c);
        for (let j = k + 1; j < rec.f.length; j++) this.folds -= rec.f[j] || 0;
        break;
      }
      n = c;
    }
  }

  add(rec) {
    this.window.push(rec);
    this.apply(rec, 1);
    if (this.window.length > WINDOW) this.apply(this.window.shift(), -1);
  }

  pop() {
    const rec = this.window.pop();
    if (rec) this.apply(rec, -1);
    return rec;
  }
}

function countLeaves(n) {
  if (LEAF.has(n.tok)) return 1;
  let s = 0;
  for (const c of n.kids.values()) s += countLeaves(c);
  return s;
}

const byCount = (a, b) => b.count - a.count || (a.tok < b.tok ? -1 : 1);

// ---------------------------------------------------------------- what to draw

function pick(root, P) {
  const total = root.count;
  const min = Math.max(1, Math.ceil(total * 0.004));
  const shown = new Map();   // node -> visible kids (sorted)
  const heap = [root];
  let rows = 1;
  const weight = n => n.count * Math.pow(P.deep, n.depth);
  while (heap.length) {
    let bi = 0;
    for (let i = 1; i < heap.length; i++) if (weight(heap[i]) > weight(heap[bi])) bi = i;
    const n = heap[bi];
    heap[bi] = heap[heap.length - 1];
    heap.pop();
    if (n.depth >= P.maxDepth || !n.kids.size || n.count < min) continue;
    // the wall gets more room: the first action is the most interesting split
    const cap = n.depth === 0 ? P.maxKids + 2 : P.maxKids;
    const kids = [...n.kids.values()].sort(byCount).filter(c => c.count >= min).slice(0, cap);
    // the first kid continues the row for free, every other kid costs one
    const take = [];
    for (const c of kids) {
      if (take.length && rows >= P.rows) break;
      if (take.length) rows++;
      take.push(c);
    }
    if (!take.length) continue;
    shown.set(n, take);
    heap.push(...take);
  }
  return shown;
}

function place(root, shown, P) {
  const items = [];
  const walk = (n, row) => {
    const kids = shown.get(n) || [];
    const item = { n, row, x: P.x0 + n.depth * P.colW, y: P.top + row * P.rowH, hidden: n.kids.size - kids.length };
    items.push(item);
    let r = row;
    kids.forEach((c, i) => {
      const sub = walk(c, i === 0 ? row : r + 1);
      sub.parent = item;
      r = sub.last;
    });
    item.last = r;
    return item;
  };
  walk(root, 0);
  return items;
}

// ---------------------------------------------------------------- drawing

const POS = { BTN: "BUTTON", SB: "SMALL BLIND", BB: "BIG BLIND", UTG: "UTG", UTG1: "UTG+1", MP: "MIDDLE", HJ: "HIJACK", CO: "CUTOFF" };

function words(tok) {
  if (CHANCE.has(tok)) return tok;
  if (tok === "SD") return "SHOWDOWN";
  if (tok === "END") return "THE REST FOLD";
  const i = tok.lastIndexOf(" ");
  const who = POS[tok.slice(0, i)] || tok.slice(0, i);
  const a = tok.slice(i + 1);
  if (a === "X") return who + " CHECKS";
  if (a === "C") return who + " CALLS";
  if (a === "A") return who + " ALL-IN";
  if (a === "R") return who + " RAISES";
  if (a === "R6+") return who + " RAISES TO 6+ BB";
  if (a[0] === "R") return `${who} RAISES TO ${a.slice(1)} BB`;
  return who + " BETS " + { "B½": "HALF POT", B1: "POT", "B2+": "2X POT OR MORE" }[a];
}

const sharePct = s => (s >= 0.995 ? "100%" : s >= 0.01 ? Math.round(s * 100) + "%" : "<1%");

export function createBookView() {
  const fig = $("bk-fig"), root = $("bk-tree");
  const gE = svg("g", {}, root), gN = svg("g", {}, root), gT = svg("g", {}, root);
  const wall = svg("g", { class: "wall" }, root);
  svg("path", { d: "M0,-16V16M0,-14l-6,6M0,-8l-6,6M0,-2l-6,6M0,4l-6,6M0,10l-6,6" }, wall);
  const wallN = svg("text", { x: -10, y: -2, "text-anchor": "end" }, wall);
  svg("text", { x: -10, y: 10, "text-anchor": "end" }, wall).textContent = "HANDS";

  let by = "p";
  let book = new Book(by);
  let queue = [];
  let paused = false, speed = 16, added = 0, lastRec = null;
  let P = null;
  const recs = new Map();  // node key -> drawn record

  function measure() {
    const w = fig.clientWidth || 600;
    const narrow = w < 560;
    const x0 = narrow ? 48 : 56;
    const minCol = narrow ? 64 : 74;
    const maxDepth = Math.max(6, Math.min(12, Math.floor((w - x0 - 50) / minCol)));
    const colW = Math.floor((w - x0 - 50) / maxDepth);
    // 26px rows: label above the branch, share below it, and neither touches the next row
    const rows = narrow ? 18 : 22, rowH = narrow ? 24 : 26, top = 22;
    const W = x0 + maxDepth * colW + 50, H = top + rows * rowH;
    P = { x0, colW: Math.max(colW, minCol), maxDepth, rows, rowH, top, W, H, fs: narrow ? 9 : 10, deep: 2.1, maxKids: 4 };
    root.setAttribute("width", W);
    root.setAttribute("height", H);
    root.setAttribute("viewBox", `0 0 ${W} ${H}`);
    wall.setAttribute("transform", `translate(${x0},${top})`);
  }

  function makeRec(it) {
    const r = { key: it.n.key, x: 0, y: 0, a: 0, tx: 0, ty: 0, ta: 1, it };
    r.e = svg("path", { class: "e" }, gE);
    r.more = svg("path", { class: "more" }, gE);
    r.g = svg("g", {}, gN);
    r.mark = svg("circle", { class: "dot", r: 2.5 }, r.g);
    r.box = svg("rect", { class: "bx", x: -2.5, y: -5, width: 5, height: 10 }, r.g);
    r.t = svg("g", {}, gT);
    r.title = svg("title", {}, r.t);
    r.lb = svg("rect", { class: "lb" }, r.t);
    r.lt = svg("text", { class: "lt", "text-anchor": "end" }, r.t);
    r.pc = svg("text", { class: "pc", "text-anchor": "end" }, r.t);
    r.ct = svg("text", { class: "ct" }, r.t);
    r.mt = svg("text", { class: "mt" }, r.t);
    return r;
  }

  function dress(r) {
    const { n, parent, hidden } = r.it;
    const isRoot = !parent;
    const leaf = LEAF.has(n.tok);
    const chance = CHANCE.has(n.tok);
    const show = (e, on) => e.setAttribute("display", on ? "inline" : "none");
    show(r.e, !isRoot); show(r.t, !isRoot); show(r.g, !isRoot);
    show(r.mark, !leaf); show(r.box, leaf);
    r.mark.setAttribute("class", chance ? "ch" : "dot");
    r.mark.setAttribute("r", chance ? 3.5 : 2.5);
    r.box.setAttribute("class", "bx" + (n.tok === "SD" ? " sd" : ""));
    if (isRoot) { wallN.textContent = fmt(n.count); return; }

    const fs = P.fs, cw = fs * 0.6;
    const label = n.tok === "SD" ? "SHOWDOWN" : n.tok === "END" ? "FOLDED" : n.tok;
    r.lt.textContent = label;
    r.lt.setAttribute("font-size", fs);
    r.lt.setAttribute("x", -6);
    r.lt.setAttribute("y", -4);
    r.lb.setAttribute("x", -6 - label.length * cw - 2);
    r.lb.setAttribute("y", -4 - fs + 1);
    r.lb.setAttribute("width", label.length * cw + 4);
    r.lb.setAttribute("height", fs + 2);
    r.pc.textContent = sharePct(n.count / parent.n.count);
    r.pc.setAttribute("x", -6);
    r.pc.setAttribute("y", 11);
    r.ct.textContent = leaf ? fmt(n.count) : "";
    r.ct.setAttribute("x", 6);
    r.ct.setAttribute("y", 3.5);
    r.ct.setAttribute("font-size", fs);
    // hidden branches: a dotted stub where the line stops, or a note under the
    // branch where it carries on, so it never sits on top of the line
    const cut = !leaf && n.kids.size > 0 && hidden === n.kids.size;
    r.mt.textContent = hidden > 0 && !leaf ? `+${hidden}` : "";
    r.mt.setAttribute("x", cut ? 22 : 6);
    r.mt.setAttribute("y", cut ? 3 : 11);
    r.cut = cut;
    show(r.more, cut);
    const sd = n.count ? Math.round((100 * n.sd) / n.count) : 0;
    r.title.textContent = `${words(n.tok)}: ${fmt(n.count)} hands, ${sd}% reach showdown, ` +
      `average pot ${fmt(n.pot / Math.max(n.count, 1))}, ${fmt(n.folds)} folds here`;
    r.e.setAttribute("stroke-width", (0.8 + 3.2 * Math.sqrt(n.count / book.root.count)).toFixed(2));
  }

  function rebuild() {
    const shown = pick(book.root, P);
    const items = place(book.root, shown, P);
    const keep = new Set();
    for (const it of items) {
      let r = recs.get(it.n.key);
      if (!r) {
        r = makeRec(it);
        const from = it.parent && recs.get(it.parent.n.key);
        r.x = from ? from.x : it.x;
        r.y = from ? from.y : it.y;
        r.a = from ? 0 : 1;
        recs.set(it.n.key, r);
      }
      r.it = it;
      r.tx = it.x; r.ty = it.y; r.ta = 1; r.dying = false;
      dress(r);
      keep.add(it.n.key);
    }
    for (const [k, r] of recs) {
      if (keep.has(k)) continue;
      r.dying = true;
      r.ta = 0;
      const p = r.it.parent && recs.get(r.it.parent.n.key);
      if (p && !p.dying) { r.tx = p.tx; r.ty = p.ty; }
    }
    highlight();
    readouts();
    moving = true;
    kick();
  }

  function highlight() {
    const on = new Set();
    if (lastRec) {
      let key = "";
      for (const tok of lastRec[by]) {
        key += "/" + tok;
        on.add(key);
      }
    }
    for (const r of recs.values()) r.t.classList.toggle("hl", on.has(r.key));
    for (const r of recs.values()) r.g.classList.toggle("hl", on.has(r.key));
  }

  // ---------------------------------------------------------------- motion

  let moving = false, raf = 0, prevT = 0, carry = 0, lastBuild = 0, dirty = false;
  const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;

  function step(dt) {
    const k = reduce ? 1 : 1 - Math.exp(-dt / 120);
    let still = true;
    for (const [key, r] of recs) {
      r.x += (r.tx - r.x) * k;
      r.y += (r.ty - r.y) * k;
      r.a += (r.ta - r.a) * k;
      if (Math.abs(r.tx - r.x) > 0.3 || Math.abs(r.ty - r.y) > 0.3 || Math.abs(r.ta - r.a) > 0.02) still = false;
      else { r.x = r.tx; r.y = r.ty; r.a = r.ta; }
      if (r.dying && r.a < 0.03) {
        r.e.remove(); r.more.remove(); r.g.remove(); r.t.remove();
        recs.delete(key);
        continue;
      }
      const tr = `translate(${r.x.toFixed(1)},${r.y.toFixed(1)})`;
      r.g.setAttribute("transform", tr + ` scale(${Math.max(r.a, 0.01).toFixed(2)})`);
      r.t.setAttribute("transform", tr);
      r.t.setAttribute("opacity", r.a.toFixed(2));
      r.e.setAttribute("opacity", r.a.toFixed(2));
      const p = r.it.parent && recs.get(r.it.parent.n.key);
      if (p) r.e.setAttribute("d", rail(p.x, p.y, r.x, r.y));
      r.more.setAttribute("d", `M${r.x + 4},${r.y}h14`);
    }
    return still;
  }

  // a branch drops straight down a rail just right of its parent, then turns into its row
  function rail(px, py, cx, cy) {
    if (Math.abs(cy - py) < 0.5) return `M${px.toFixed(1)},${py.toFixed(1)}H${cx.toFixed(1)}`;
    const rx = px + 10, rr = Math.min(8, Math.abs(cy - py) / 2), s = cy > py ? 1 : -1;
    return `M${px.toFixed(1)},${py.toFixed(1)}H${(rx - rr).toFixed(1)}` +
      `Q${rx.toFixed(1)},${py.toFixed(1)} ${rx.toFixed(1)},${(py + s * rr).toFixed(1)}` +
      `V${(cy - s * rr).toFixed(1)}Q${rx.toFixed(1)},${cy.toFixed(1)} ${(rx + rr).toFixed(1)},${cy.toFixed(1)}H${cx.toFixed(1)}`;
  }

  function frame(t) {
    raf = 0;
    const dt = prevT ? Math.min(t - prevT, 100) : 16;
    prevT = t;
    if (!paused && queue.length) {
      const rate = PER_SEC[speed];
      carry += rate === Infinity ? queue.length : (rate * dt) / 1000;
      let n = Math.min(Math.floor(carry), 400);
      if (n > 0) {
        carry -= n;
        while (n-- > 0 && queue.length) addOne(queue.shift());
        dirty = true;
      }
    }
    if (dirty && t - lastBuild > (speed >= 8 ? 120 : 40)) {
      dirty = false;
      lastBuild = t;
      rebuild();
    }
    if (moving) moving = !step(dt);
    if (moving || dirty || (!paused && queue.length)) kick();
    else prevT = 0;
  }
  const kick = () => { if (!raf) raf = requestAnimationFrame(frame); };

  function addOne(rec) {
    book.add(rec);
    lastRec = rec;
    added++;
  }

  // ---------------------------------------------------------------- readouts

  function readouts() {
    $("bk-hands").textContent = fmt(added);
    $("bk-held").textContent = fmt(book.window.length);
    $("bk-lines").textContent = fmt(book.lines);
    $("bk-folds").textContent = fmt(book.folds);
    const main = [];
    for (let n = book.root; n.kids.size;) {
      n = [...n.kids.values()].sort(byCount)[0];
      main.push(words(n.tok));
    }
    $("bk-main").textContent = main.length ? main.join(", ") : " ";

    const r = lastRec;
    if (!r) return;
    $("bk-lastNo").textContent = `HAND ${String(r.n).padStart(6, "0")}, POT ${fmt(r.pot)}`;
    $("bk-lastRes").textContent = r.split ? "SPLIT POT" :
      `${r.wb} (${r.wp}) WINS ${fmt(r.amt)}` + (r.sd ? `, ${r.desc}` : "");
    const board = [...r.board, null, null, null, null, null].slice(0, 5);
    $("bk-board").replaceChildren(...board.map(miniCard));
    // nobody saw the winner's cards if everyone else folded
    $("bk-win").replaceChildren(...(r.sd ? r.wc : ["back", "back"]).map(miniCard));
    $("bk-line").textContent = r[by].map(words).join(", ");
  }

  // ---------------------------------------------------------------- controls

  const playBtn = $("bk-play");
  const speedBtns = [...playBtn.parentElement.querySelectorAll("[data-speed]")];
  const byBtns = [...document.querySelectorAll("#book [data-by]")];
  function sync() {
    playBtn.textContent = paused ? "[PLAY]" : "[PAUSE]";
    for (const b of speedBtns) b.setAttribute("aria-pressed", String(+b.dataset.speed === speed));
    for (const b of byBtns) b.setAttribute("aria-pressed", String(b.dataset.by === by));
  }
  playBtn.onclick = () => { paused = !paused; sync(); kick(); };
  for (const b of speedBtns) b.onclick = () => { speed = +b.dataset.speed; carry = 0; sync(); kick(); };
  $("bk-next").onclick = () => {
    paused = true;
    if (queue.length) addOne(queue.shift());
    sync(); rebuild();
  };
  $("bk-prev").onclick = () => {
    paused = true;
    const rec = book.pop();
    if (rec) { queue.unshift(rec); added = Math.max(0, added - 1); }
    lastRec = book.window[book.window.length - 1] || null;
    sync(); rebuild();
  };
  $("bk-first").onclick = () => {
    while (book.window.length) book.pop();
    lastRec = null;
    $("bk-lastNo").textContent = "NO HANDS YET";
    $("bk-lastRes").textContent = "";
    sync(); rebuild();
  };
  for (const b of byBtns) {
    b.onclick = () => {
      if (b.dataset.by === by) return;
      by = b.dataset.by;
      const old = book.window;
      book = new Book(by);
      for (const rec of old) book.add(rec);
      for (const r of recs.values()) { r.e.remove(); r.more.remove(); r.g.remove(); r.t.remove(); }
      recs.clear();
      sync(); rebuild();
    };
  }

  let lastW = 0;
  new ResizeObserver(() => {
    const w = fig.clientWidth;
    if (Math.abs(w - lastW) < 8) return;
    lastW = w;
    measure();
    rebuild();
  }).observe(fig);

  measure();
  sync();
  rebuild();

  return {
    // backlog: fold it in quietly, then animate from there on
    load(lines) {
      for (const rec of lines) book.add(rec);
      added = lines.length;
      lastRec = lines[lines.length - 1] || null;
      rebuild();
    },
    push(lines, hps) {
      queue.push(...lines);
      if (queue.length > 3000) queue.splice(0, queue.length - 3000);
      if (hps != null) $("bk-hps").textContent = hps.toFixed(1);
      kick();
    },
  };
}
