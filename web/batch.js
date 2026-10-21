"use strict";

(() => {
  const LIMIT = 200;
  const stopCodes = new Set(["rate_limited", "network_error", "service_unavailable"]);
  const stateLabel = (row) => ({ pending: "未查询", loading: "查询中", success: "成功", failed: "失败" })[row.state];

  function parseLines(text) {
    const lines = text.replace(/^\uFEFF/, "").split(/\r\n|\r|\n/).map((line) => line.trim()).filter(Boolean);
    if (!lines.length) throw new Error("先粘贴一些 UID 吧，每行一个。");
    if (lines.length > LIMIT) throw new Error(`一次最多查询 ${LIMIT} 条，请分批粘贴。`);
    return lines.map((value, index) => ({ index: index + 1, input: value, uid: "", nickname: "", state: "pending", message: "", cached: false }));
  }

  function plainCell(value) {
    return String(value ?? "").replace(/[\t\r\n]+/g, " ");
  }

  function spreadsheetCell(value) {
    const text = plainCell(value);
    // Public nicknames are untrusted text, not spreadsheet formulas.
    return /^\s*[=+\-@]/.test(text) || /^[0-9]{16,}$/.test(text) ? "'" + text : text;
  }

  function nameOrStatus(row) {
    return row.state === "success" ? row.nickname : row.state === "failed" ? `查询失败：${row.message}` : "未查询";
  }

  function toTSV(rows) {
    return ["UID\t昵称", ...rows.map((row) => [row.uid || row.input, nameOrStatus(row)].map(spreadsheetCell).join("\t"))].join("\n");
  }

  function toNames(rows) {
    return rows.map((row) => plainCell(nameOrStatus(row))).join("\n");
  }

  function toCSV(rows) {
    const cells = [["序号", "UID", "昵称", "状态", "备注"], ...rows.map((row) => [row.index, row.uid || row.input, row.state === "success" ? row.nickname : "", stateLabel(row), row.message || (row.cached ? "缓存结果" : "")])];
    return "\uFEFF" + cells.map((row) => row.map((cell) => `"${spreadsheetCell(cell).replace(/"/g, '""')}"`).join(",")).join("\r\n");
  }

  async function runQueue(rows, request, { onUpdate = () => {}, shouldStop = () => false } = {}) {
    for (const row of rows) {
      if (shouldStop()) return "stopped";
      row.state = "loading";
      row.message = "";
      onUpdate(row);
      let stopReason = "";
      try {
        const profile = await request(row.input);
        row.uid = String(profile.uid);
        row.nickname = profile.nickname;
        row.cached = Boolean(profile.cached);
        row.state = "success";
      } catch (error) {
        row.state = "failed";
        row.message = error.message || "查询失败，请稍后重试。";
        row.code = error.code || "query_error";
        if (stopCodes.has(row.code)) stopReason = row.code;
      }
      onUpdate(row);
      if (stopReason) return stopReason;
    }
    return "";
  }

  if (typeof module !== "undefined" && module.exports) {
    module.exports = { parseLines, runQueue, toTSV, toNames, toCSV };
  }
  if (typeof document === "undefined") return;

  const el = (id) => document.getElementById(id);
  let rows = [];
  let running = false;
  let stopRequested = false;
  let mode = "batch";

  function setMode(next) {
    if (running || el("lookup-button").disabled) return;
    mode = next;
    el("mode-single").setAttribute("aria-pressed", String(next === "single"));
    el("mode-batch").setAttribute("aria-pressed", String(next === "batch"));
    el("lookup-form").hidden = next !== "single";
    el("single-output").hidden = next !== "single";
    el("batch-form").hidden = next !== "batch";
    el("batch-output").hidden = next !== "batch";
    el("error-message").hidden = true;
    el("batch-error").hidden = true;
  }

  function updateCount() {
    const count = el("batch-input").value.split(/\r\n|\r|\n/).filter((line) => line.trim()).length;
    el("batch-input-count").textContent = `${count} / ${LIMIT} 条`;
    el("batch-error").hidden = true;
  }

  function updateRow(row) {
    const [number, uid, name, status] = row.cells;
    number.textContent = row.index;
    uid.textContent = row.uid || row.input;
    name.textContent = row.state === "success" ? row.nickname : row.state === "failed" ? row.message : row.state === "loading" ? "正在查询…" : "等待查询";
    name.className = row.state === "failed" ? "row-error" : row.state === "success" ? "row-name" : "row-muted";
    status.textContent = row.state === "success" && row.cached ? "成功 · 缓存" : stateLabel(row);
    status.className = "row-status " + row.state;
    updateSummary();
  }

  function updateSummary() {
    const success = rows.filter((row) => row.state === "success").length;
    const failed = rows.filter((row) => row.state === "failed").length;
    el("batch-total").textContent = `${rows.length} 条`;
    el("batch-progress-text").textContent = `${running ? "查询中" : "已处理"} ${success + failed} / ${rows.length} · 成功 ${success} · 失败 ${failed} · 未查询 ${rows.length - success - failed}`;
    el("batch-progress").max = rows.length || 1;
    el("batch-progress").value = success + failed;
    el("batch-retry").disabled = running || !rows.some((row) => row.state !== "success");
    for (const id of ["batch-copy", "batch-copy-names", "batch-export"]) el(id).disabled = success + failed === 0;
  }

  function renderTable() {
    const fragment = document.createDocumentFragment();
    rows.forEach((row) => {
      const tr = document.createElement("tr");
      row.cells = Array.from({ length: 4 }, () => document.createElement("td"));
      tr.append(...row.cells);
      fragment.append(tr);
      updateRow(row);
    });
    el("batch-rows").replaceChildren(fragment);
    el("batch-empty").hidden = true;
    el("batch-results").hidden = false;
  }

  async function request(value) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 18000);
    try {
      const response = await fetch(`/api/user?uid=${encodeURIComponent(value)}`, { signal: controller.signal });
      const payload = await response.json();
      if (!response.ok || !payload.data) {
        const error = new Error(payload.error || "查询未完成，请稍后重试。");
        error.code = payload.code || "query_error";
        throw error;
      }
      return payload.data;
    } catch (error) {
      if (error.name === "AbortError") throw new Error("本条查询超时，请稍后重试。");
      if (error instanceof TypeError) {
        const offline = new Error("无法连接本地服务，请重新启动工具。");
        offline.code = "service_unavailable";
        throw offline;
      }
      throw error;
    } finally {
      clearTimeout(timer);
    }
  }

  async function start(retry = false) {
    if (running) return;
    try {
      if (!retry) rows = parseLines(el("batch-input").value);
    } catch (error) {
      el("batch-error").textContent = error.message;
      el("batch-error").hidden = false;
      return;
    }
    const queue = rows.filter((row) => row.state !== "success");
    if (!queue.length) return;
    queue.forEach((row) => { row.state = "pending"; row.message = ""; });
    running = true;
    stopRequested = false;
    el("batch-error").hidden = true;
    el("batch-notice").hidden = true;
    el("batch-stop").hidden = false;
    el("batch-stop").disabled = false;
    el("batch-stop").textContent = "停止查询";
    for (const id of ["batch-input", "batch-start", "batch-example", "batch-clear", "mode-single", "mode-batch"]) el(id).disabled = true;
    renderTable();
    const reason = await runQueue(queue, request, { onUpdate: updateRow, shouldStop: () => stopRequested });
    running = false;
    for (const id of ["batch-input", "batch-start", "batch-example", "batch-clear", "mode-single", "mode-batch"]) el(id).disabled = false;
    el("batch-stop").hidden = true;
    updateSummary();
    if (reason) {
      el("batch-notice").textContent = reason === "stopped" ? "已停止，已查到的结果已保留。可点击“重试未成功项”继续。" : reason === "rate_limited" ? "哔哩哔哩暂时限制查询，已暂停并保留结果。请稍后点击“重试未成功项”。" : "网络或本地服务暂时不可用，已暂停并保留结果。恢复后可重试未成功项。";
      el("batch-notice").hidden = false;
    }
  }

  el("mode-single").addEventListener("click", () => setMode("single"));
  el("mode-batch").addEventListener("click", () => setMode("batch"));
  el("batch-input").addEventListener("input", updateCount);
  el("batch-form").addEventListener("submit", (event) => { event.preventDefault(); start(); });
  el("batch-retry").addEventListener("click", () => start(true));
  el("batch-stop").addEventListener("click", () => { stopRequested = true; el("batch-stop").disabled = true; el("batch-stop").textContent = "等待当前条完成…"; });
  el("batch-clear").addEventListener("click", () => { el("batch-input").value = ""; updateCount(); el("batch-input").focus(); });
  el("batch-example").addEventListener("click", () => { el("batch-input").value = Array.from({ length: 18 }, (_, i) => String(10331033 + i * 10001)).join("\n"); updateCount(); });
  el("batch-copy").addEventListener("click", () => copy(toTSV(rows), "UID 和昵称已复制，可直接粘贴为两列"));
  el("batch-copy-names").addEventListener("click", () => copy(toNames(rows), "昵称列表已复制"));
  el("batch-export").addEventListener("click", () => {
    const blob = new Blob([toCSV(rows)], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `bili-uid-results-${new Date().toISOString().slice(0, 10)}.csv`;
    document.body.append(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  });
  updateCount();
  setMode(mode);
})();
