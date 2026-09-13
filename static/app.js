/* SafeSQL UI: chat, result cards, collapsible SQL, blocked cards, history. */
"use strict";

const chat = document.getElementById("chat");
const form = document.getElementById("askform");
const input = document.getElementById("question");
const btn = document.getElementById("askbtn");
const historyEl = document.getElementById("history");

const REASONS = {
  not_select: "not a SELECT",
  multi_statement: "more than one statement",
  comment: "contains a comment",
  select_into: "SELECT INTO creates a table",
  denied_function: "calls a denied function",
  system_table: "touches a system catalog",
  unknown_table: "table not in the allow-list",
  unparseable: "could not be parsed",
  generation_failed: "the model produced no valid proposal",
  execution_failed: "both attempts failed against the database",
};

function el(tag, cls, text) {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (text !== undefined) node.textContent = text;
  return node;
}

function resultsTable(columns, rows) {
  const wrap = el("div", "tbl-wrap");
  const table = el("table");
  const thead = el("thead");
  const headRow = el("tr");
  columns.forEach((c) => headRow.appendChild(el("th", "", c)));
  thead.appendChild(headRow);
  table.appendChild(thead);
  const tbody = el("tbody");
  rows.forEach((r) => {
    const tr = el("tr");
    r.forEach((v) => tr.appendChild(el("td", "", v === null ? "∅" : String(v))));
    tbody.appendChild(tr);
  });
  table.appendChild(tbody);
  wrap.appendChild(table);
  return wrap;
}

function sqlBlock(data) {
  const details = el("details");
  details.appendChild(el("summary", "", "SQL that ran"));
  const body = el("div", "sql-body");
  if (data.rationale) {
    body.appendChild(el("div", "label", "Rationale"));
    body.appendChild(el("div", "", data.rationale));
  }
  if (data.sql) {
    body.appendChild(el("div", "label", "SQL"));
    body.appendChild(el("pre", "", data.sql));
  }
  if (data.rewrites && data.rewrites.length) {
    body.appendChild(el("div", "label", "Rewrites applied by the guard"));
    const ul = el("ul", "rewrites");
    data.rewrites.forEach((r) => ul.appendChild(el("li", "", r)));
    body.appendChild(ul);
  }
  // don't repeat the SQL already shown above unless the whole question failed
  const attempts = (data.attempts || []).filter(
    (a) => a.sql !== data.sql || data.status === "failed"
  );
  if (attempts.length) {
    body.appendChild(el("div", "label", "Failed attempts"));
    attempts.forEach((a) => {
      body.appendChild(el("pre", "", a.sql));
      body.appendChild(el("div", "attempt-err", a.error));
    });
  }
  details.appendChild(body);
  return details;
}

function renderAnswer(data) {
  const card = el("div", "card " + data.status);
  const status = el("div", "status-line");
  status.appendChild(el("span", "badge " + data.status, data.status));
  if (data.latency_ms !== undefined) status.appendChild(el("span", "", data.latency_ms + " ms"));
  card.appendChild(status);

  if (data.status === "ok") {
    card.appendChild(el("div", "summary", data.summary));
    if (data.columns.length) card.appendChild(resultsTable(data.columns, data.rows));
  } else {
    const reason = REASONS[data.block_reason] || data.block_reason || "unknown error";
    const line = el("div", "summary");
    line.appendChild(
      document.createTextNode(data.status === "blocked" ? "Query blocked: " : "Query failed: ")
    );
    line.appendChild(el("span", "reason", reason));
    card.appendChild(line);
    if (data.summary && data.status === "failed") card.appendChild(el("div", "", data.summary));
  }
  if (data.sql || (data.attempts && data.attempts.length)) card.appendChild(sqlBlock(data));
  return card;
}

async function refreshHistory() {
  try {
    const rows = await (await fetch("/queries")).json();
    historyEl.replaceChildren();
    rows.forEach((q) => {
      const item = el("div", "hist");
      const title = el("span", "hq");
      const dot = el("span", "dot " + q.status);
      title.appendChild(dot);
      title.appendChild(document.createTextNode(q.question));
      item.appendChild(title);
      const meta = q.status + (q.block_reason ? " · " + q.block_reason : "") +
        " · " + q.latency_ms + " ms · " + q.rows_returned + " rows";
      item.appendChild(el("span", "hmeta", meta));
      historyEl.appendChild(item);
    });
  } catch {
    /* history is cosmetic; never break the chat */
  }
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const question = input.value.trim();
  if (!question) return;
  input.value = "";
  btn.disabled = true;
  chat.appendChild(el("div", "q", question));
  const pending = el("div", "card", "Thinking…");
  chat.appendChild(pending);
  pending.scrollIntoView({ behavior: "smooth" });
  try {
    const resp = await fetch("/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    });
    if (!resp.ok) throw new Error("HTTP " + resp.status + ": " + (await resp.text()));
    const data = await resp.json();
    pending.replaceWith(renderAnswer(data));
  } catch (err) {
    pending.replaceWith(renderAnswer({ status: "failed", block_reason: String(err.message || err) }));
  } finally {
    btn.disabled = false;
    input.focus();
    refreshHistory();
  }
});

refreshHistory();
input.focus();
