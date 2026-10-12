const log = document.getElementById("log");
const form = document.getElementById("form");
const input = document.getElementById("input");
const chips = document.getElementById("chips");

function bubble(text, who) {
  const div = document.createElement("div");
  div.className = "msg " + who;
  div.textContent = text;
  log.appendChild(div);
  log.scrollTop = log.scrollHeight;
  return div;
}

async function send(text) {
  bubble(text, "user");
  const pending = bubble("…", "bot");
  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({message: text}),
    });
    const data = await res.json();
    pending.textContent = data.response || data.detail || "Something went wrong.";
  } catch (e) {
    pending.textContent = "Could not reach the server. Is the backend running?";
  }
}

form.addEventListener("submit", (e) => {
  e.preventDefault();
  const text = input.value.trim();
  if (!text) return;
  input.value = "";
  send(text);
});

fetch("/api/examples")
  .then((r) => r.json())
  .then((ex) => {
    const all = [...(ex.customer || []), ...(ex.product || []), ...(ex.business || [])];
    all.slice(0, 6).forEach((q) => {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "chip";
      b.textContent = q;
      b.onclick = () => send(q);
      chips.appendChild(b);
    });
    bubble(
      "Hi! Ask me about a customer (e.g. “How much has customer C11111 spent in total?”), " +
      "a product (e.g. “Which stores sell the product A?”), or business metrics " +
      "(e.g. “What is the total revenue by category?”).",
      "bot"
    );
  })
  .catch(() => bubble("Hi! Type a question below to get started.", "bot"));
