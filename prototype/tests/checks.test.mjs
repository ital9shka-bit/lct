import test from "node:test";
import assert from "node:assert/strict";
import { demoFacts, stageEvidence, daySummary } from "../src/checks.js";
const date = "2026-09-15";
const stage = {
  id: "p",
  observable: "Да",
  evidenceKind: "crane",
  start: date,
  end: date,
};
const check = (time, extra = {}) => ({
  date,
  time,
  cams: [{ id: "c", photo: "x", facts: demoFacts("overview", true), ...extra }],
});
test("two separate observations confirm a stage; repeats do not", () => {
  assert.equal(stageEvidence(stage, [check("12:00")]).type, "neutral");
  assert.equal(
    stageEvidence(stage, [check("12:00"), check("12:00")]).type,
    "neutral",
  );
  assert.equal(
    stageEvidence(stage, [check("12:00"), check("15:00")]).type,
    "success",
  );
});
test("unprocessed real photos, failures, and unrelated cameras cannot confirm work", () => {
  assert.equal(
    stageEvidence(stage, [
      check("12:00", { facts: [] }),
      check("15:00", { failed: true }),
    ]).hits.length,
    0,
  );
  assert.equal(
    stageEvidence({ ...stage, cameraIds: ["another"] }, [
      check("12:00"),
      check("15:00"),
    ]).hits.length,
    0,
  );
  assert.equal(
    stageEvidence({ ...stage, evidenceKind: undefined }, [
      check("12:00"),
      check("15:00"),
    ]).hits.length,
    0,
  );
});
test("day summary separates unobservable stages and deduplicates planned control times", () => {
  const s = daySummary(
    [stage, { ...stage, id: "hidden", observable: "Нет" }],
    [
      check("12:00"),
      check("12:00"),
      check("15:00"),
      { ...check("09:00"), date: "2026-09-14" },
    ],
    date,
  );
  assert.equal(s.confirmed, 1);
  assert.equal(s.excluded, 1);
  assert.equal(s.insufficient, 0);
  assert.equal(s.received, 2);
});

import { scheduleOf, stageCells, stageVerdict } from "../src/checks.js";
const stages = {
  visible: { id: "v", observable: "Да", evidenceKind: "crane" },
  hidden: { id: "h", observable: "Нет" },
};
const inspection = (extra = {}) => ({
  stageId: "h",
  date,
  verdict: "confirmed",
  author: "Инженер",
  ...extra,
});

test("schedule sets the day's control intervals and the coverage denominator", () => {
  const schedule = scheduleOf({ schedule: { times: ["17:00", "09:00"] } });
  assert.deepEqual(schedule.times, ["09:00", "17:00"]);
  const cells = stageCells(stages.visible, [check("09:00")], schedule.times);
  assert.deepEqual(
    cells.map((c) => c.state),
    ["positive", "missing"],
  );
});

test("an engineer inspection outranks thresholds and unobservability", () => {
  const hidden = stageVerdict(stages.hidden, [], {
    date,
    inspections: [inspection()],
  });
  assert.equal(hidden.type, "success");
  assert.equal(hidden.source, "inspection");
  const withoutInspection = stageVerdict(stages.hidden, [], { date });
  assert.equal(withoutInspection.type, "muted");
  const rejected = stageVerdict(stages.visible, [check("09:00"), check("15:00")], {
    date,
    inspections: [inspection({ stageId: "v", verdict: "rejected" })],
  });
  assert.equal(rejected.type, "warning");
});

test("an inspection applies inside its period and the later one wins", () => {
  const options = (d) => ({
    date: d,
    inspections: [
      inspection({ until: "2026-09-17" }),
      inspection({ date: "2026-09-16", until: "2026-09-17", verdict: "note" }),
    ],
  });
  assert.equal(stageVerdict(stages.hidden, [], options(date)).type, "success");
  assert.equal(
    stageVerdict(stages.hidden, [], options("2026-09-16")).type,
    "neutral",
  );
  assert.equal(
    stageVerdict(stages.hidden, [], options("2026-09-18")).type,
    "muted",
  );
});
