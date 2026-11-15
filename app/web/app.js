"use strict";

const state = { articleId: null, article: null };

const $ = (id) => document.getElementById(id);

function escapeHtml(s) {
  return (s || "").replace(/[&<>"]/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])
  );
}

// Minimal Markdown -> HTML for the article body (headings + paragraphs).
function renderMarkdown(text) {
  const blocks = (text || "").split(/\n\n+/);
  const out = [];
  for (let block of blocks) {
    block = block.trim();
    if (!block) continue;
    const h = block.match(/^(#{1,4})\s+(.*)$/);
    if (h) {
      const level = Math.min(h[1].length + 1, 4); // # title shown separately
      out.push(`<h${level}>${escapeHtml(h[2])}</h${level}>`);
    } else {
      out.push(`<p>${escapeHtml(block)}</p>`);
    }
  }
  return out.join("\n");
}

async function loadArticles() {
  const res = await fetch("/api/articles");
  const articles = await res.json();
  const list = $("article-list");
  list.innerHTML = "";
  articles.forEach((a, i) => {
    const li = document.createElement("li");
    const link = document.createElement("a");
    link.href = "#";
    link.textContent = a.title;
    link.dataset.id = a.article_id;
    link.onclick = (e) => {
      e.preventDefault();
      document.querySelectorAll("#article-list a").forEach((x) => x.classList.remove("active"));
      link.classList.add("active");
      loadArticle(a.article_id);
    };
    li.appendChild(link);
    list.appendChild(li);
    if (i === 0) {
      link.classList.add("active");
      loadArticle(a.article_id);
    }
  });
}

async function loadArticle(id) {
  state.articleId = id;
  showRead();
  const res = await fetch(`/api/article/${id}`);
  const data = await res.json();
  state.article = data;
  // Strip a leading "# Title" line from the body (shown as the page title).
  let body = data.text || "";
  body = body.replace(/^#\s+.*\n/, "");
  $("article-title").textContent = data.title;
  $("read-view").innerHTML = renderMarkdown(body);
  $("edit-text").value = data.lead || "";
}

function showRead() {
  $("read-view").hidden = false;
  $("edit-view").hidden = true;
  $("tab-read").classList.add("active");
  $("tab-edit").classList.remove("active");
}
function showEdit() {
  $("read-view").hidden = true;
  $("edit-view").hidden = false;
  $("tab-edit").classList.add("active");
  $("tab-read").classList.remove("active");
}

function resetOverlay() {
  $("overlay-title").textContent = "WikiGuardian is verifying this edit…";
  $("overlay-sub").textContent = "Checking past data and real-world sources before publishing.";
  $("progress-log").innerHTML = "";
  const sig = $("signal-line");
  sig.hidden = true; sig.className = "";
  const v = $("verdict");
  v.hidden = true; v.className = ""; v.innerHTML = "";
  $("overlay-close").hidden = true;
}

function addProgress(message, cls) {
  const log = $("progress-log");
  // mark the previous step as done
  const prev = log.querySelector("li:last-child");
  if (prev && !prev.classList.contains("claim")) prev.classList.add("done");
  const li = document.createElement("li");
  if (cls) li.className = cls;
  li.textContent = message;
  log.appendChild(li);
}

function handleEvent(ev) {
  if (ev.type === "stage") {
    addProgress(ev.message);
  } else if (ev.type === "signal") {
    const sig = $("signal-line");
    sig.hidden = false;
    sig.className = ev.contested ? "contested" : "";
    sig.innerHTML =
      `&#128337; Past revisions: <b>${ev.versions}</b> versions, ` +
      `<b>${ev.reverts}</b> reverts — ` +
      (ev.contested ? "<b>CONTESTED</b> (edit-war signals)" : "routine activity") + ".";
  } else if (ev.type === "claim") {
    addProgress(
      `Claim: "${ev.claim}" → ${ev.verdict.replace(/_/g, " ")} ` +
      `(${Math.round(ev.confidence * 100)}%)`,
      "claim"
    );
  } else if (ev.type === "result") {
    showVerdict(ev);
  } else if (ev.type === "error") {
    showError(ev.message);
  } else if (ev.type === "done") {
    const log = $("progress-log");
    const prev = log.querySelector("li:last-child");
    if (prev && !prev.classList.contains("claim")) prev.classList.add("done");
    $("overlay-close").hidden = false;
  }
}

function showVerdict(ev) {
  const v = $("verdict");
  v.hidden = false;
  const rows = ev.decisions
    .map(
      (d) =>
        `<p><span class="badge ${d.verdict}">${d.verdict.replace(/_/g, " ").toUpperCase()}</span>` +
        `<b>confidence ${Math.round(d.confidence * 100)}%</b><br/>${escapeHtml(d.reasoning)}</p>`
    )
    .join("");

  if (ev.blocked) {
    v.className = "blocked";
    $("overlay-title").textContent = "Edit blocked by WikiGuardian";
    $("overlay-sub").textContent = "The edit was not published.";
    v.innerHTML = `<h2>&#128737; WikiGuardian stopped this edit</h2>
      <p>False or unverifiable information was detected. The edit was <b>not published</b>.</p>${rows}`;
  } else if (ev.decisions.length) {
    v.className = "pass";
    $("overlay-title").textContent = "No contradictions found";
    $("overlay-sub").textContent = "Sent to a human reviewer — WikiGuardian never auto-publishes.";
    v.innerHTML = `<h2>&#9989; No contradictions found</h2>
      <p>WikiGuardian found no false claims. Sent to a human reviewer.</p>${rows}`;
  } else {
    v.className = "pass";
    v.innerHTML = `<h2>No verifiable claims</h2><p>No independently verifiable factual claims were found in this edit.</p>`;
  }
}

function showError(message) {
  const v = $("verdict");
  v.hidden = false; v.className = "blocked";
  v.innerHTML = `<h2>Verification error</h2><p>${escapeHtml(message)}</p>`;
}

async function save() {
  resetOverlay();
  $("overlay").hidden = false;

  const payload = {
    article_id: state.articleId,
    proposed_text: $("edit-text").value,
    editor_name: $("editor-name").value,
    edit_summary: $("edit-summary").value,
  };

  let resp;
  try {
    resp = await fetch("/api/verify", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  } catch (e) {
    showError(String(e));
    $("overlay-close").hidden = false;
    return;
  }

  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let idx;
    while ((idx = buffer.indexOf("\n\n")) >= 0) {
      const chunk = buffer.slice(0, idx);
      buffer = buffer.slice(idx + 2);
      const line = chunk.split("\n").find((l) => l.startsWith("data: "));
      if (line) {
        try { handleEvent(JSON.parse(line.slice(6))); } catch (e) { /* ignore */ }
      }
    }
  }
}

document.addEventListener("DOMContentLoaded", () => {
  $("tab-edit").onclick = showEdit;
  $("tab-read").onclick = showRead;
  $("cancel-btn").onclick = showRead;
  $("save-btn").onclick = save;
  $("overlay-close").onclick = () => { $("overlay").hidden = true; };
  loadArticles();
});
