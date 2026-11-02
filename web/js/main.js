import { $, signed } from "./util.js";
import { createBookView } from "./book.js";

const get = path => fetch(path).then(r => r.json());
const book = createBookView();

function records(st) {
  for (const [name, s] of Object.entries(st.bots)) {
    const el = $("rec-" + name);
    if (el) el.textContent = s.hands ? `${signed(s.bb100)} BB/100` : "--";
  }
}

function connect() {
  const es = new EventSource("/api/stream");
  es.onopen = () => {
    $("conn").textContent = "CONNECTED, LIVE";
    get("/api/stats").then(records);
  };
  es.onerror = () => { $("conn").textContent = "RECONNECTING…"; };
  es.addEventListener("book", e => {
    const msg = JSON.parse(e.data);
    book.push(msg.lines, msg.hps);
  });
  es.addEventListener("stats", e => records(JSON.parse(e.data)));
}

async function boot() {
  const backlog = await get("/api/book");
  book.load(backlog.lines);
  connect();
}

boot().catch(err => {
  $("conn").textContent = "SERVER NOT RUNNING? " + err.message.toUpperCase();
});
