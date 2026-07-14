const state = { package: null, graph: null, nodes: [], filter: "all" };

const el = (id) => document.getElementById(id);
const number = (value, digits = 0) => Number(value || 0).toLocaleString(undefined, { maximumFractionDigits: digits });

async function api(path, options) {
  const response = await fetch(path, options);
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || `Request failed with status ${response.status}`);
  }
  return response.json();
}

async function loadStatus() {
  const status = await api("/api/status");
  el("repo-name").textContent = status.repository.split("/").pop();
  el("index-count").textContent = `${number(status.files)} files · ${number(status.units)} units`;
}

el("budget").addEventListener("input", (event) => {
  el("budget-output").textContent = number(event.target.value);
});

el("compile-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = el("compile-button");
  const original = button.innerHTML;
  button.disabled = true;
  button.innerHTML = "<span>Forging context…</span><span>•••</span>";
  try {
    const result = await api("/api/compile", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ task: el("task").value, token_budget: Number(el("budget").value) }),
    });
    state.package = result;
    state.graph = await api("/api/graph");
    render(result);
    el("results").classList.remove("is-hidden");
    el("empty-state").classList.add("is-hidden");
    el("results").scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (error) {
    button.innerHTML = `<span>${error.message}</span><span>!</span>`;
    await new Promise((resolve) => setTimeout(resolve, 2200));
  } finally {
    button.disabled = false;
    button.innerHTML = original;
  }
});

function render(pkg) {
  const selected = pkg.decisions.filter((decision) => decision.selected).length;
  const rejected = pkg.decisions.length - selected;
  const totalLatency = pkg.timings.reduce((sum, timing) => sum + timing.elapsed_ms, 0);
  const tests = pkg.items.filter((item) => item.is_test).length;
  el("metrics").innerHTML = [
    ["Evidence selected", selected, `${rejected} rejected`],
    ["Graph expansions", pkg.graph_expansion_count, `${pkg.initial_anchor_ids.length} anchors`],
    ["Validation ranges", tests, tests ? "tests represented" : "none selected"],
    ["Compile latency", `${number(totalLatency, 1)} ms`, `${pkg.timings.length} stages`],
  ].map(([label, value, detail]) => `<div class="metric"><span>${label}</span><strong>${value}</strong><small>${detail}</small></div>`).join("");

  el("route-type").textContent = pkg.routing.task_type.replaceAll("_", " ");
  el("route-reason").textContent = pkg.routing.reasoning_summary;
  el("route-sources").replaceChildren(...pkg.routing.selected_sources.map((source) => {
    const chip = document.createElement("span"); chip.className = "chip"; chip.textContent = source; return chip;
  }));
  el("evolution").textContent = pkg.query_evolution?.derived_concepts?.join(" · ") || "No additional concepts";

  const percentage = Math.min(100, (pkg.estimated_tokens / pkg.token_budget) * 100);
  el("budget-percent").textContent = `${number(percentage, 1)}%`;
  el("tokens-used").textContent = number(pkg.estimated_tokens);
  el("budget-ring").style.background = `conic-gradient(var(--orange) ${percentage}%, rgba(255,255,255,.07) ${percentage}%)`;

  el("candidate-count").textContent = `${pkg.decisions.length} considered`;
  renderCandidates();
  renderEvidence(pkg.items);
  renderCommits(pkg.relevant_commits);
  renderTimings(pkg.timings);
  renderGraph();
}

function renderCandidates() {
  const decisions = state.package.decisions.filter((decision) => state.filter === "all" || (state.filter === "selected") === decision.selected);
  const container = el("candidate-list");
  container.replaceChildren(...decisions.map((decision) => {
    const row = document.createElement("div"); row.className = "candidate-row";
    row.innerHTML = `<div class="candidate-score">${decision.score.toFixed(3)}</div><div class="candidate-symbol"><strong></strong><span></span></div><div class="candidate-reason"></div><div class="candidate-status ${decision.selected ? "selected" : "rejected"}">${decision.selected ? "● selected" : "○ rejected"}</div>`;
    row.querySelector("strong").textContent = decision.symbol;
    row.querySelector(".candidate-symbol span").textContent = `${decision.file} · ${number(decision.estimated_tokens)} tok`;
    row.querySelector(".candidate-reason").textContent = decision.reason;
    return row;
  }));
}

document.querySelectorAll(".candidate-tabs button").forEach((button) => button.addEventListener("click", () => {
  document.querySelectorAll(".candidate-tabs button").forEach((item) => item.classList.remove("active"));
  button.classList.add("active"); state.filter = button.dataset.filter; renderCandidates();
}));

function renderEvidence(items) {
  const container = el("evidence-list");
  container.replaceChildren(...items.map((item) => {
    const card = document.createElement("article"); card.className = "evidence-card";
    card.innerHTML = `<div class="evidence-meta"><div><strong></strong><span></span></div><b>${item.score.toFixed(3)}</b></div><div class="evidence-why"></div><pre><code></code></pre>`;
    card.querySelector("strong").textContent = item.symbol;
    card.querySelector(".evidence-meta span").textContent = `${item.file}:${item.start_line}–${item.end_line} · ${item.retrieved_by.join(", ")}`;
    card.querySelector(".evidence-why").textContent = item.why_selected;
    card.querySelector("code").textContent = item.content;
    return card;
  }));
}

function renderCommits(commits) {
  el("commit-count").textContent = commits.length;
  const container = el("commit-list");
  if (!commits.length) { container.className = "empty-state"; container.textContent = "No historical patch passed the confidence gate."; return; }
  container.className = "";
  container.replaceChildren(...commits.map((commit) => {
    const item = document.createElement("div"); item.className = "commit";
    item.innerHTML = `<strong></strong><p></p>`;
    item.querySelector("strong").textContent = `${commit.commit_hash.slice(0, 10)} / ${commit.message}`;
    item.querySelector("p").textContent = commit.reasons.join(" · "); return item;
  }));
}

function renderTimings(timings) {
  const total = timings.reduce((sum, timing) => sum + timing.elapsed_ms, 0);
  const maximum = Math.max(...timings.map((timing) => timing.elapsed_ms), 1);
  el("total-latency").textContent = `${number(total, 1)} ms`;
  el("timing-list").innerHTML = timings.map((timing) => `<div class="timing"><span>${timing.stage.replaceAll("_", " ")}</span><div class="timing-bar"><i style="width:${(timing.elapsed_ms / maximum) * 100}%"></i></div><b>${number(timing.elapsed_ms, 1)} ms</b></div>`).join("");
}

function renderGraph() {
  const canvas = el("graph-canvas"); const graph = state.graph;
  if (!graph) return;
  const ratio = window.devicePixelRatio || 1; const rect = canvas.getBoundingClientRect();
  canvas.width = rect.width * ratio; canvas.height = rect.height * ratio;
  const ctx = canvas.getContext("2d"); ctx.scale(ratio, ratio); ctx.clearRect(0, 0, rect.width, rect.height);
  const visible = graph.nodes.filter((node) => !["directory", "repository"].includes(node.type) || node.selected || node.anchor);
  const cx = rect.width / 2; const cy = rect.height / 2; const radius = Math.min(rect.width, rect.height) * .39;
  const positions = new Map();
  visible.forEach((node, index) => {
    const angle = (index / Math.max(1, visible.length)) * Math.PI * 2 - Math.PI / 2;
    const layer = node.selected || node.anchor ? .58 : .82 + (index % 3) * .08;
    positions.set(node.id, { x: cx + Math.cos(angle) * radius * layer, y: cy + Math.sin(angle) * radius * layer, node });
  });
  ctx.lineWidth = .65;
  graph.edges.forEach((edge) => { const a = positions.get(edge.source); const b = positions.get(edge.target); if (!a || !b) return; ctx.strokeStyle = `rgba(151,160,163,${.08 + edge.confidence * .15})`; ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke(); });
  positions.forEach(({ x, y, node }) => {
    const size = node.selected ? 7 : node.anchor ? 6 : node.type === "file" ? 4 : 2.8;
    ctx.fillStyle = node.selected ? "#ff5a36" : node.anchor ? "#c9f44f" : node.type === "test" ? "#a48af2" : "#65d5e4";
    ctx.beginPath(); ctx.arc(x, y, size, 0, Math.PI * 2); ctx.fill();
    if (node.selected || node.anchor) { ctx.fillStyle = "rgba(239,237,229,.82)"; ctx.font = "9px SFMono-Regular, monospace"; ctx.fillText(node.label.split(".").pop().slice(0, 24), x + 10, y + 3); }
  });
  state.nodes = [...positions.values()]; el("graph-count").textContent = `${visible.length} nodes · ${graph.edges.length} edges`;
}

el("graph-canvas").addEventListener("mousemove", (event) => {
  const rect = event.target.getBoundingClientRect(); const x = event.clientX - rect.left; const y = event.clientY - rect.top;
  const closest = state.nodes.find((item) => Math.hypot(item.x - x, item.y - y) < 12);
  el("graph-tooltip").textContent = closest ? `${closest.node.type.toUpperCase()} / ${closest.node.label}${closest.node.path ? ` / ${closest.node.path}` : ""}` : "Hover a node to inspect its repository identity.";
});

window.addEventListener("resize", () => { if (state.graph) renderGraph(); });
loadStatus().catch((error) => { el("repo-name").textContent = error.message; });

