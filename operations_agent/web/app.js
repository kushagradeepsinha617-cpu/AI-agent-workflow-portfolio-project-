"use strict";

const fields = {
  vendor_name: "Vendor", invoice_number: "Invoice number", invoice_date: "Invoice date",
  due_date: "Due date", currency: "Currency", subtotal: "Subtotal", tax: "Tax",
  total: "Total", description: "Description"
};
const form = document.getElementById("invoice-form");
const source = document.getElementById("document");
const email = document.getElementById("email");
const vendors = document.getElementById("known-vendors");
const select = document.getElementById("example");
const fileInput = document.getElementById("text-file");
const message = document.getElementById("message");
let examples = [];

function announce(text, error = false) {
  message.textContent = text;
  message.classList.toggle("error", error);
  message.setAttribute("role", error ? "alert" : "status");
}

function clearResult(text = "Input changed. Process the invoice to prepare a new record.") {
  document.getElementById("result").hidden = true;
  document.getElementById("placeholder").hidden = false;
  announce(text);
}

function textNode(tag, text, className) {
  const element = document.createElement(tag);
  element.textContent = String(text);
  if (className) element.className = className;
  return element;
}

function readable(code) {
  return String(code).replaceAll("_", " ").replaceAll(":", ": ");
}

function issuesGroup(title, values, emptyText) {
  const section = document.createElement("section");
  section.className = "issue-group";
  section.append(textNode("h4", title));
  if (values.length) {
    const list = document.createElement("ul");
    for (const value of values) list.append(textNode("li", readable(value)));
    section.append(list);
  } else {
    section.append(textNode("p", emptyText, "clear"));
  }
  return section;
}

function render(row) {
  if (row.human_decision !== "pending" || row.processing_status !== "awaiting_review") {
    throw new Error("Unexpected record state. No decision has been accepted by this viewer.");
  }
  const extraction = row.extraction;
  document.getElementById("extraction-status").textContent = readable(extraction.status);
  document.getElementById("validation-status").textContent = readable(row.validation_status);
  const body = document.getElementById("fields");
  body.replaceChildren();
  for (const [key, label] of Object.entries(fields)) {
    const value = extraction.fields[key];
    const tr = document.createElement("tr");
    let note = "";
    if (Object.hasOwn(extraction.conflicts, key)) note = "Conflicting sources";
    else if (Object.hasOwn(extraction.uncertain_fields, key)) note = "Uncertain";
    else if (extraction.missing_fields.includes(key)) note = "Missing";
    tr.append(textNode("td", label), textNode("td", value === null ? "Not extracted" : value,
              value === null ? "unresolved" : ""), textNode("td", note));
    body.append(tr);
  }
  const uncertainty = Object.entries(extraction.uncertain_fields).map(([key, reason]) => `${fields[key]}: ${reason}`);
  const conflicts = Object.keys(extraction.conflicts).map(key => `${fields[key]}: inspect both source values`);
  document.getElementById("issues").replaceChildren(
    issuesGroup("Validation", row.errors, "No validation errors reported."),
    issuesGroup("Missing or unresolved", [...extraction.missing_fields.map(key => `${fields[key]}: missing`),
                ...uncertainty, ...conflicts], "No unresolved fields reported."),
    issuesGroup("Review flags", row.risk_indicators, "No risk indicators reported. Human review is still pending."),
    issuesGroup("Processing", [...extraction.issues, ...row.workflow.issues], "All processing steps completed without a workflow issue.")
  );
  const evidenceList = document.getElementById("evidence");
  evidenceList.replaceChildren();
  for (const [key, label] of Object.entries(fields)) {
    for (const evidence of extraction.evidence[key]) {
      const item = document.createElement("li");
      item.append(textNode("strong", label), textNode("span", `${evidence.source} · line ${evidence.line}`),
                  textNode("code", evidence.value));
      evidenceList.append(item);
    }
  }
  if (!evidenceList.children.length) evidenceList.append(textNode("li", "No source evidence was extracted."));
  document.getElementById("review-summary").textContent = row.review_summary;
  document.getElementById("placeholder").hidden = true;
  document.getElementById("result").hidden = false;
  announce(row.validation_status === "valid" && extraction.status === "extracted" && !row.risk_indicators.length
    ? "Record prepared. The human decision remains pending."
    : "Record prepared with items requiring attention. The human decision remains pending.");
}

function setBusy(busy) {
  for (const element of form.elements) element.disabled = busy;
  form.setAttribute("aria-busy", String(busy));
  document.getElementById("process").textContent = busy ? "Processing…" : "Process invoice →";
}

form.addEventListener("submit", async event => {
  event.preventDefault();
  clearResult("Processing the synthetic invoice…");
  const payload = JSON.stringify({document: source.value, email: email.value,
    known_vendors: vendors.value.split(/\r?\n/).map(value => value.trim()).filter(Boolean)});
  if (new TextEncoder().encode(payload).length > 256000) {
    announce("This request is too large. Keep the combined text below 256,000 bytes.", true);
    return;
  }
  setBusy(true);
  try {
    const response = await fetch("/api/process", {method: "POST", headers: {"Content-Type": "application/json"}, body: payload});
    const row = await response.json();
    if (!response.ok) throw new Error(row.message || "Processing failed. Try again with a smaller synthetic example.");
    render(row);
  } catch (error) {
    clearResult();
    announce(error.message || "Could not process the invoice.", true);
  } finally {
    setBusy(false);
  }
});

for (const input of [source, email, vendors]) input.addEventListener("input", () => clearResult());
select.addEventListener("change", () => {
  const selected = examples.find(item => item.id === select.value);
  if (!selected) return;
  source.value = selected.document;
  email.value = selected.email;
  document.getElementById("context-options").open = Boolean(selected.email);
  fileInput.value = "";
  clearResult("Example loaded. Process it to inspect the evidence.");
});

fileInput.addEventListener("change", async () => {
  clearResult();
  const file = fileInput.files[0];
  if (!file) return;
  setBusy(true);
  try {
    if (!file.name.toLowerCase().endsWith(".txt") || file.size > 256000) {
      throw new Error("Choose a .txt file smaller than 256,000 bytes.");
    }
    source.value = new TextDecoder("utf-8", {fatal: true}).decode(await file.arrayBuffer());
    email.value = "";
    select.value = "";
    announce("Text file loaded and previous email context cleared. Process it to inspect the record.");
  } catch (error) {
    announce("Could not load this file. Use a small UTF-8 .txt file containing synthetic data.", true);
  } finally {
    setBusy(false);
  }
});

async function loadExamples() {
  try {
    const response = await fetch("/api/examples");
    if (!response.ok) throw new Error("Examples unavailable");
    examples = (await response.json()).examples;
    for (const example of examples) {
      const option = textNode("option", example.title);
      option.value = example.id;
      select.append(option);
    }
  } catch (_) {
    announce("Examples could not be loaded. You can still paste synthetic invoice text.", true);
  }
}
loadExamples();
