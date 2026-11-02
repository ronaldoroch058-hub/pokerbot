export const $ = id => document.getElementById(id);
export const fmt = n => Math.round(n).toLocaleString("en-US");
export const signed = x => (x > 0 ? "+" : x < 0 ? "−" : "") + Math.abs(x).toFixed(1);

const NS = "http://www.w3.org/2000/svg";
export function svg(tag, attrs, parent) {
  const e = document.createElementNS(NS, tag);
  for (const k in attrs || {}) e.setAttribute(k, attrs[k]);
  if (parent) parent.appendChild(e);
  return e;
}

function h(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text != null) e.textContent = text;
  return e;
}

// "Ah" -> rank over suit. ︎ keeps suits as text, not emoji
const SUIT = { s: "♠︎", h: "♥︎", d: "♦︎", c: "♣︎" };
const rankOf = c => (c[0] === "T" ? "10" : c[0]);

// one-line card for the readouts; "" is an empty slot, "back" a face-down card
export function miniCard(c) {
  const e = h("span", "cd mini");
  if (!c || c === "back") {
    e.classList.add(c ? "back" : "slot");
    e.textContent = "  ";
    return e;
  }
  e.append(rankOf(c), h("i", null, SUIT[c[1]]));
  return e;
}
