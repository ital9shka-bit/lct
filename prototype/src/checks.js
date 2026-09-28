export const DEFAULT_TIMES = ["09:00", "12:00", "15:00", "18:00"];
export const DEFAULT_SCHEDULE = {
  times: DEFAULT_TIMES,
  confirm: 2,
  absence: 3,
};
// Совместимость с прежним именем; расписание объекта задаётся в настройках.
export const CONTROL_TIMES = DEFAULT_TIMES;

export const scheduleOf = (object) => {
  const s = object?.schedule || {};
  return {
    times: s.times?.length ? [...s.times].sort() : DEFAULT_SCHEDULE.times,
    confirm: s.confirm || DEFAULT_SCHEDULE.confirm,
    absence: s.absence || DEFAULT_SCHEDULE.absence,
  };
};

export function demoFacts(role, includeCrane = false) {
  return [
    ...(role === "pit" || role === "entrance" ? ["excavator"] : []),
    ...(["pit", "entrance", "overview"].includes(role)
      ? ["pit", "earthworks"]
      : []),
    ...(role === "overview" && includeCrane ? ["crane"] : []),
  ];
}

const FACT_OF = { excavation: "earthworks", crane: "crane" };
// Признаки укрупнённого этапа — объединение признаков его подэтапов,
// поэтому анализ проверяет один этап вместо нескольких.
export const factsFor = (stage) => [
  ...new Set([
    ...(FACT_OF[stage.evidenceKind] ? [FACT_OF[stage.evidenceKind]] : []),
    ...(stage.children || []).flatMap(factsFor),
  ]),
];
// Способ подтверждения: по камерам либо осмотром инженера.
export const confirmBy = (stage) =>
  stage.confirmBy || (stage.observable === "Нет" ? "inspection" : "cameras");

const watching = (stage, cams = []) =>
  cams.filter(
    (c) =>
      c.photo &&
      !c.failed &&
      (!stage.cameraIds?.length || stage.cameraIds.includes(c.id)),
  );

// Одна ячейка «этап × контрольный интервал».
// missing — проверки не было, uncovered — камеры этап не покрывают,
// positive — признак найден, none — проверка есть, признака нет.
export function stageCell(stage, check, facts = factsFor(stage)) {
  if (!check) return { state: "missing", sources: [] };
  const covering = watching(stage, check.cams);
  if (!covering.length || !facts.length)
    return { state: "uncovered", sources: [] };
  const sources = covering
    .filter((c) => facts.some((f) => c.facts?.includes(f)))
    .map((c) => ({ ...c, time: check.time, date: check.date }));
  return { state: sources.length ? "positive" : "none", sources };
}

// Несколько проверок внутри одного интервала дают максимум одно наблюдение.
export function stageCells(stage, checks, times) {
  const facts = factsFor(stage);
  return times.map((time) => {
    const check = checks.find((c) => c.time === time);
    return { time, check, ...stageCell(stage, check, facts) };
  });
}

export const SOURCE_LABELS = {
  camera: "Снимки с камер",
  manual: "Загружено вручную",
  mixed: "Камеры и ручная загрузка",
};
export function snapshotSource(snapshot) {
  const kinds = new Set(
    (snapshot.cams || [])
      .filter((c) => c.photo)
      .map((c) => c.source || snapshot.source || "camera"),
  );
  if (kinds.size > 1) return "mixed";
  return [...kinds][0] || snapshot.source || "camera";
}

export const INSPECTION_RESULTS = {
  confirmed: { type: "success", label: "Подтверждён инженером" },
  rejected: { type: "warning", label: "Не подтверждён инженером" },
  note: { type: "neutral", label: "Замечание инженера" },
};

export function activeInspection(stage, inspections = [], date) {
  return (
    inspections
      .filter(
        (i) =>
          i.stageId === stage.id &&
          i.date <= date &&
          date <= (i.until || i.date),
      )
      .sort((a, b) => a.date.localeCompare(b.date))
      .at(-1) || null
  );
}

// Дневная оценка этапа: осмотр инженера, затем ненаблюдаемость, затем пороги.
export function stageVerdict(stage, checks, options = {}) {
  const schedule = options.schedule || DEFAULT_SCHEDULE;
  const times = options.times || schedule.times;
  const cells = stageCells(stage, checks, times);
  const positives = cells.filter((c) => c.state === "positive").length;
  const usable = cells.filter(
    (c) => c.state === "positive" || c.state === "none",
  ).length;
  const sources = cells.flatMap((c) => c.sources);
  const required = schedule.confirm;
  const inspection = options.date
    ? activeInspection(stage, options.inspections, options.date)
    : null;
  const base = { cells, positives, usable, sources, required, inspection };
  if (inspection)
    return {
      ...base,
      source: "inspection",
      ...INSPECTION_RESULTS[inspection.verdict],
      count: `осмотр ${inspection.date.split("-").reverse().slice(0, 2).join(".")} · ${inspection.author}`,
    };
  if (confirmBy(stage) === "inspection")
    return {
      ...base,
      source: "inspection-pending",
      type: "muted",
      label:
        stage.observable === "Нет"
          ? "Вне визуального контроля"
          : "Ожидает осмотра",
      count:
        stage.observable === "Нет"
          ? "внешние камеры не видят работы, нужен осмотр"
          : "этап подтверждается осмотром инженера",
    };
  if (positives >= required)
    return {
      ...base,
      source: "cameras",
      type: "success",
      label: "Подтверждается",
      count: `подтверждений ${positives} из ${required}`,
    };
  if (positives === 0 && usable >= schedule.absence)
    return {
      ...base,
      source: "cameras",
      type: "warning",
      label: "Возможное отклонение",
      count: `пригодных интервалов ${usable}, признаков нет`,
    };
  return {
    ...base,
    source: "cameras",
    type: "neutral",
    label: "Недостаточно данных",
    count: `подтверждений ${positives} из ${required}`,
  };
}

// Оценка этапа по одной проверке — для экрана результата.
export function checkEvidence(stage, check) {
  const analyzed = check?.analysis?.stage_evidence?.find(
    (item) => item.plan_item_id === stage.id,
  );
  if (analyzed) {
    const items = (check.analysis.evidence_items || []).filter(
      (item) =>
        analyzed.evidence_item_ids.includes(item.evidence_id) &&
        item.plan_item_id === stage.id,
    );
    const sources = items
      .map((item) => {
        const camera = check.cams.find((entry) => entry.id === item.camera_id);
        return camera
          ? {
              ...camera,
              time: check.time,
              date: check.date,
              evidenceId: item.evidence_id,
              evidenceDescription: item.description,
              confidence: item.confidence,
              polarity: item.polarity,
            }
          : null;
      })
      .filter(Boolean);
    const states = {
      positive: { type: "success", label: "Признаки найдены" },
      conflict: { type: "warning", label: "Найдены противоречия" },
      not_observable: { type: "muted", label: "Вне визуального контроля" },
      insufficient_coverage: {
        type: "neutral",
        label: "Недостаточно покрытия",
      },
      neutral: { type: "neutral", label: "Признаков не найдено" },
    };
    return {
      ...(states[analyzed.status] || states.neutral),
      sources,
      explanation: analyzed.explanation,
      limitations: analyzed.limitations || [],
      confidence: analyzed.confidence,
      modelStatus: analyzed.status,
    };
  }
  if (confirmBy(stage) === "inspection")
    return {
      type: "muted",
      label:
        stage.observable === "Нет"
          ? "Вне визуального контроля"
          : "Подтверждается осмотром",
      sources: [],
    };
  const cell = stageCell(stage, check);
  if (cell.state === "uncovered")
    return { type: "neutral", label: "Камеры не покрывают этап", sources: [] };
  return cell.state === "positive"
    ? { type: "success", label: "Признаки найдены", sources: cell.sources }
    : { type: "neutral", label: "Признаков не найдено", sources: [] };
}

// Совместимая обёртка: интервалы берутся из самих проверок.
export function stageEvidence(stage, checks, required = 2) {
  const times = [...new Set(checks.map((c) => c.time))].sort();
  const v = stageVerdict(stage, checks, {
    times,
    schedule: { times, confirm: required, absence: DEFAULT_SCHEDULE.absence },
  });
  return {
    ...v,
    hits: v.cells.filter((c) => c.state === "positive").map((c) => c.check),
  };
}

export function daySummary(plan, checks, date, object = {}) {
  const schedule = scheduleOf(object);
  const today = checks.filter((check) => check.date === date);
  const stages = plan
    .filter((p) => p.start <= date && p.end >= date)
    .map((p) => ({
      ...p,
      evidence: stageVerdict(p, today, {
        schedule,
        date,
        inspections: object.inspections,
      }),
    }));
  return {
    schedule,
    stages,
    confirmed: stages.filter((p) => p.evidence.type === "success").length,
    insufficient: stages.filter((p) => p.evidence.type === "neutral").length,
    deviations: stages.filter((p) => p.evidence.type === "warning").length,
    excluded: stages.filter((p) => p.evidence.type === "muted").length,
    received: schedule.times.filter((time) =>
      today.some((check) => check.time === time),
    ).length,
    expected: schedule.times.length,
  };
}
