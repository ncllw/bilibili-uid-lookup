"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const { parseLines, runQueue, toTSV, toNames, toCSV } = require("./web/batch.js");

test("line parsing ignores blanks and retains order, duplicates and long UID strings", () => {
  const rows = parseLines("\uFEFF10331033\r\n\r\n10341034\n10331033\n9223372036854775807\n");
  assert.deepEqual(rows.map((row) => row.input), ["10331033", "10341034", "10331033", "9223372036854775807"]);
  assert.deepEqual(rows.map((row) => row.index), [1, 2, 3, 4]);
  assert.throws(() => parseLines("\n  "), /粘贴/);
  assert.throws(() => parseLines(Array(201).fill("2").join("\n")), /200/);
});

test("queue is sequential and one failed item does not shift or cancel other rows", async () => {
  const rows = parseLines("2\ninvalid\n3\n2");
  let inFlight = 0;
  let maxFlight = 0;
  const visits = [];
  await runQueue(rows, async (value) => {
    inFlight++;
    maxFlight = Math.max(maxFlight, inFlight);
    await new Promise((resolve) => setTimeout(resolve, 1));
    visits.push(value);
    inFlight--;
    if (value === "invalid") throw new Error("无效 UID");
    return { uid: value, nickname: "昵称" + value };
  });
  assert.equal(maxFlight, 1);
  assert.deepEqual(visits, ["2", "invalid", "3", "2"]);
  assert.deepEqual(rows.map((row) => row.state), ["success", "failed", "success", "success"]);
  assert.equal(toTSV(rows), "UID\t昵称\n2\t昵称2\ninvalid\t查询失败：无效 UID\n3\t昵称3\n2\t昵称2");
  assert.equal(toNames(rows).split("\n").length, 4);
});

test("rate limit pauses the queue and preserves results and pending rows", async () => {
  const rows = parseLines("2\n3\n4");
  const reason = await runQueue(rows, async (value) => {
    if (value === "3") throw Object.assign(new Error("稍后重试"), { code: "rate_limited" });
    return { uid: value, nickname: "测试" };
  });
  assert.equal(reason, "rate_limited");
  assert.deepEqual(rows.map((row) => row.state), ["success", "failed", "pending"]);
  assert.equal(toNames(rows), "测试\n查询失败：稍后重试\n未查询");
});

test("manual stop finishes the current item and resume leaves successful rows intact", async () => {
  const rows = parseLines("2\n3\n4");
  let stopped = false;
  const reason = await runQueue(rows, async (value) => {
    stopped = true;
    return { uid: value, nickname: "第一次" };
  }, { shouldStop: () => stopped });
  assert.equal(reason, "stopped");
  assert.deepEqual(rows.map((row) => row.state), ["success", "pending", "pending"]);
  await runQueue(rows.filter((row) => row.state !== "success"), async (value) => ({ uid: value, nickname: "继续" }));
  assert.deepEqual(rows.map((row) => row.nickname), ["第一次", "继续", "继续"]);
});

test("CSV escapes nicknames and preserves large numeric IDs as text", () => {
  const rows = parseLines("9223372036854775807\n3");
  Object.assign(rows[0], { uid: "9223372036854775807", nickname: '=HYPERLINK("bad")', state: "success" });
  Object.assign(rows[1], { uid: "3", nickname: '昵称,"测试"', state: "success" });
  const csv = toCSV(rows);
  assert.ok(csv.startsWith("\uFEFF"));
  assert.ok(csv.includes('"\'9223372036854775807"'));
  assert.ok(csv.includes('"\'=HYPERLINK(""bad"")"'));
  assert.ok(csv.includes('"昵称,""测试"""'));
  assert.equal(csv.split("\r\n").length, 3);
});

test("network failure stops further requests", async () => {
  const rows = parseLines("2\n3");
  let calls = 0;
  const reason = await runQueue(rows, async () => {
    calls++;
    throw Object.assign(new Error("无法连接"), { code: "service_unavailable" });
  });
  assert.equal(reason, "service_unavailable");
  assert.equal(calls, 1);
  assert.equal(rows[1].state, "pending");
});
