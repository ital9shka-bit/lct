import React, { useState } from "react";
import {
  IconArrowUpRight,
  IconArrowRight,
  IconBuildings,
  IconCamera,
  IconCheck,
  IconClock,
  IconCircleCheck,
  IconAlertTriangle,
  IconInfoCircle,
  IconSearch,
  IconPlus,
  IconPlayerPause,
  IconMapPin,
  IconX,
} from "@tabler/icons-react";

const summaryFromReport = (report) => {
  const statusType = (status) => {
    if (["confirmed", "inspection_confirmed"].includes(status))
      return "success";
    if (["possible_deviation", "inspection_rejected"].includes(status))
      return "warning";
    if (status === "outside_visual_control") return "muted";
    return "neutral";
  };
  const stages = report.stages.map((stage) => ({
    id: stage.plan_item_id,
    name: stage.stage_name,
    status: stage.status,
    evidence: {
      type: statusType(stage.status),
      count:
        stage.source?.type === "inspection"
          ? `осмотр ${stage.source.observed_date.split("-").reverse().join(".")} · ${stage.source.author}`
          : stage.status === "possible_deviation"
            ? `пригодных интервалов ${stage.usable_intervals}, признаков нет`
            : stage.status === "awaiting_inspection"
              ? "нужен осмотр инженера"
              : `подтверждений ${stage.positive_intervals} из ${stage.required_positive}`,
    },
  }));
  return {
    stages,
    confirmed: stages.filter((stage) => stage.evidence.type === "success")
      .length,
    insufficient: stages.filter((stage) => stage.evidence.type === "neutral")
      .length,
    deviations: stages.filter((stage) => stage.evidence.type === "warning")
      .length,
    excluded: stages.filter((stage) => stage.evidence.type === "muted").length,
    received: report.received,
    expected: report.expected,
  };
};

const emptySummary = (object) => ({
  stages: [],
  confirmed: 0,
  insufficient: 0,
  deviations: 0,
  excluded: 0,
  received: 0,
  expected: object.schedule?.times?.length || 0,
});

const EQUIPMENT_LABELS = {
  excavator: "Экскаватор",
  bulldozer: "Бульдозер",
  crane: "Кран",
  tower_crane: "Башенный кран",
  mobile_crane: "Автокран",
  dump_truck: "Самосвал",
  truck: "Грузовик",
  loader: "Погрузчик",
  concrete_mixer: "Бетономешалка",
  concrete_pump: "Бетононасос",
};
export const equipmentLabel = (value = "") => {
  const key = value.trim().toLowerCase().replace(/[\s-]+/g, "_");
  return EQUIPMENT_LABELS[key] || value;
};
const movementFor = (object, response, serverBacked) => {
  if (!serverBacked) return null;
  const signal = response?.signals?.[0];
  if (!signal) return null;
  return {
    idleDays: signal.idle_days,
    equipment: equipmentLabel(signal.equipment_type),
    cameraName: signal.camera_name,
    startDate: signal.start_date,
    endDate: signal.end_date,
    observationCount: signal.observation_count,
    images: signal.images,
    detail: `Камера «${signal.camera_name}»`,
    note: signal.note,
  };
};

export function statusFor(object, date, report, serverBacked = false) {
  const summary = report?.stages ? summaryFromReport(report) : emptySummary(object);
  const worst = (type) => summary.stages.find((p) => p.evidence.type === type);
  if (object.archived)
    return {
      key: "archived",
      label: "В архиве",
      tone: "muted",
      detail: "История и настройки сохранены",
      summary,
    };
  if (object.draft)
    return {
      key: "draft",
      label: "Черновик",
      tone: "muted",
      detail: "Добавьте камеры и план работ",
      summary,
    };
  if (serverBacked && !report)
    return {
      key: "data",
      label: "Сводка загружается",
      tone: "neutral",
      detail: "Получаем оценку за выбранный день",
      summary,
    };
  if (report?.error)
    return {
      key: "data",
      label: "Сводка недоступна",
      tone: "neutral",
      detail: report.error,
      summary,
    };
  if (summary.deviations) {
    const stage = worst("warning");
    return {
      key: "deviation",
      label: "Возможное отклонение",
      tone: "warning",
      detail: `${stage.name} · ${stage.evidence.count}`,
      summary,
    };
  }
  if (summary.insufficient || !summary.stages.length || summary.confirmed === 0)
    return {
      key: "data",
      label: "Нужно больше данных",
      tone: "neutral",
      detail: summary.stages.length
        ? `${summary.confirmed} подтверждается · ${summary.insufficient} без оценки`
        : "Нет работ по плану на эту дату",
      summary,
    };
  return {
    key: "ontrack",
    label: "Всё по плану",
    tone: "success",
    detail: `${summary.confirmed} ${plural(summary.confirmed, "этап подтверждается", "этапа подтверждаются", "этапов подтверждаются")}`,
    summary,
  };
}

const iconFor = {
  success: IconCircleCheck,
  warning: IconAlertTriangle,
  neutral: IconInfoCircle,
  muted: IconClock,
};
export default function PortfolioDashboard({
  objects,
  reports = {},
  movements = {},
  serverBacked = false,
  date,
  today,
  onDate,
  onAdd,
  onOpen,
  Modal,
}) {
  const [filter, setFilter] = useState("all"),
    [query, setQuery] = useState(""),
    [signal, setSignal] = useState(null);
  const rows = objects.map((object) => ({
    object,
    status: statusFor(object, date, reports[object.id], serverBacked),
    movement: movementFor(object, movements[object.id], serverBacked),
    last: [...object.snapshots].sort((a, b) =>
      `${b.date} ${b.time}`.localeCompare(`${a.date} ${a.time}`),
    )[0],
  }));
  const metrics = [
    {
      key: "all",
      label: "Всего объектов",
      value: rows.length,
      detail: `${rows.filter((r) => !r.object.draft).length} в работе · ${rows.filter((r) => r.object.draft).length} черновик`,
      Icon: IconBuildings,
      tone: "blue",
    },
    {
      key: "ontrack",
      label: "Всё по плану",
      value: rows.filter((r) => r.status.key === "ontrack").length,
      detail: "По наблюдаемым этапам",
      Icon: IconCircleCheck,
      tone: "success",
    },
    {
      key: "deviation",
      label: "Возможные отклонения",
      value: rows.filter((r) => r.status.key === "deviation").length,
      detail: "Нужна проверка эксперта",
      Icon: IconAlertTriangle,
      tone: "warning",
    },
    {
      key: "idle",
      label: "Техника без перемещений",
      value: rows.filter((r) => r.movement?.idleDays).length,
      detail: "На снимках за несколько дней",
      Icon: IconPlayerPause,
      tone: "amber",
    },
  ];
  const shown = rows.filter(
    (r) =>
      (filter === "all" ||
        (filter === "idle" ? r.movement?.idleDays : r.status.key === filter)) &&
      `${r.object.name} ${r.object.address}`
        .toLocaleLowerCase("ru")
        .includes(query.trim().toLocaleLowerCase("ru")),
  );
  const lastLabel = (last) =>
    last
      ? `${last.date.split("-").reverse().slice(0, 2).join(".")} · ${last.time}`
      : "Проверок пока нет";
  return (
    <section className="portfolio-dashboard">
      <div className="heading-row">
        <div>
          <h1>Мои объекты</h1>
          <p className="subtitle">
            План работ, отклонения и активность техники — на одном экране
          </p>
        </div>
        <div className="heading-aside">
          <label className="heading-date">
            <IconClock size={15} />
            Сводка за день
            <input
              type="date"
              aria-label="День сводки"
              max={today}
              value={date}
              onChange={(e) => e.target.value && onDate(e.target.value)}
            />
          </label>
          <button className="button primary" onClick={onAdd}>
            <IconPlus size={20} />
            Добавить объект
          </button>
        </div>
      </div>
      <div className="portfolio-metrics">
        {metrics.map(({ key, label, value, detail, Icon, tone }) => (
          <button
            key={key}
            className={`portfolio-metric ${tone} ${filter === key ? "selected" : ""}`}
            aria-pressed={filter === key}
            onClick={() => setFilter(key)}
          >
            <span className="metric-label">
              {label}
              <Icon size={20} stroke={1.6} />
            </span>
            <strong>{value}</strong>
            <span className="metric-detail">{detail}</span>
          </button>
        ))}
      </div>
      <div className="portfolio-list-heading">
        <div>
          <h2>
            Объекты под контролем <span>{shown.length}</span>
          </h2>
          <p>Откройте сигнал, чтобы увидеть причину и исходные наблюдения</p>
        </div>
        <div className="portfolio-tools">
          <div className="search-field">
            <IconSearch size={18} />
            <input
              aria-label="Найти объект"
              placeholder="Название или адрес"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </div>
          <div
            className="filter-chips"
            role="group"
            aria-label="Дополнительные фильтры"
          >
            {[
              ["data", "Нужно больше данных"],
              ["draft", "Черновики"],
              ["archived", "Архив"],
            ].map(([key, label]) => (
              <button
                key={key}
                className={`chip ${filter === key ? "selected" : ""}`}
                aria-pressed={filter === key}
                onClick={() => setFilter(filter === key ? "all" : key)}
              >
                {label}
              </button>
            ))}
            {filter !== "all" && (
              <button className="chip reset" onClick={() => setFilter("all")}>
                <IconX size={14} />
                Сбросить
              </button>
            )}
          </div>
        </div>
      </div>
      <div className="portfolio-table">
        <div className="portfolio-columns" aria-hidden="true">
          <span>Объект</span>
          <span>План и работы</span>
          <span>Наблюдения техники</span>
          <span>Последняя проверка</span>
          <span />
        </div>
        {shown.map(({ object: o, status, movement, last }) => {
          const StatusIcon = iconFor[status.tone];
          return (
            <article
              key={o.id}
              className={`portfolio-row ${status.key === "deviation" ? "needs-review" : ""}`}
            >
              <button className="portfolio-object" onClick={() => onOpen(o.id)}>
                {o.cover || o.cams.find((c) => c.photo)?.photo ? (
                  <img
                    src={o.cover || o.cams.find((c) => c.photo).photo}
                    alt=""
                  />
                ) : (
                  <span className="portfolio-placeholder">
                    <IconBuildings size={29} stroke={1.4} />
                  </span>
                )}
                <span>
                  <small>{o.type}</small>
                  <h3>{o.name}</h3>
                  <span className="portfolio-address">
                    <IconMapPin size={13} />
                    {o.address || "Адрес не указан"}
                  </span>
                </span>
              </button>
              <div className="portfolio-plan">
                <button
                  className={`badge ${status.tone}`}
                  onClick={() =>
                    status.key === "draft"
                      ? onOpen(o.id)
                      : setSignal({ object: o, status, kind: "plan" })
                  }
                >
                  <StatusIcon size={16} />
                  {status.label}
                </button>
                <small>{status.detail}</small>
                {status.summary.excluded > 0 && (
                  <span className="portfolio-excluded">
                    {status.summary.excluded} вне визуального контроля
                  </span>
                )}
              </div>
              <div className="portfolio-motion">
                {movement?.idleDays ? (
                  <button
                    className="motion-alert"
                    onClick={() =>
                      setSignal({
                        object: o,
                        status,
                        movement,
                        kind: "motion",
                      })
                    }
                  >
                    <IconPlayerPause size={17} />
                    <span>
                      <strong>
                        Без перемещений {movement.idleDays}{" "}
                        {plural(movement.idleDays, "день", "дня", "дней")}
                      </strong>
                      <small>
                        {movement.equipment} · камера «{movement.cameraName}»
                      </small>
                    </span>
                    <IconChevron />
                  </button>
                ) : (
                  <>
                    <span className={movement ? "motion-active" : "subtle"}>
                      {movement ? (
                        <IconCheck size={17} />
                      ) : (
                        <IconClock size={16} />
                      )}
                      {movement
                        ? "Перемещения замечены"
                        : last
                          ? "Простоя не выявлено"
                          : "Наблюдений пока нет"}
                    </span>
                    <small>
                      {movement
                        ? movement.detail
                        : last
                          ? "Сигнал появляется после 3 дней без перемещений"
                          : "Появятся после проверок"}
                    </small>
                  </>
                )}
              </div>
              <div className="portfolio-last">
                <strong>{lastLabel(last)}</strong>
                {last ? (
                  <>
                    <span>
                      <IconCamera size={14} />
                      {last.cams.filter((c) => c.photo).length} из{" "}
                      {last.cams.length} камер
                    </span>
                    <small>
                      {status.summary.received} из {status.summary.expected}{" "}
                      проверок за день
                    </small>
                  </>
                ) : (
                  <small>Объект настраивается</small>
                )}
              </div>
              <button
                className="icon-button portfolio-open"
                aria-label={`Открыть объект ${o.name}`}
                onClick={() => onOpen(o.id)}
              >
                <IconArrowUpRight size={20} />
              </button>
            </article>
          );
        })}
        {!objects.length ? (
          <div className="empty">
            <IconBuildings size={38} />
            <h3>Рабочее пространство пустое</h3>
            <p>Здесь появятся ваши объекты. Другие пользователи их не видят.</p>
            <button className="button primary" onClick={onAdd}>
              <IconPlus size={19} />
              Добавить первый объект
            </button>
          </div>
        ) : (
          !shown.length && (
            <div className="empty">
              <IconSearch size={36} />
              <h3>Объекты не найдены</h3>
              <p>Попробуйте другой запрос или статус.</p>
              <button
                className="button"
                onClick={() => {
                  setQuery("");
                  setFilter("all");
                }}
              >
                Сбросить фильтры
              </button>
            </div>
          )
        )}
      </div>
      <p className="portfolio-footnote">
        <IconInfoCircle size={16} />
        Статус по плану и наблюдение за техникой — отдельные сигналы. Один
        объект может попасть в обе группы.
      </p>
      {signal && (
        <Modal
          title={
            signal.kind === "motion"
              ? `Без видимых перемещений ${signal.movement.idleDays} ${plural(signal.movement.idleDays, "день", "дня", "дней")}`
              : signal.status.label
          }
          onClose={() => setSignal(null)}
        >
          <div className="portfolio-signal">
            <span className="eyebrow">{signal.object.name}</span>
            {signal.kind === "motion" ? (
              <>
                <p>
                  {signal.movement.equipment} остаётся в одной зоне на
                  контрольных фотографиях.
                </p>
                <div className="signal-facts">
                  <span>
                    <IconCamera size={18} />
                    Камера «{signal.movement.cameraName}»
                  </span>
                  <span>
                    <IconCalendarLabel />
                    {signal.movement.startDate
                      ? `${shortDate(signal.movement.startDate)} — ${shortDate(signal.movement.endDate)}`
                      : `${signal.movement.idleDays} ${plural(signal.movement.idleDays, "день", "дня", "дней")}`}
                    {signal.movement.observationCount
                      ? ` · ${signal.movement.observationCount} наблюдений`
                      : " · контрольные снимки"}
                  </span>
                </div>
                {!!signal.movement.images?.length && (
                  <div className="signal-photos">
                    {[
                      signal.movement.images[0],
                      signal.movement.images.at(-1),
                    ].map((image) => (
                      <figure key={image.id}>
                        <img
                          src={image.url}
                          alt={`Положение техники: ${image.observed_at}`}
                        />
                        <figcaption>
                          {new Date(image.observed_at).toLocaleString("ru-RU", {
                            day: "numeric",
                            month: "long",
                            hour: "2-digit",
                            minute: "2-digit",
                          })}
                        </figcaption>
                      </figure>
                    ))}
                  </div>
                )}
                <p className="helper">
                  {signal.movement.note ||
                    "Между контрольными фотографиями техника могла работать. Проверьте ситуацию на площадке."}
                </p>
              </>
            ) : (
              <>
                <p>
                  {signal.status.key === "deviation"
                    ? `За день не найдены ожидаемые признаки этапа «${signal.status.summary.stages.find((p) => p.evidence.type === "warning")?.name}»: ${signal.status.summary.stages.find((p) => p.evidence.type === "warning")?.evidence.count}. Этап требует проверки экспертом.`
                    : signal.status.key === "ontrack"
                      ? "Все визуально наблюдаемые этапы подтверждаются повторными свидетельствами на фотографиях."
                      : "Котлован подтверждается. Для монтажа крана пока недостаточно повторных наблюдений."}
                </p>
                <div className="signal-facts">
                  <span>
                    <IconCamera size={18} />
                    {signal.object.cams.filter((c) => !c.archived).length}{" "}
                    камеры наблюдения
                  </span>
                  <span>
                    <IconClock size={18} />
                    {signal.status.summary.received} из{" "}
                    {signal.status.summary.expected} проверок за день
                  </span>
                </div>
                <p className="helper">
                  {signal.status.summary.excluded > 0
                    ? "Этапы вне визуального контроля не оцениваются по внешним камерам; их закрывает осмотр инженера."
                    : "Оценка относится к этапам, доступным визуальному контролю."}
                </p>
              </>
            )}
            <button
              className="button primary"
              onClick={() => {
                onOpen(signal.object.id);
                setSignal(null);
              }}
            >
              Открыть объект
              <IconArrowRight size={18} />
            </button>
          </div>
        </Modal>
      )}
    </section>
  );
}
function plural(n, one, few, many) {
  const mod100 = n % 100;
  if (mod100 >= 11 && mod100 <= 14) return many;
  const mod10 = n % 10;
  if (mod10 === 1) return one;
  if (mod10 >= 2 && mod10 <= 4) return few;
  return many;
}
function shortDate(value) {
  return value?.split("-").reverse().join(".") || "";
}
function IconChevron() {
  return <IconArrowUpRight size={15} />;
}
function IconCalendarLabel() {
  return <IconClock size={18} />;
}
