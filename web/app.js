"use strict";
const $ = (id) => document.getElementById(id);
const input = $("uid-input");
const historyKey = "bili-uid-history-v1";
let current = null;
let busy = false;
let toastTimer;
let records = [];
try {
  const saved = JSON.parse(localStorage.getItem(historyKey) || "[]");
  if (Array.isArray(saved)) records = saved.filter((x) => x && typeof x.uid === "string" && /^[1-9][0-9]{0,18}$/.test(x.uid) && typeof x.nickname === "string").slice(0, 8);
} catch { /* The app also works when browser storage is unavailable. */ }

function toast(message) {
  $("toast").textContent = message;
  $("toast").hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { $("toast").hidden = true; }, 2400);
}

async function copy(value, message) {
  try {
    await navigator.clipboard.writeText(value);
    toast(message);
  } catch {
    toast("复制失败，请选中结果中的文字手动复制。");
  }
}

function writeHistory() {
  try { localStorage.setItem(historyKey, JSON.stringify(records)); } catch { /* Optional. */ }
}

function renderHistory() {
  $("history-section").hidden = records.length === 0;
  $("history-count").textContent = records.length;
  $("history-list").replaceChildren();
  records.forEach((record) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "history-item";
    button.disabled = busy;
    const name = document.createElement("span");
    name.className = "history-name";
    name.textContent = record.nickname;
    const uid = document.createElement("span");
    uid.className = "history-uid";
    uid.textContent = record.uid;
    button.append(name, uid);
    button.addEventListener("click", () => {
      input.value = record.uid;
      updateInput();
      query();
    });
    $("history-list").append(button);
  });
}

function updateInput() {
  $("clear-input").hidden = !input.value;
  $("error-message").hidden = true;
}

function showProfile(profile) {
  current = profile;
  $("empty-state").hidden = true;
  $("result").hidden = false;
  $("nickname").textContent = profile.nickname;
  $("result-uid").textContent = profile.uid;
  $("space-link").href = profile.space_url;
  $("level").hidden = !Number.isInteger(profile.level);
  $("level").textContent = `LV ${profile.level}`;
  $("official").hidden = !profile.official;
  $("official").textContent = profile.official;
  $("sign").hidden = !profile.sign;
  $("sign").textContent = profile.sign;
  $("followers").textContent = Number.isFinite(profile.followers) ? `${new Intl.NumberFormat("zh-CN").format(profile.followers)} 位粉丝` : "来自哔哩哔哩公开信息";
  const time = new Date(profile.fetched_at).toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" });
  $("result-time").textContent = `${profile.cached ? "缓存 · " : "查询于 "}${time}`;
  const avatar = $("avatar");
  avatar.hidden = true;
  avatar.onload = () => { avatar.hidden = false; };
  avatar.onerror = () => { avatar.hidden = true; };
  if (profile.avatar) avatar.src = profile.avatar;
  else avatar.removeAttribute("src");
  records = [{ uid: profile.uid, nickname: profile.nickname }, ...records.filter((r) => r.uid !== profile.uid)].slice(0, 8);
  writeHistory();
  renderHistory();
}

async function query() {
  if (busy) return;
  const value = input.value.trim();
  $("error-message").hidden = true;
  $("result").hidden = true;
  $("empty-state").hidden = false;
  current = null;
  if (!value) {
    $("error-message").textContent = "先输入一个 UID 或个人空间链接吧。";
    $("error-message").hidden = false;
    input.focus();
    return;
  }
  busy = true;
  $("lookup-button").disabled = true;
  $("button-label").textContent = "查询中…";
  $("example").disabled = true;
  input.disabled = true;
  $("clear-input").disabled = true;
  $("result").setAttribute("aria-busy", "true");
  renderHistory();
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 18000);
  try {
    const response = await fetch(`/api/user?uid=${encodeURIComponent(value)}`, { signal: controller.signal });
    const payload = await response.json();
    if (!response.ok || !payload.data) throw new Error(payload.error || "查询未完成，请稍后重试。");
    showProfile(payload.data);
  } catch (error) {
    $("error-message").textContent = error.name === "AbortError" ? "查询等待超时，请稍后重试。" : (error instanceof TypeError ? "无法连接本地服务，请重新双击启动工具。" : error.message);
    $("error-message").hidden = false;
  } finally {
    clearTimeout(timer);
    busy = false;
    $("lookup-button").disabled = false;
    $("button-label").textContent = "查询昵称";
    $("example").disabled = false;
    input.disabled = false;
    $("clear-input").disabled = false;
    $("result").setAttribute("aria-busy", "false");
    renderHistory();
  }
}

$("lookup-form").addEventListener("submit", (event) => { event.preventDefault(); query(); });
input.addEventListener("input", updateInput);
$("clear-input").addEventListener("click", () => { input.value = ""; updateInput(); input.focus(); });
$("example").addEventListener("click", () => { input.value = "306936843"; updateInput(); query(); });
$("copy-name").addEventListener("click", () => { if (current) copy(current.nickname, "昵称已复制"); });
$("copy-uid").addEventListener("click", () => { if (current) copy(current.uid, "UID 已复制"); });
$("clear-history").addEventListener("click", () => { records = []; writeHistory(); renderHistory(); toast("查询记录已清空"); });
renderHistory();
