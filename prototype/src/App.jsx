import React, { useEffect, useRef, useState } from "react";
import {
  authApi,
  comparisonApi,
  inspectionApi,
  objectApi,
  snapshotApi,
} from "./api";
import {
  IconBuildingSkyscraper,
  IconBuildings,
  IconCamera,
  IconPlus,
  IconMinus,
  IconTrash,
  IconCheck,
  IconChevronRight,
  IconArrowLeft,
  IconArrowRight,
  IconSearch,
  IconLayoutDashboard,
  IconCalendar,
  IconHistory,
  IconSettings,
  IconLogout,
  IconX,
  IconInfoCircle,
  IconAlertTriangle,
  IconCircleCheck,
  IconClock,
  IconEyeOff,
  IconUpload,
  IconPhoto,
  IconMaximize,
  IconArchive,
  IconDeviceFloppy,
  IconMapPin,
  IconPencil,
  IconRefresh,
  IconLoader2,
  IconArrowUpRight,
  IconDownload,
  IconAdjustments,
  IconMenu2,
  IconSelector,
  IconLayoutGrid,
  IconClipboardCheck,
  IconFileDescription,
  IconCode,
  IconChevronLeft,
  IconUser,
  IconEye,
  IconPlayerPause,
} from "@tabler/icons-react";

import PhotoCheck from "./PhotoCheck";
import PortfolioDashboard, { equipmentLabel, statusFor } from "./PortfolioDashboard";
import {
  DEFAULT_SCHEDULE,
  INSPECTION_RESULTS,
  checkEvidence,
  scheduleOf,
  confirmBy,
  factsFor,
  snapshotSource,
  SOURCE_LABELS,
} from "./checks";

const NORTH = "/assets/site-north.png",
  ENTRANCE = "/assets/site-entrance.png",
  OVERVIEW = "/assets/site-overview.png";
const dateInZone = (timeZone = "Europe/Moscow") => {
  const parts = Object.fromEntries(
    new Intl.DateTimeFormat("en-US", {
      timeZone,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    })
      .formatToParts(new Date())
      .map((part) => [part.type, part.value]),
  );
  return `${parts.year}-${parts.month}-${parts.day}`;
};
const TODAY = dateInZone();
const dayOffset = (days) => {
  const value = new Date(`${TODAY}T12:00:00Z`);
  value.setUTCDate(value.getUTCDate() + days);
  return value.toISOString().slice(0, 10);
};
const uid = () => crypto.randomUUID();
const VIEW_TYPES = [
  ["fixed overview", "Обзорная точка"],
  ["fixed detail", "Детальная точка"],
  ["ptz preset", "Поворотная точка, пресет"],
];
const ORIENTATIONS = [
  ["north", "Север"],
  ["north-east", "Северо-восток"],
  ["east", "Восток"],
  ["south-east", "Юго-восток"],
  ["south", "Юг"],
  ["south-west", "Юго-запад"],
  ["west", "Запад"],
  ["north-west", "Северо-запад"],
];
const TIMEZONE_LABELS = {
  "Europe/Moscow": "Москва, UTC+3",
  "Asia/Yekaterinburg": "Екатеринбург, UTC+5",
  "Asia/Novosibirsk": "Новосибирск, UTC+7",
};
const timezoneLabel = (value) =>
  TIMEZONE_LABELS[value || "Europe/Moscow"] || value;
const snapshotState = (snapshot) =>
  snapshot.state || (snapshot.partial ? "partial" : "completed");
const HISTORY_STATE_META = {
  completed: { type: "success", label: "Анализ готов" },
  partial: { type: "warning", label: "Анализ частично" },
  error: { type: "warning", label: "Ошибка анализа" },
  queued: { type: "neutral", label: "В очереди" },
  analyzing: { type: "neutral", label: "Анализируется" },
  draft: { type: "neutral", label: "Черновик" },
};
const labelOf = (list, value) =>
  list.find(([key]) => key === value)?.[1] || value || "не указана";
const EDGE_NOTE =
  "Укажите стабильный ракурс и участки, которые действительно попадают в кадр. Эти данные используются и при ручной загрузке, и при подключении камеры через ONVIF/RTSP.";
const cameraSeed = () => [
  {
    id: uid(),
    code: "CAM-01",
    name: "Котлован",
    zone: "Северная сторона",
    viewDescription: "Котлован и северная граница площадки",
    viewType: "fixed detail",
    placement: "северная часть объекта",
    orientation: "south",
    coverage: ["котлован", "северная граница"],
    fovRevision: 2,
    photo: NORTH,
    demoRole: "pit",
  },
  {
    id: uid(),
    code: "CAM-02",
    name: "Въезд",
    zone: "Ворота № 1",
    viewDescription: "Въездная группа и разгрузочная площадка",
    viewType: "fixed detail",
    placement: "западная граница объекта",
    orientation: "east",
    coverage: ["въезд", "проезд", "разгрузка"],
    fovRevision: 1,
    photo: ENTRANCE,
    demoRole: "entrance",
  },
  {
    id: uid(),
    code: "CAM-03",
    name: "Общий план",
    zone: "Северо-восточная часть",
    viewDescription: "Общий вид котлована и корпуса 1",
    viewType: "fixed overview",
    placement: "северо-восточная часть объекта",
    orientation: "south-west",
    coverage: ["котлован", "корпус 1", "проезд"],
    fovRevision: 1,
    photo: OVERVIEW,
    demoRole: "overview",
  },
];
// Типы объектов из справочника заказчика (Excel «Сводный перечень строительных работ»).
const OBJECT_TYPES = [
  "Жильё",
  "Образование",
  "Здравоохранение",
  "Спорт",
  "Культура",
  "Административные здания",
  "ДОУ",
  "Офисно-деловой центр",
  "Дороги",
];
const objectTypeOptions = (current) =>
  (OBJECT_TYPES.includes(current) || !current
    ? OBJECT_TYPES
    : [current, ...OBJECT_TYPES]
  ).map((type) => <option key={type}>{type}</option>);
const planSeed = () => [
  {
    id: uid(),
    name: "Нулевой цикл",
    start: dayOffset(-5),
    end: dayOffset(7),
    observable: "Да",
    confirmBy: "cameras",
    zone: "Северная сторона",
    children: [
      {
        id: uid(),
        name: "Разработка котлована",
        evidenceKind: "excavation",
        start: dayOffset(-5),
        end: dayOffset(7),
        observable: "Да",
        confirmBy: "cameras",
        zone: "Северная сторона",
      },
      {
        id: uid(),
        name: "Бетонирование фундамента",
        start: dayOffset(1),
        end: dayOffset(13),
        observable: "Частично",
        confirmBy: "inspection",
        zone: "Северная сторона",
      },
    ],
  },
  {
    id: uid(),
    name: "Монтаж башенного крана",
    evidenceKind: "crane",
    start: dayOffset(-1),
    end: dayOffset(3),
    observable: "Частично",
    confirmBy: "cameras",
    zone: "Южная сторона",
  },
  {
    id: uid(),
    name: "Внутренние инженерные сети",
    start: TODAY,
    end: dayOffset(17),
    observable: "Нет",
    confirmBy: "inspection",
    zone: "Корпус 1",
  },
];
const OBSERVABILITY_FROM_API = {
  yes: "Да",
  partial: "Частично",
  no: "Нет",
};
const OBSERVABILITY_TO_API = {
  Да: "yes",
  Частично: "partial",
  Нет: "no",
};
const cameraFromApi = (camera) => ({
  id: camera.id,
  code: camera.code,
  name: camera.name,
  zone: camera.zone,
  sortOrder: camera.sort_order,
  archived: !camera.is_active,
  viewDescription: camera.view_description,
  viewType: camera.view_type,
  placement: camera.placement,
  orientation: camera.orientation,
  coverage: camera.coverage || [],
  fovRevision: camera.fov_revision,
  photo: null,
});
const planFromApi = (item) => ({
  id: item.id,
  stageCode: item.stage_code,
  name: item.name,
  note: item.note || "",
  start: item.start_date,
  end: item.end_date,
  confirmBy: item.confirmation_method,
  observable: OBSERVABILITY_FROM_API[item.observability] || "Да",
  cameraIds: item.camera_ids || [],
  outsideDirectory: item.is_outside_directory,
  version: item.version,
  children: item.children?.map(planFromApi) || undefined,
});
const inspectionFromApi = (item, localStageId = item.plan_item_id) => ({
  id: item.id,
  stageId: localStageId,
  date: item.observed_date,
  until: item.valid_until || "",
  verdict: item.verdict,
  author: item.author,
  role: item.role || "",
  comment: item.comment,
  superseded: item.superseded,
  attachments: item.attachments || [],
  photos: (item.attachments || [])
    .filter((attachment) => attachment.content_type.startsWith("image/"))
    .map((attachment) => attachment.url),
  real: true,
});
const mapAnalysisToObject = (analysis, snapshot, object) => {
  if (!analysis) return null;
  const frozenCameras = snapshot.plan_snapshot?.cameras || [];
  const cameraIds = new Map(
    frozenCameras.map((camera, index) => {
      const local =
        object.cams.find((item) => item.id === camera.camera_id) ||
        object.cams.find((item) => item.code === camera.camera_code) ||
        object.cams.find((item) => item.name === camera.name) ||
        object.cams[index];
      return [camera.camera_id, local?.id || camera.camera_id];
    }),
  );
  const localPlan = object.plan.filter(
    (item) =>
      item.start <= snapshot.observed_at.slice(0, 10) &&
      item.end >= snapshot.observed_at.slice(0, 10),
  );
  const planIds = new Map(
    (snapshot.plan_snapshot?.plan_items || []).map((item, index) => {
      const local =
        localPlan.find((row) => row.id === item.plan_item_id) ||
        localPlan.find((row) => row.name === item.stage_name) ||
        localPlan[index];
      return [item.plan_item_id, local?.id || item.plan_item_id];
    }),
  );
  return {
    ...analysis,
    camera_observations: analysis.camera_observations.map((item) => ({
      ...item,
      camera_id: cameraIds.get(item.camera_id) || item.camera_id,
    })),
    stage_evidence: analysis.stage_evidence.map((item) => ({
      ...item,
      plan_item_id: planIds.get(item.plan_item_id) || item.plan_item_id,
    })),
    evidence_items: analysis.evidence_items.map((item) => ({
      ...item,
      camera_id: cameraIds.get(item.camera_id) || item.camera_id,
      plan_item_id: planIds.get(item.plan_item_id) || item.plan_item_id,
    })),
    unexpected_evidence: analysis.unexpected_evidence.map((item) => ({
      ...item,
      camera_id: cameraIds.get(item.camera_id) || item.camera_id,
    })),
  };
};
const snapshotFromApi = (snapshot, object) => {
  const attempt = [...(snapshot.attempts || [])]
    .reverse()
    .find((item) => item.normalized_response || item.error_code);
  const analysis = mapAnalysisToObject(
    attempt?.normalized_response,
    snapshot,
    object,
  );
  const frozenCameras = snapshot.plan_snapshot?.cameras || [];
  const cameraForImage = (image) => {
    const frozen = frozenCameras.find(
      (camera) => camera.camera_id === image.camera_id,
    );
    return (
      object.cams.find((camera) => camera.id === image.camera_id) ||
      object.cams.find((camera) => camera.code === frozen?.camera_code) ||
      object.cams.find((camera) => camera.name === image.camera_name)
    );
  };
  const imageByCamera = new Map(
    snapshot.images.map((image) => [cameraForImage(image)?.id, image]),
  );
  const observedAt = snapshot.observed_at.slice(0, 16);
  return {
    id: snapshot.id,
    remoteObjectId: snapshot.object_id,
    date: observedAt.slice(0, 10),
    time: snapshot.control_slot || observedAt.slice(11, 16),
    source: snapshot.source,
    state: snapshot.state,
    partial: snapshot.state === "partial",
    real: true,
    plan: structuredClone(object.plan),
    analysis,
    analysisAttempt: attempt || null,
    attempts: snapshot.attempts || [],
    planSnapshot: snapshot.plan_snapshot,
    cams: object.cams.map((camera) => {
      const image = imageByCamera.get(camera.id);
      const observation = analysis?.camera_observations.find(
        (item) => item.camera_id === camera.id,
      );
      const evidenceFeatures =
        analysis?.evidence_items
          .filter(
            (item) =>
              item.camera_id === camera.id && item.polarity === "positive",
          )
          .map((item) => item.feature_code) || [];
      return {
        ...camera,
        imageId: image?.id,
        photo: image?.url || null,
        fileName: image?.original_name,
        source: image?.source || snapshot.source,
        fovRevision: image?.fov_revision || camera.fovRevision,
        failed: observation?.quality === "unreadable",
        facts: [
          ...(observation?.scene_facts || [])
            .filter((item) => item.state === "present")
            .map((item) => item.feature_code),
          ...evidenceFeatures,
        ],
      };
    }),
  };
};
const objectFromApi = (item) => {
  const object = {
    id: item.id,
    name: item.name,
    type: item.object_type,
    address: item.address,
    timezone: item.timezone,
    draft: item.is_draft,
    archived: item.is_archived,
    cams: item.cameras.map(cameraFromApi),
    plan: item.plan_items.map(planFromApi),
    schedule: {
      times: item.schedule.times,
      confirm: item.schedule.confirmation_threshold,
      absence: item.schedule.absence_threshold,
      version: item.schedule.version,
      effectiveFrom: item.schedule.effective_from,
    },
    inspections: [],
    snapshots: [],
  };
  object.snapshots = (item.snapshots || []).map((snapshot) =>
    snapshotFromApi(snapshot, object),
  );
  object.inspections = (item.inspections || []).map((inspection) =>
    inspectionFromApi(inspection),
  );
  // Обложка карточки — кадр общего плана из последней проверки объекта.
  const latest = [...object.snapshots]
    .filter((snapshot) => snapshot.cams.some((camera) => camera.photo))
    .sort((a, b) => `${b.date} ${b.time}`.localeCompare(`${a.date} ${a.time}`))[0];
  object.cover =
    latest?.cams.findLast((camera) => camera.photo)?.photo || null;
  return object;
};

const daySummaryFromApi = (report, object) => {
  const schedule = {
    times: report.times,
    confirm: report.stages[0]?.required_positive || scheduleOf(object).confirm,
    absence: report.stages[0]?.required_absence || scheduleOf(object).absence,
  };
  const stages = report.stages.map((row) => {
    const planItem = object.plan.find((item) => item.id === row.plan_item_id) ||
      object.plan.find(
        (item) =>
          item.stageCode === row.stage_code || item.name === row.stage_name,
      ) || {
        id: row.plan_item_id,
        stageCode: row.stage_code,
        name: row.stage_name,
        observable: OBSERVABILITY_FROM_API[row.observability] || "Да",
        confirmBy: row.confirmation_method,
        cameraIds: [],
        children: [],
      };
    const cells = row.cells.map((cell) => {
      const check = object.snapshots.find(
        (snapshot) => snapshot.id === cell.snapshot_id,
      );
      const sources = (cell.evidence_items || [])
        .map((evidence) => {
          const camera = check?.cams.find(
            (item) => item.id === evidence.camera_id,
          );
          return camera
            ? {
                ...camera,
                time: cell.slot,
                date: report.date,
                evidenceId: evidence.evidence_id,
                evidenceDescription: evidence.description,
                confidence: evidence.confidence,
                polarity: evidence.polarity,
              }
            : null;
        })
        .filter(Boolean);
      return {
        ...cell,
        time: cell.slot,
        check,
        sources,
      };
    });
    const sources = cells.flatMap((cell) => cell.sources);
    const inspection = row.source?.inspection_id
      ? object.inspections.find((item) => item.id === row.source.inspection_id)
      : null;
    const status = {
      inspection_confirmed: {
        type: "success",
        label: "Подтверждён инженером",
      },
      inspection_rejected: {
        type: "warning",
        label: "Не подтверждён инженером",
      },
      inspection_note: { type: "neutral", label: "Замечание инженера" },
      awaiting_inspection: { type: "muted", label: "Ожидает осмотра" },
      outside_visual_control: {
        type: "muted",
        label: "Вне визуального контроля",
      },
      confirmed: { type: "success", label: "Подтверждается" },
      possible_deviation: {
        type: "warning",
        label: "Возможное отклонение",
      },
      insufficient_data: { type: "neutral", label: "Недостаточно данных" },
    }[row.status] || { type: "neutral", label: "Недостаточно данных" };
    const count =
      row.source?.type === "inspection"
        ? `осмотр ${shortDate(row.source.observed_date)} · ${row.source.author}`
        : row.status === "possible_deviation"
          ? `видимых признаков работ нет в ${row.usable_intervals} из ${row.required_absence} пригодных проверок`
          : row.status === "awaiting_inspection" ||
              row.status === "outside_visual_control"
            ? "нужен осмотр инженера"
            : row.usable_intervals
              ? `признаки найдены в ${row.positive_intervals} из ${row.usable_intervals} ${checksOf(row.usable_intervals)} · для подтверждения нужно ${row.required_positive}`
              : `проверок пока не было · для подтверждения нужно ${row.required_positive}`;
    return {
      ...planItem,
      evidence: {
        ...status,
        source:
          row.source?.type === "inspection"
            ? "inspection"
            : row.source?.type === "inspection_pending"
              ? "inspection-pending"
              : "cameras",
        count,
        cells,
        positives: row.positive_intervals,
        usable: row.usable_intervals,
        required: row.required_positive,
        sources,
        inspection,
        explanation: row.status === "possible_deviation"
          ? `Работы по этапу не видны в ${row.usable_intervals} ${plural(row.usable_intervals, "пригодной проверке", "пригодных проверках", "пригодных проверках")}. Это сигнал для проверки на площадке, а не доказательство остановки работ.`
          : sources.length
            ? "Найдены визуальные признаки этапа в обработанных снимках."
            : "",
        limitations: [
          ...new Set(cells.flatMap((cell) => cell.limitations || [])),
        ],
      },
    };
  });
  return {
    schedule,
    stages,
    confirmed: stages.filter((item) => item.evidence.type === "success").length,
    insufficient: stages.filter((item) => item.evidence.type === "neutral")
      .length,
    deviations: stages.filter((item) => item.evidence.type === "warning")
      .length,
    excluded: stages.filter((item) => item.evidence.type === "muted").length,
    received: report.received,
    expected: report.expected,
    rulesVersion: report.rules_version,
    scheduleVersion: report.schedule_version,
  };
};

// Первый экран после входа: контроль дня первого рабочего объекта, иначе список.
const startRoute = (items) => {
  const first = items.find((item) => !item.draft && !item.archived);
  return first ? `/object/${first.id}/day` : "/objects";
};
const cameraToApi = (camera, index) => ({
  id: camera.id,
  client_id: camera.id,
  name: camera.name,
  zone: camera.zone || "",
  sort_order: index,
  view_description: camera.viewDescription || "",
  view_type: camera.viewType || VIEW_TYPES[0][0],
  placement: camera.placement || "",
  orientation: camera.orientation || "",
  coverage: camera.coverage || [],
});
const planToApi = (item) => ({
  id: item.id,
  client_id: item.id,
  stage_code: item.stageCode || "",
  name: item.name,
  note: item.note || "",
  start_date: item.start,
  end_date: item.end,
  confirmation_method: confirmBy(item),
  observability: OBSERVABILITY_TO_API[item.observable] || "yes",
  camera_ids: item.cameraIds || [],
  children: (item.children || []).map(planToApi),
});
const active = (cams) => cams.filter((c) => !c.archived);
const dateLabel = (d) =>
  new Date(d + "T12:00:00")
    .toLocaleDateString("ru-RU", {
      day: "numeric",
      month: "long",
      year: "numeric",
    })
    .replace(" г.", "");
const shortDate = (d) => d?.split("-").reverse().join(".");
const MONTHS_SHORT = [
  "янв", "фев", "мар", "апр", "май", "июн",
  "июл", "авг", "сен", "окт", "ноя", "дек",
];
const PLAN_PHASES = {
  now: ["blue", "Идёт сейчас"],
  done: ["muted", "Завершён"],
  next: ["neutral", "Впереди"],
};
// «из 1 проверки», «из 4 проверок»
const checksOf = (n) => plural(n, "проверки", "проверок", "проверок");
const plural = (n, one, few, many) => {
  const mod100 = n % 100;
  if (mod100 >= 11 && mod100 <= 14) return many;
  const mod10 = n % 10;
  if (mod10 === 1) return one;
  if (mod10 >= 2 && mod10 <= 4) return few;
  return many;
};
const cameraErrors = (cams) => {
  const errs = {};
  const names = new Map();
  cams.forEach((c) => {
    const n = c.name.trim().toLocaleLowerCase("ru");
    if (!n) errs[c.id] = "Введите название камеры";
    else if (c.name.trim().length > 80) errs[c.id] = "Не более 80 символов";
    else if (names.has(n)) {
      errs[c.id] = "Название уже используется";
      errs[names.get(n)] = "Название уже используется";
    }
    names.set(n, c.id);
  });
  return errs;
};
function Button({ children, kind = "", className = "", ...props }) {
  return (
    <button className={`button ${kind} ${className}`} {...props}>
      {children}
    </button>
  );
}
function Badge({ type = "neutral", children }) {
  const I =
    {
      success: IconCircleCheck,
      warning: IconAlertTriangle,
      neutral: IconInfoCircle,
      muted: IconEyeOff,
      blue: IconClock,
    }[type] || IconInfoCircle;
  return (
    <span className={`badge ${type}`}>
      <I size={16} />
      {children}
    </span>
  );
}
function Empty({ icon: Icon = IconCamera, title, detail, action }) {
  return (
    <div className="empty">
      <Icon size={42} stroke={1.4} />
      <h3>{title}</h3>
      {detail && <p>{detail}</p>}
      {action}
    </div>
  );
}
function Field({ label, error, children, help }) {
  return (
    <div className={`field ${error ? "has-error" : ""}`}>
      <label>
        {label}
        {children}
      </label>
      {error ? (
        <small className="error" role="alert">
          {error}
        </small>
      ) : (
        help && <small>{help}</small>
      )}
    </div>
  );
}
function Modal({ title, children, onClose, wide = false, className = "" }) {
  const ref = useRef(null);
  useEffect(() => {
    const prev = document.activeElement;
    ref.current?.querySelector("button,input,select")?.focus();
    const fn = (e) => {
      if (e.key === "Escape") onClose();
      if (e.key === "Tab") {
        const list = [
          ...ref.current.querySelectorAll(
            "button:not(:disabled),input,select,a[href]",
          ),
        ];
        const first = list[0],
          last = list.at(-1);
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last?.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first?.focus();
        }
      }
    };
    document.addEventListener("keydown", fn);
    return () => {
      document.removeEventListener("keydown", fn);
      prev?.focus();
    };
  }, []);
  return (
    <div
      className="modal-backdrop"
      onMouseDown={(e) => e.target === e.currentTarget && onClose()}
    >
      <section
        className={`modal ${wide ? "wide" : ""} ${className}`}
        role="dialog"
        aria-modal="true"
        aria-labelledby="modal-title"
        ref={ref}
      >
        <div className="modal-head">
          <h2 id="modal-title">{title}</h2>
          <button
            className="icon-button"
            aria-label="Закрыть"
            onClick={onClose}
          >
            <IconX />
          </button>
        </div>
        {children}
      </section>
    </div>
  );
}
// Окно «О сервисе»: краткое описание и методология анализа простыми словами.
// Числа совпадают с config/analysis/thresholds.v1.json, backend/app/day_rules.py и movement.py.
function AboutModal({ onClose, onCameras }) {
  const [tab, setTab] = useState("service");
  return (
    <Modal title="О сервисе СтройКонтроль" onClose={onClose} className="about">
      <div className="filter-chips about-tabs" role="tablist">
        {[
          ["service", "О сервисе"],
          ["method", "Как работает анализ"],
          ["architecture", "Архитектура"],
        ].map(([key, label]) => (
          <button
            key={key}
            role="tab"
            aria-selected={tab === key}
            className={`chip ${tab === key ? "selected" : ""}`}
            onClick={() => setTab(key)}
          >
            {label}
          </button>
        ))}
      </div>
      {tab === "service" ? (
        <div className="form-stack">
          <p>
            Сервис сопоставляет контрольные фотографии с планом работ и
            сохраняет объяснимую историю наблюдений по объекту.
          </p>
          <h3>Что можно попробовать</h3>
          <p>
            Создать объект, указать количество и названия камер, изменить план,
            загрузить фото, открыть результат и историю.
          </p>
          <div className="inline-note">
            <IconInfoCircle size={22} />
            <span>
              Для знакомства используйте заполненный пример demo / demo.
              Созданные в личном рабочем пространстве объекты и настройки
              сохраняются на сервере.
            </span>
          </div>
          <Button kind="primary" onClick={onCameras}>
            Посмотреть настройку камер
          </Button>
        </div>
      ) : tab === "architecture" ? (
        <div className="about-architecture">
          <p>Так устроен работающий демонстрационный стенд.</p>
          <a href="/assets/architecture-as-is.png" target="_blank" rel="noopener noreferrer">
            <img
              src="/assets/architecture-as-is.png"
              alt="Схема: браузер, Caddy и Nginx, FastAPI, PostgreSQL, хранилище снимков S3, GateLLM и Rusender"
            />
            Открыть схему в полном размере
          </a>
          <p className="helper">
            Фото и результаты сохраняются на сервере. Статус этапа вычисляют
            фиксированные правила по обработанным проверкам; выводы модели и
            ссылки на исходные кадры доступны в истории.
          </p>
        </div>
      ) : (
        <div className="about-method">
          <section>
            <h3>1. Проверка по фото</h3>
            <ol>
              <li>
                Фотографии сохраняются вместе с камерой, временем, источником
                («с камеры» или «загружено вручную») и отпечатком файла.
              </li>
              <li>
                Сервер собирает для модели контекст: какие камеры и что они
                видят, какие этапы идут по плану в этот день и как каждый этап
                выглядит на фото по справочнику.
              </li>
              <li>
                Все фотографии проверки уходят в модель одним запросом. Ответ
                приходит строго по схеме из пяти частей: наблюдения по каждой
                камере, вывод по каждому этапу, доказательства со ссылкой на
                камеру и фото, работы вне плана и краткий вывод.
              </li>
              <li>
                Сервер проверяет форму ответа и все ссылки. Ответ, который не
                прошёл проверку, запрашивается повторно, затем у резервной
                модели. Если не получилось, показывается ошибка — подставного
                результата нет.
              </li>
            </ol>
          </section>
          <section>
            <h3>2. Признаки этапов</h3>
            <p>
              Справочник этапов задаёт для каждой работы главные и
              второстепенные признаки, типичную технику, наблюдаемость камерами
              и способ подтверждения. Признаки подставляются в этап плана
              автоматически, когда он выбран из справочника. Техника сама по
              себе этап не подтверждает: нужен признак самой работы — например,
              открытый котлован, а не только экскаватор. Этап вне справочника
              камерами не оценивается, его закрывает осмотр инженера.
            </p>
          </section>
          <section>
            <h3>3. Оценка дня</h3>
            <p>
              Итог дня считает сервер по фиксированным правилам, без модели.
              Проверка относится к ближайшему времени расписания; повторно
              загруженный тот же файл второго подтверждения не даёт.
            </p>
            <ul>
              <li>
                <b>Признак найден</b> — модель нашла признаки этапа с
                уверенностью не ниже 0,72, и связанная с этапом камера дала
                пригодный кадр.
              </li>
              <li>
                <b>Признака нет</b> — модель уверенно (от 0,70) не нашла
                признаков.
              </li>
              <li>
                <b>Без вывода</b> — низкая уверенность, плохой кадр,
                противоречие или камеры этап не видят.
              </li>
            </ul>
            <table className="about-table">
              <tbody>
                {[
                  ["Есть осмотр инженера на эту дату", "Вывод инженера"],
                  ["Этап подтверждается только осмотром", "Ожидает осмотра"],
                  ["Камеры этап не видят", "Вне визуального контроля"],
                  ["Признак найден минимум в 2 проверках", "Подтверждается"],
                  [
                    "Ни одного признака при 3 и более проверках с выводом",
                    "Возможное отклонение",
                  ],
                  ["Во всех остальных случаях", "Недостаточно данных"],
                ].map(([condition, result]) => (
                  <tr key={result}>
                    <td>{condition}</td>
                    <td>{result}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="helper">
              Условия проверяются сверху вниз. Пороги 2 и 3 меняются в
              настройках объекта; у укрупнённого этапа засчитывается признак
              любого подэтапа.
            </p>
          </section>
          <section>
            <h3>4. Техника</h3>
            <p>
              Модель считает технику только внутри одной камеры. Суммы по
              объекту нет: один и тот же кран попадает в кадр нескольких камер,
              и сложение дало бы лишние машины.
            </p>
            <p>
              Сигнал «без видимых перемещений» строится из сравнений соседних
              кадров одной камеры внутри одного дня: модель отвечает, сдвинулась
              техника, не сдвинулась или определить нельзя. День засчитывается,
              если в нём минимум два кадра с разницей от трёх часов и все пары —
              «не сдвинулась» с уверенностью от 0,70 для техники одного типа.
              Три таких дня подряд при неизменном ракурсе дают сигнал. Пара
              «вечер → утро» не используется: к утру техника обычно стоит на
              стоянке. Сигнал не меняет статус плана, а снимки не доказывают
              непрерывный простой между проверками.
            </p>
          </section>
          <section>
            <h3>5. Что сохраняется</h3>
            <p>
              Исходные фотографии; план на момент проверки; каждая попытка
              анализа — модель, версия запроса, исходный и проверенный ответ,
              время и расход; итог дня с версиями правил, расписания и плана;
              осмотры инженера с вложениями. Прошлые дни не пересчитываются
              задним числом. В режиме разработчика у проверки виден исходный
              ответ модели.
            </p>
            <div className="inline-note">
              <IconInfoCircle size={20} />
              <span>
                Уверенность модели — вспомогательная оценка качества
                распознавания, а не вероятность того, что работа выполнена.
              </span>
            </div>
          </section>
        </div>
      )}
    </Modal>
  );
}
function Stepper({ value, onChange }) {
  return (
    <div className="stepper">
      <button
        aria-label="Уменьшить количество камер"
        disabled={Number(value) <= 0}
        onClick={() => onChange(Number(value) - 1)}
      >
        <IconMinus size={20} />
      </button>
      <input
        aria-label="Количество камер"
        type="number"
        min="0"
        max="16"
        step="1"
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
      <button
        aria-label="Увеличить количество камер"
        disabled={Number(value) >= 16}
        onClick={() => onChange(Number(value) + 1)}
      >
        <IconPlus size={20} />
      </button>
    </div>
  );
}

function CameraForm({
  cams,
  onChange,
  existing = false,
  onConfirm,
  needCamera = true,
  onValidityChange,
}) {
  const [quantity, setQuantity] = useState(cams.length),
    [countError, setCountError] = useState(""),
    [removal, setRemoval] = useState(null),
    [chosen, setChosen] = useState([]);
  useEffect(() => {
    setQuantity(cams.length);
  }, [cams.length]);
  const errors = cameraErrors(cams);
  useEffect(() => {
    onValidityChange?.(
      !countError && !Object.keys(errors).length && cams.length > 0,
    );
  }, [countError, JSON.stringify(errors), cams.length]);
  const requestCount = (raw) => {
    setQuantity(raw);
    const n = Number(raw);
    if (raw === "" || !Number.isInteger(n) || n < 0 || n > 16) {
      setCountError("Введите целое число от 0 до 16");
      return;
    }
    setCountError("");
    if (n < cams.length) {
      setRemoval(cams.length - n);
      setChosen(cams.slice(n).map((c) => c.id));
      return;
    }
    if (n > cams.length) {
      const all = [...cams];
      while (all.length < n) {
        let k = 1;
        while (all.some((c) => c.name.toLowerCase() === `камера ${k}`)) k++;
        all.push({
          id: uid(),
          code: `CAM-${String(all.length + 1).padStart(2, "0")}`,
          name: `Камера ${k}`,
          zone: "",
          viewDescription: "",
          viewType: VIEW_TYPES[0][0],
          placement: "",
          orientation: "",
          coverage: [],
          fovRevision: 1,
          photo: null,
        });
      }
      onChange(all);
    }
  };
  const removeOne = (id) => {
    setRemoval(1);
    setChosen([id]);
  };
  return (
    <>
      <div className="camera-quantity">
        <strong>Количество камер</strong>
        <Stepper value={quantity} onChange={requestCount} />
      </div>
      <p className={`helper ${countError ? "error" : ""}`}>
        {countError || "Названия можно изменить позже."}
      </p>
      <div className="camera-form-table">
        <div className="camera-grid table-head">
          <span>№</span>
          <span></span>
          <span>Название камеры</span>
          <span>Зона обзора</span>
          <span></span>
        </div>
        {cams.map((c, i) => (
          <div className="camera-grid camera-form-row" key={c.id}>
            <span className="row-number">{String(i + 1).padStart(2, "0")}</span>
            <IconCamera size={27} stroke={1.6} />
            <div>
              <input
                aria-label={`Название камеры ${i + 1}`}
                aria-invalid={!!errors[c.id]}
                value={c.name}
                maxLength={80}
                onChange={(e) =>
                  onChange(
                    cams.map((x) =>
                      x.id === c.id ? { ...x, name: e.target.value } : x,
                    ),
                  )
                }
              />
              {errors[c.id] && (
                <small className="error" role="alert">
                  {errors[c.id]}
                </small>
              )}
            </div>
            <input
              aria-label={`Зона обзора камеры ${i + 1}`}
              value={c.zone}
              maxLength={200}
              placeholder="Необязательно"
              onChange={(e) =>
                onChange(
                  cams.map((x) =>
                    x.id === c.id ? { ...x, zone: e.target.value } : x,
                  ),
                )
              }
            />
            <button
              className="icon-button"
              aria-label={`Убрать камеру ${c.name}`}
              onClick={() => removeOne(c.id)}
            >
              <IconTrash size={23} />
            </button>
          </div>
        ))}
      </div>
      {cams.length === 0 && (
        <Empty
          title="Камеры пока не добавлены"
          detail="Добавьте точку наблюдения, чтобы загружать снимки."
        />
      )}
      <button
        className="text-button add-camera"
        disabled={cams.length >= 16}
        onClick={() => requestCount(cams.length + 1)}
      >
        <IconPlus size={23} />
        Добавить камеру
      </button>
      <p className="helper">
        {existing
          ? "При переименовании история снимков сохраняется."
          : "Фото загружаются после создания объекта."}
      </p>
      {needCamera && cams.length === 0 && (
        <p className="error">
          Для продолжения нужна хотя бы одна камера. Можно сохранить черновик.
        </p>
      )}
      {onConfirm && (
        <Button
          kind="primary"
          disabled={!!countError || !!Object.keys(errors).length}
          onClick={onConfirm}
        >
          Сохранить камеры
        </Button>
      )}
      {removal !== null && (
        <Modal
          title={
            existing ? "Какие камеры архивировать?" : "Убрать камеры из списка?"
          }
          onClose={() => {
            setRemoval(null);
            setQuantity(cams.length);
          }}
        >
          <p>
            Выберите {removal} {removal === 1 ? "камеру" : "камеры"}.{" "}
            {existing
              ? "Их снимки и результаты останутся в истории."
              : "Введённые данные выбранных строк будут удалены."}
          </p>
          <div className="check-list">
            {cams.map((c) => (
              <label key={c.id}>
                <input
                  type="checkbox"
                  checked={chosen.includes(c.id)}
                  onChange={() =>
                    setChosen(
                      chosen.includes(c.id)
                        ? chosen.filter((id) => id !== c.id)
                        : [...chosen, c.id],
                    )
                  }
                />
                <IconCamera size={20} />
                {c.name || "Без названия"}
              </label>
            ))}
          </div>
          <div className="modal-actions">
            <Button
              onClick={() => {
                setRemoval(null);
                setQuantity(cams.length);
              }}
            >
              Отмена
            </Button>
            <Button
              kind="primary"
              disabled={chosen.length !== removal}
              onClick={() => {
                onChange(cams.filter((c) => !chosen.includes(c.id)));
                setRemoval(null);
              }}
            >
              {existing ? "Архивировать выбранные" : "Убрать выбранные"}
            </Button>
          </div>
        </Modal>
      )}
    </>
  );
}

function PlanEditor({
  plan,
  onChange,
  cams,
  objectType = "Жильё",
  compact = false,
  directoryItems,
}) {
  const [edit, setEdit] = useState(null),
    [err, setErr] = useState(""),
    [picked, setPicked] = useState([]),
    [grouping, setGrouping] = useState(null),
    [phaseChoice, setPhaseFilter] = useState(null);
  // Справочник приходит с сервера по типу объекта; локального запасного списка нет.
  const directory = directoryItems || [];
  const known = new Set(directory.map((d) => d.name));
  const count = plan.reduce((n, p) => n + 1 + (p.children?.length || 0), 0);
  // Положение этапа относительно сегодняшнего дня: календарный план целиком,
  // текущие этапы выделены — именно они попадают в проверки и контроль дня.
  const phaseOf = (item) =>
    item.end < TODAY ? "done" : item.start > TODAY ? "next" : "now";
  const phaseCounts = plan.reduce(
    (acc, p) => ({ ...acc, [phaseOf(p)]: acc[phaseOf(p)] + 1 }),
    { now: 0, done: 0, next: 0 },
  );
  // По умолчанию — идущие сейчас этапы; в мастере создания объекта — весь план.
  const phaseFilter = compact
    ? "all"
    : phaseChoice || (phaseCounts.now ? "now" : "all");
  const visiblePlan = plan.filter(
    (p) => phaseFilter === "all" || phaseOf(p) === phaseFilter,
  );
  const allItems = plan.flatMap((p) => [p, ...(p.children || [])]);
  const dayNumber = (d) => Date.parse(`${d}T00:00:00Z`) / 86400000;
  const rangeStart = Math.min(
    dayNumber(TODAY),
    ...allItems.map((p) => dayNumber(p.start)),
  );
  const rangeDays =
    Math.max(dayNumber(TODAY), ...allItems.map((p) => dayNumber(p.end))) +
    1 -
    rangeStart;
  const trackLeft = (d) => ((dayNumber(d) - rangeStart) / rangeDays) * 100;
  const todayShare = (dayNumber(TODAY) - rangeStart + 0.5) / rangeDays;
  // Деления шкалы по началам месяцев: для длинного плана — по кварталам.
  const axisTicks = [];
  {
    const first = new Date(rangeStart * 86400000);
    const step = rangeDays > 540 ? 6 : rangeDays > 210 ? 3 : 1;
    for (
      let y = first.getUTCFullYear(), m = first.getUTCMonth() + 1;
      ;
      m += 1
    ) {
      const month = m % 12,
        year = y + Math.floor(m / 12),
        day = Date.UTC(year, month, 1) / 86400000,
        share = (day - rangeStart) / rangeDays;
      if (share >= 0.97) break;
      if (month % step === 0 && share > 0.03)
        axisTicks.push({
          share,
          label:
            month === 0 || !axisTicks.length
              ? `${MONTHS_SHORT[month]} ${year}`
              : MONTHS_SHORT[month],
        });
    }
  }
  const blank = () => ({
    id: uid(),
    name: "",
    start: TODAY,
    end: TODAY,
    observable: "Да",
    confirmBy: "cameras",
    zone: "",
    cameraIds: [],
  });
  const applyFromDirectory = (item, name) => {
    const d = directory.find((x) => x.name === name);
    return d ? { ...item, ...d, name } : { ...item, name };
  };
  const saveItem = (item, parentId) => {
    if (!parentId) {
      onChange(
        plan.some((p) => p.id === item.id)
          ? plan.map((p) => (p.id === item.id ? { ...p, ...item } : p))
          : [...plan, item],
      );
      return;
    }
    onChange(
      plan.map((p) =>
        p.id === parentId
          ? {
              ...p,
              children: p.children.map((c) =>
                c.id === item.id ? { ...c, ...item } : c,
              ),
            }
          : p,
      ),
    );
  };
  const removeItem = (item, parentId) =>
    onChange(
      parentId
        ? plan.map((p) =>
            p.id === parentId
              ? { ...p, children: p.children.filter((c) => c.id !== item.id) }
              : p,
          )
        : plan.filter((p) => p.id !== item.id),
    );
  const ungroup = (group) =>
    onChange(
      plan.flatMap((p) =>
        p.id === group.id ? (p.children || []).map((c) => ({ ...c })) : [p],
      ),
    );
  const makeGroup = () => {
    const members = plan.filter((p) => picked.includes(p.id));
    if (members.length < 2) return;
    const group = {
      id: uid(),
      name: grouping.name.trim(),
      confirmBy: grouping.confirmBy,
      observable: members.some((m) => m.observable === "Да")
        ? "Да"
        : members.some((m) => m.observable === "Частично")
          ? "Частично"
          : "Нет",
      zone: members[0].zone,
      start: members.map((m) => m.start).sort()[0],
      end: members
        .map((m) => m.end)
        .sort()
        .at(-1),
      cameraIds: [...new Set(members.flatMap((m) => m.cameraIds || []))],
      children: members.map((m) => ({ ...m })),
    };
    const first = plan.findIndex((p) => p.id === members[0].id);
    const rest = plan.filter((p) => !picked.includes(p.id));
    onChange([...rest.slice(0, first), group, ...rest.slice(first)]);
    setPicked([]);
    setGrouping(null);
  };
  const methodBadge = (item) => (
    <span className="source-tag">
      {confirmBy(item) === "inspection" ? (
        <IconClipboardCheck size={14} />
      ) : (
        <IconCamera size={14} />
      )}
      {confirmBy(item) === "inspection" ? "Осмотром" : "По камерам"}
    </span>
  );
  const row = (item, parent) => (
    <tr
      key={item.id}
      className={`${parent ? "plan-child" : ""} plan-${phaseOf(item)}`}
    >
      <td>
        <div className="plan-name">
          {!parent && (
            <input
              type="checkbox"
              aria-label={`Выбрать этап ${item.name}`}
              checked={picked.includes(item.id)}
              disabled={!!item.children?.length}
              onChange={(e) =>
                setPicked(
                  e.target.checked
                    ? [...picked, item.id]
                    : picked.filter((id) => id !== item.id),
                )
              }
            />
          )}
          <span>
            <strong>
              {item.name}
              {!!item.children?.length && (
                <span className="substage-count">
                  {item.children.length}{" "}
                  {plural(
                    item.children.length,
                    "подэтап",
                    "подэтапа",
                    "подэтапов",
                  )}
                </span>
              )}
              {!known.has(item.name) && !item.children?.length && (
                <span className="substage-count muted">вне справочника</span>
              )}
            </strong>
            <small>{item.zone || "Зона не указана"}</small>
          </span>
        </div>
      </td>
      <td className="plan-period">
        <span>
          {shortDate(item.start)} — {shortDate(item.end)}
        </span>
        {!compact && (
          <span className={`badge ${PLAN_PHASES[phaseOf(item)][0]}`}>
            {PLAN_PHASES[phaseOf(item)][1]}
          </span>
        )}
      </td>
      {!compact && (
        <td className="plan-track-cell" style={{ "--today": todayShare }}>
          <div className="plan-track" aria-hidden="true">
            <span
              className="plan-bar"
              style={{
                left: `${trackLeft(item.start)}%`,
                width: `${Math.max(
                  trackLeft(item.end) + 100 / rangeDays - trackLeft(item.start),
                  0.8,
                )}%`,
              }}
            />
          </div>
        </td>
      )}
      <td>{methodBadge(item)}</td>
      <td>
        <div className="plan-row-actions">
          {!!item.children?.length && (
            <button className="text-button small" onClick={() => ungroup(item)}>
              Разгруппировать
            </button>
          )}
          <button
            className="icon-button"
            aria-label={`Изменить этап ${item.name}`}
            onClick={() => {
              setEdit({
                ...item,
                cameraIds: item.cameraIds || [],
                parentId: parent?.id || null,
              });
              setErr("");
            }}
          >
            <IconPencil size={19} />
          </button>
        </div>
      </td>
    </tr>
  );
  return (
    <>
      <div className="section-heading">
        <div>
          <h2>{compact ? "Этапы строительства" : "Календарный план"}</h2>
          <p className="helper">
            Справочник по типу объекта «{objectType}» · {count}{" "}
            {plural(count, "этап", "этапа", "этапов")} вместе с подэтапами
          </p>
        </div>
        <div className="actions">
          {picked.length >= 2 && (
            <Button
              kind="primary"
              onClick={() =>
                setGrouping({
                  name: `${plan.find((p) => p.id === picked[0]).name} и другие`,
                  confirmBy: "cameras",
                })
              }
            >
              <IconLayoutGrid size={19} />
              Объединить в этап ({picked.length})
            </Button>
          )}
          <Button onClick={() => setEdit({ ...blank(), parentId: null })}>
            <IconPlus size={19} />
            Добавить этап
          </Button>
        </div>
      </div>
      {!compact && !!plan.length && (
        <div className="filter-chips plan-phase-filter">
          {[
            ["all", "Все этапы", plan.length],
            ["now", "Идут сейчас", phaseCounts.now],
            ["done", "Завершены", phaseCounts.done],
            ["next", "Впереди", phaseCounts.next],
          ].map(([key, label, n]) => (
            <button
              key={key}
              className={`chip ${phaseFilter === key ? "selected" : ""}`}
              aria-pressed={phaseFilter === key}
              onClick={() => setPhaseFilter(key)}
            >
              {label}
              <span className="chip-count">{n}</span>
            </button>
          ))}
        </div>
      )}
      {plan.length ? (
        <div className="data-table plan-table">
          <table>
            <thead>
              <tr>
                <th>Этап / зона работ</th>
                <th>Сроки</th>
                {!compact && (
                  <th
                    className="plan-track-head"
                    style={{ "--today": todayShare }}
                  >
                    <div className="plan-axis">
                      {axisTicks.map((tick) => (
                        <span
                          key={tick.label}
                          style={{ left: `${tick.share * 100}%` }}
                        >
                          {tick.label}
                        </span>
                      ))}
                      <em>
                        Сегодня,{" "}
                        {Number(TODAY.slice(8))}{" "}
                        {MONTHS_SHORT[Number(TODAY.slice(5, 7)) - 1]}
                      </em>
                    </div>
                  </th>
                )}
                <th>Способ подтверждения</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {visiblePlan.flatMap((p) => [
                row(p),
                ...(p.children || []).map((c) => row(c, p)),
              ])}
            </tbody>
          </table>
        </div>
      ) : (
        <Empty
          icon={IconCalendar}
          title="В плане пока нет этапов"
          detail="Добавьте работу из справочника и укажите период её выполнения."
        />
      )}
      <div className="inline-note">
        <IconInfoCircle size={19} />
        <span>
          Оценивается верхний уровень плана: признаки укрупнённого этапа —
          объединение признаков его подэтапов. Этап со способом «осмотром» не
          оценивается по камерам, его закрывает осмотр инженера.
        </span>
      </div>
      {grouping && (
        <Modal title="Объединение этапов" onClose={() => setGrouping(null)}>
          <div className="form-stack">
            <p className="helper">
              Выбранные этапы станут подэтапами одного укрупнённого этапа.
              Период возьмётся по крайним датам, признаки объединятся, проверки
              будут оценивать только верхний этап.
            </p>
            <ul className="group-members">
              {plan
                .filter((p) => picked.includes(p.id))
                .map((p) => (
                  <li key={p.id}>
                    <IconChevronRight size={15} />
                    {p.name}
                  </li>
                ))}
            </ul>
            <Field label="Название укрупнённого этапа">
              <input
                value={grouping.name}
                onChange={(e) =>
                  setGrouping({ ...grouping, name: e.target.value })
                }
              />
            </Field>
            <Field label="Способ подтверждения укрупнённого этапа">
              <select
                value={grouping.confirmBy}
                onChange={(e) =>
                  setGrouping({ ...grouping, confirmBy: e.target.value })
                }
              >
                <option value="cameras">По камерам</option>
                <option value="inspection">Осмотром инженера</option>
              </select>
            </Field>
            <div className="modal-actions">
              <Button onClick={() => setGrouping(null)}>Отмена</Button>
              <Button
                kind="primary"
                disabled={!grouping.name.trim()}
                onClick={makeGroup}
              >
                Объединить
              </Button>
            </div>
          </div>
        </Modal>
      )}
      {edit && (
        <Modal
          title={
            edit.parentId
              ? "Редактирование подэтапа"
              : plan.some((p) => p.id === edit.id)
                ? "Редактирование этапа"
                : "Новый этап"
          }
          onClose={() => setEdit(null)}
        >
          <div className="form-stack">
            <Field
              label="Этап из справочника"
              help={`Работы, применимые к типу «${objectType}»`}
            >
              <input
                value={edit.name}
                list="stage-types"
                onChange={(e) =>
                  setEdit(applyFromDirectory(edit, e.target.value))
                }
              />
              <datalist id="stage-types">
                {directory.map((d) => (
                  <option key={d.name}>{d.name}</option>
                ))}
              </datalist>
            </Field>
            {(edit.directoryNote || edit.includes?.length > 0) && (
              <div className="inline-note stage-includes">
                <IconInfoCircle size={18} />
                <span>
                  {edit.directoryNote}
                  {edit.directoryNote && edit.includes?.length > 0 && " "}
                  {edit.includes?.length > 0 &&
                    `Входит: ${edit.includes.slice(0, 6).join(", ")}${
                      edit.includes.length > 6
                        ? ` и ещё ${edit.includes.length - 6}`
                        : ""
                    }.`}
                </span>
              </div>
            )}
            <div className="two-fields">
              <Field label="Дата начала">
                <input
                  type="date"
                  value={edit.start}
                  onChange={(e) => setEdit({ ...edit, start: e.target.value })}
                />
              </Field>
              <Field label="Дата окончания">
                <input
                  type="date"
                  value={edit.end}
                  onChange={(e) => setEdit({ ...edit, end: e.target.value })}
                />
              </Field>
            </div>
            <div className="two-fields">
              <Field
                label="Способ подтверждения"
                help="Осмотр закрывает работы, которых не видно с камер"
              >
                <select
                  value={confirmBy(edit)}
                  onChange={(e) =>
                    setEdit({ ...edit, confirmBy: e.target.value })
                  }
                >
                  <option value="cameras">По камерам</option>
                  <option value="inspection">Осмотром инженера</option>
                </select>
              </Field>
              <Field label="Визуальная наблюдаемость">
                <select
                  value={edit.observable}
                  onChange={(e) =>
                    setEdit({ ...edit, observable: e.target.value })
                  }
                >
                  <option>Да</option>
                  <option>Частично</option>
                  <option>Нет</option>
                </select>
              </Field>
            </div>
            <Field label="Зона работ">
              <input
                value={edit.zone}
                onChange={(e) => setEdit({ ...edit, zone: e.target.value })}
              />
            </Field>
            {confirmBy(edit) === "cameras" && (
              <>
                <span className="field-label">
                  Камеры, которые покрывают зону
                </span>
                <div className="check-list">
                  {cams.map((c) => (
                    <label key={c.id}>
                      <input
                        type="checkbox"
                        checked={(edit.cameraIds || []).includes(c.id)}
                        onChange={(e) =>
                          setEdit({
                            ...edit,
                            cameraIds: e.target.checked
                              ? [...(edit.cameraIds || []), c.id]
                              : (edit.cameraIds || []).filter(
                                  (id) => id !== c.id,
                                ),
                          })
                        }
                      />
                      {c.name}
                    </label>
                  ))}
                </div>
              </>
            )}
            {err && (
              <p className="error" role="alert">
                {err}
              </p>
            )}
            <div className="modal-actions">
              {(plan.some((p) => p.id === edit.id) || edit.parentId) && (
                <Button
                  kind="danger"
                  onClick={() => {
                    removeItem(edit, edit.parentId);
                    setEdit(null);
                  }}
                >
                  Удалить этап
                </Button>
              )}
              <Button
                kind="primary"
                onClick={() => {
                  if (!edit.name.trim() || !edit.start || !edit.end) {
                    setErr("Заполните название и даты");
                    return;
                  }
                  if (edit.start > edit.end) {
                    setErr("Дата окончания не может быть раньше начала");
                    return;
                  }
                  const { parentId, ...item } = edit;
                  saveItem(item, parentId);
                  setEdit(null);
                }}
              >
                Сохранить этап
              </Button>
            </div>
          </div>
        </Modal>
      )}
    </>
  );
}

export default function App() {
  const [route, setRoute] = useState(location.hash.slice(1) || "/login");
  const [objects, setObjects] = useState([]);
  const [draft, setDraft] = useState(() => ({
    name: "ЖК Северный парк",
    type: "Жильё",
    address: "",
    timezone: "Europe/Moscow",
    schedule: { ...DEFAULT_SCHEDULE },
    cams: cameraSeed().map((c) => ({ ...c, photo: null })),
    plan: planSeed(),
  }));
  const [toast, setToast] = useState(""),
    [profile, setProfile] = useState(false),
    [navigationOpen, setNavigationOpen] = useState(false),
    [switcherOpen, setSwitcherOpen] = useState(false),
    [photo, setPhoto] = useState(null),
    [help, setHelp] = useState(false);
  const [editingCams, setEditingCams] = useState(null),
    [archive, setArchive] = useState(false),
    [confirm, setConfirm] = useState(null);
  const [snapshotDate, setSnapshotDate] = useState(TODAY),
    [snapshotTime, setSnapshotTime] = useState("15:00"),
    [expandedStage, setExpandedStage] = useState(null),
    [checkKey, setCheckKey] = useState(0);
  const [viewDate, setViewDate] = useState(TODAY),
    [dayCell, setDayCell] = useState(null),
    [inspectionForm, setInspectionForm] = useState(null),
    [inspectionFilters, setInspectionFilters] = useState({
      stageId: "all",
      date: "",
      verdict: "all",
    }),
    [historyView, setHistoryView] = useState("list"),
    [filmFrom, setFilmFrom] = useState(""),
    [filmCompare, setFilmCompare] = useState(null),
    [comparisonResult, setComparisonResult] = useState(null),
    [comparisonLoading, setComparisonLoading] = useState(false);
  const [historyDate, setHistoryDate] = useState(""),
    [historyCamera, setHistoryCamera] = useState("all"),
    [historyStatus, setHistoryStatus] = useState("all"),
    [historySource, setHistorySource] = useState("all"),
    [passport, setPassport] = useState(null),
    [devMode, setDevMode] = useState(false),
    [account, setAccount] = useState(null),
    [authReady, setAuthReady] = useState(false),
    [authSubmitting, setAuthSubmitting] = useState(false),
    [saving, setSaving] = useState(false),
    [stageDirectory, setStageDirectory] = useState(null);
  const [authMode, setAuthMode] = useState("login"),
    [signup, setSignup] = useState({ email: "", password: "", error: "" });
  const [login, setLogin] = useState({ name: "", password: "", error: "" }),
    [formError, setFormError] = useState(""),
    [cameraValid, setCameraValid] = useState(true);
  const [dayReport, setDayReport] = useState(null),
    [dayReportLoading, setDayReportLoading] = useState(false),
    [dayReportError, setDayReportError] = useState(""),
    [dayReportNonce, setDayReportNonce] = useState(0);
  const [dayMovement, setDayMovement] = useState(null);
  const [portfolioReports, setPortfolioReports] = useState({});
  const [portfolioMovements, setPortfolioMovements] = useState({});
  const wizard = route.startsWith("/new"),
    step = Math.max(
      0,
      ["object", "cameras", "plan", "review"].indexOf(route.split("/")[2]),
    );
  const EMPTY_OBJECT = {
    id: "none",
    name: "Объектов пока нет",
    type: "",
    address: "",
    schedule: { ...DEFAULT_SCHEDULE },
    inspections: [],
    cams: [],
    plan: [],
    snapshots: [],
    draft: true,
  };
  const object =
    objects.find((o) => o.id === route.split("/")[2]) ||
    objects[0] ||
    EMPTY_OBJECT;
  const tab = route.split("/")[3] || "day";
  const navigationTab =
    tab === "snapshot" ? "day" : tab === "result" ? "history" : tab;
  const cams = active(object.cams);
  const nav = (p) => {
    location.hash = p;
    setNavigationOpen(false);
    setSwitcherOpen(false);
    setEditingCams(null);
    setArchive(false);
    setFormError("");
    window.scrollTo(0, 0);
  };
  const objnav = (t) => nav(`/object/${object.id}/${t}`);
  const updateObject = (fn) =>
    setObjects((objs) => objs.map((o) => (o.id === object.id ? fn(o) : o)));
  const notify = (s) => {
    setToast(s);
    setTimeout(() => setToast(""), 3500);
  };
  useEffect(() => {
    const fn = () => setRoute(location.hash.slice(1) || "/login");
    window.addEventListener("hashchange", fn);
    return () => window.removeEventListener("hashchange", fn);
  }, []);
  useEffect(() => {
    let cancelled = false;
    authApi
      .me()
      .then(({ user }) => {
        if (cancelled) return;
        setAccount({ kind: "user", demo: user.is_demo, email: user.email });
        return objectApi.listDetails().then((items) => {
          if (cancelled) return;
          const loaded = items.map(objectFromApi);
          setObjects(loaded);
          if (route === "/login") nav(startRoute(loaded));
        });
      })
      .catch(() => {
        if (cancelled) return;
        setAccount(null);
        setObjects([]);
        if (route !== "/login") nav("/login");
      })
      .finally(() => {
        if (!cancelled) setAuthReady(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);
  useEffect(() => {
    document.title =
      "СтройКонтроль — " +
      (route === "/login"
        ? "Вход"
        : wizard
          ? "Новый объект"
          : route === "/objects"
            ? "Мои объекты"
            : object.name);
  }, [route, wizard, object.name]);
  useEffect(() => {
    if (authReady && !account && route !== "/login") nav("/login");
  }, [authReady, account, route]);
  useEffect(() => {
    if (account?.kind !== "user") {
      setStageDirectory(null);
      return;
    }
    let cancelled = false;
    const objectType = wizard ? draft.type : object.type;
    if (!objectType) {
      setStageDirectory(null);
      return;
    }
    objectApi
      .stageDirectory(objectType)
      .then((items) => {
        if (cancelled) return;
        setStageDirectory(
          items.map((item) => ({
            name: item.name,
            stageCode: item.code,
            evidenceKind: item.visual_class,
            observable: OBSERVABILITY_FROM_API[item.observability] || "Да",
            confirmBy: item.confirmation_method,
            profile: item.profile,
            section: item.section,
            includes: item.includes || [],
            directoryNote: item.note || "",
          })),
        );
      })
      .catch(() => {
        if (!cancelled) setStageDirectory(null);
      });
    return () => {
      cancelled = true;
    };
  }, [account?.kind, wizard, draft.type, object.type]);
  useEffect(() => {
    if (account?.kind !== "user") {
      setDayReport(null);
      setDayReportLoading(false);
      setDayReportError("");
      return;
    }
    if (tab !== "day" || object.id === "none") {
      return;
    }
    let cancelled = false;
    setDayReportLoading(true);
    setDayReportError("");
    inspectionApi
      .day(object.id, viewDate)
      .then((report) => {
        if (!cancelled) setDayReport(report);
      })
      .catch((error) => {
        if (cancelled) return;
        setDayReport(null);
        setDayReportError(error.message);
      })
      .finally(() => {
        if (!cancelled) setDayReportLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [
    account?.kind,
    tab,
    object.id,
    viewDate,
    dayReportNonce,
    object.snapshots.length,
    object.inspections.length,
  ]);
  useEffect(() => {
    if (account?.kind !== "user" || tab !== "day" || object.id === "none") {
      setDayMovement(null);
      return;
    }
    let cancelled = false;
    setDayMovement(null);
    comparisonApi
      .movement(object.id, viewDate)
      .then((result) => {
        if (!cancelled) setDayMovement(result);
      })
      .catch(() => {
        if (!cancelled) setDayMovement(null);
      });
    return () => {
      cancelled = true;
    };
  }, [account?.kind, tab, object.id, viewDate, object.snapshots.length]);
  useEffect(() => {
    if (account?.kind !== "user" || route !== "/objects") {
      return;
    }
    let cancelled = false;
    setPortfolioReports({});
    setPortfolioMovements({});
    Promise.all(
      objects
        .filter((item) => !item.draft && !item.archived)
        .map(async (item) => {
          const [report, movement] = await Promise.allSettled([
            inspectionApi.day(item.id, viewDate),
            comparisonApi.movement(item.id, viewDate),
          ]);
          return [
            item.id,
            report.status === "fulfilled"
              ? report.value
              : { error: report.reason.message },
            movement.status === "fulfilled"
              ? movement.value
              : { error: movement.reason.message },
          ];
        }),
    ).then((entries) => {
      if (cancelled) return;
      setPortfolioReports(
        Object.fromEntries(entries.map(([id, report]) => [id, report])),
      );
      setPortfolioMovements(
        Object.fromEntries(entries.map(([id, , movement]) => [id, movement])),
      );
    });
    return () => {
      cancelled = true;
    };
  }, [account?.kind, route, viewDate, objects]);
  const newObject = () => {
    setDraft({
      name: "",
      type: "Жильё",
      address: "",
      timezone: "Europe/Moscow",
      schedule: { ...DEFAULT_SCHEDULE },
      cams: cameraSeed().map((c) => ({ ...c, photo: null })),
      plan: [],
    });
    nav("/new/object");
  };
  const completeObject = async (asDraft = false) => {
    if (!draft.name.trim()) {
      setFormError("Укажите название объекта");
      return;
    }
    if (
      !asDraft &&
      (!draft.cams.length ||
        Object.keys(cameraErrors(draft.cams)).length ||
        !draft.plan.length)
    ) {
      setFormError("Проверьте названия камер и добавьте хотя бы один этап");
      return;
    }
    setSaving(true);
    setFormError("");
    try {
      const created = await objectApi.create({
        name: draft.name,
        object_type: draft.type,
        address: draft.address,
        timezone: draft.timezone || "Europe/Moscow",
        is_draft: asDraft,
        cameras: draft.cams.map(cameraToApi),
        plan_items: draft.plan.map(planToApi),
        schedule: {
          effective_from: dateInZone(draft.timezone || "Europe/Moscow"),
          times: scheduleOf(draft).times,
          confirmation_threshold: scheduleOf(draft).confirm,
          absence_threshold: scheduleOf(draft).absence,
        },
      });
      const o = objectFromApi(created);
      setObjects([...objects, o]);
      nav(`/object/${o.id}/day`);
      notify(asDraft ? "Черновик объекта сохранён" : "Объект создан");
    } catch (error) {
      setFormError(error.message);
    } finally {
      setSaving(false);
    }
  };
  const saveCameras = async () => {
    setSaving(true);
    try {
      const response = await objectApi.syncCameras(
        object.id,
        editingCams.map(cameraToApi),
      );
      updateObject((o) => ({ ...o, cams: response.map(cameraFromApi) }));
      setEditingCams(null);
      notify("Камеры сохранены");
    } catch (error) {
      setFormError(error.message);
    } finally {
      setSaving(false);
    }
  };
  const setCameraActive = async (camera, isActive) => {
    if (isActive && cams.length >= 16) {
      notify("Достигнут лимит 16 активных камер");
      return;
    }
    if (
      isActive &&
      cams.some(
        (item) =>
          item.id !== camera.id &&
          item.name.trim().toLocaleLowerCase("ru") ===
            camera.name.trim().toLocaleLowerCase("ru"),
      )
    ) {
      notify("Сначала переименуйте активную камеру с таким названием");
      return;
    }
    setSaving(true);
    try {
      const response = await objectApi.updateCamera(camera.id, {
        is_active: isActive,
      });
      const updated = cameraFromApi(response);
      updateObject((o) => ({
        ...o,
        cams: o.cams.map((item) => (item.id === updated.id ? updated : item)),
      }));
      notify(isActive ? "Камера восстановлена" : "Камера перемещена в архив");
    } catch (error) {
      notify(error.message);
    } finally {
      setSaving(false);
    }
  };
  const savePlan = async (plan) => {
    const previous = object.plan;
    updateObject((o) => ({ ...o, plan }));
    setSaving(true);
    try {
      const response = await objectApi.syncPlan(object.id, plan.map(planToApi));
      updateObject((o) => ({ ...o, plan: response.map(planFromApi) }));
      notify("План сохранён для следующих проверок");
    } catch (error) {
      updateObject((o) => ({ ...o, plan: previous }));
      notify(error.message);
    } finally {
      setSaving(false);
    }
  };
  const archiveObject = async () => {
    setSaving(true);
    try {
      const response = await objectApi.update(object.id, {
        is_archived: true,
      });
      const archivedObject = objectFromApi(response);
      archivedObject.snapshots = object.snapshots;
      archivedObject.inspections = object.inspections;
      updateObject(() => archivedObject);
    } catch (error) {
      notify(error.message);
      setSaving(false);
      return;
    }
    setSaving(false);
    nav("/objects");
    notify("Объект перемещён в архив");
  };
  const startCheck = (time) => {
    setSnapshotDate(viewDate);
    setSnapshotTime(
      time ||
        schedule.times.find(
          (t) =>
            !object.snapshots.some((s) => s.date === viewDate && s.time === t),
        ) ||
        schedule.times.at(-1),
    );
    setCheckKey((k) => k + 1);
    objnav("snapshot");
  };
  const ensureAnalysisObject = async () => ({
    id: object.id,
    cameras: object.cams,
  });
  const waitForAnalysis = async (snapshotId, onProgress) => {
    const deadline = Date.now() + 110_000;
    while (Date.now() < deadline) {
      const current = await snapshotApi.get(snapshotId);
      if (["completed", "partial", "error"].includes(current.state))
        return current;
      onProgress(current.state);
      await new Promise((resolve) => setTimeout(resolve, 1200));
    }
    throw new Error(
      "Анализ занимает больше обычного. Откройте историю через несколько минут.",
    );
  };
  const finishCheck = async ({ date, time, uploads }, onProgress) => {
    const remote = await ensureAnalysisObject();
    onProgress("uploading");
    let created;
    try {
      created = await snapshotApi.create(remote.id, date, time, "manual");
      const localCameras = active(object.cams);
      await Promise.all(
        localCameras
          .filter((camera) => uploads[camera.id])
          .map((camera, index) => {
            const remoteCamera =
              remote.cameras.find((item) => item.code === camera.code) ||
              remote.cameras.find((item) => item.name === camera.name) ||
              remote.cameras[index];
            if (!remoteCamera)
              throw new Error(`Не найдена камера «${camera.name}»`);
            return snapshotApi.upload(
              created.id,
              remoteCamera.id,
              uploads[camera.id].file,
              "manual",
            );
          }),
      );
    } catch (error) {
      if (created?.id) await snapshotApi.remove(created.id).catch(() => {});
      throw error;
    }
    onProgress("queued");
    await snapshotApi.analyze(created.id, crypto.randomUUID());
    const response = await waitForAnalysis(created.id, onProgress);
    const saved = snapshotFromApi(response, object);
    updateObject((item) => ({
      ...item,
      snapshots: [
        saved,
        ...item.snapshots.filter((row) => row.id !== saved.id),
      ],
    }));
    objnav("result/" + saved.id);
  };
  const retryAnalysis = async (snapshot) => {
    setSaving(true);
    try {
      await snapshotApi.analyze(snapshot.id, crypto.randomUUID());
      const response = await waitForAnalysis(snapshot.id, () => {});
      const saved = snapshotFromApi(response, object);
      updateObject((item) => ({
        ...item,
        snapshots: item.snapshots.map((row) =>
          row.id === saved.id ? saved : row,
        ),
      }));
      notify(
        saved.state === "error"
          ? "Анализ снова завершился ошибкой"
          : "Анализ завершён",
      );
    } catch (error) {
      notify(error.message);
    } finally {
      setSaving(false);
    }
  };
  const snap =
    object.snapshots.find((s) => s.id === route.split("/")[4]) ||
    object.snapshots[0];
  const configuredSchedule = scheduleOf(object);
  const serverDayReady =
    dayReport?.object_id === object.id && dayReport?.date === viewDate;
  // Итог дня считает только сервер; клиент его не пересчитывает и не подменяет.
  const summary = serverDayReady
    ? daySummaryFromApi(dayReport, object)
    : {
        schedule: configuredSchedule,
        stages: [],
        confirmed: 0,
        insufficient: 0,
        deviations: 0,
        excluded: 0,
        received: 0,
        expected: configuredSchedule.times.length,
      };
  const schedule = summary.schedule;
  const todayPlan = summary.stages;
  const movementSignal =
    dayMovement?.object_id === object.id && dayMovement?.date === viewDate
      ? dayMovement.signals?.[0]
      : null;
  const dayChecks = object.snapshots.filter((s) => s.date === viewDate);
  const inspectionStage = inspectionForm
    ? object.plan.find((stage) => stage.id === inspectionForm.stageId)
    : null;
  const inspectionAllowsPeriod = ["Нет", "Частично"].includes(
    inspectionStage?.observable,
  );
  const filteredInspections = (object.inspections || []).filter(
    (inspection) =>
      (inspectionFilters.stageId === "all" ||
        inspection.stageId === inspectionFilters.stageId) &&
      (inspectionFilters.verdict === "all" ||
        inspection.verdict === inspectionFilters.verdict) &&
      (!inspectionFilters.date ||
        (inspection.date <= inspectionFilters.date &&
          inspectionFilters.date <= (inspection.until || inspection.date))),
  );
  const openPassport = (cam) =>
    setPassport({
      ...cam,
      coverage: cam.coverage || [],
      coverageText: (cam.coverage || []).join(", "),
    });
  const savePassport = async () => {
    const { coverageText, ...cam } = passport;
    const coverage = coverageText
      .split(",")
      .map((x) => x.trim())
      .filter(Boolean);
    setSaving(true);
    try {
      const response = await objectApi.updateCamera(cam.id, {
        name: cam.name,
        zone: cam.zone || "",
        view_description: cam.viewDescription || "",
        view_type: cam.viewType || VIEW_TYPES[0][0],
        placement: cam.placement || "",
        orientation: cam.orientation || "",
        coverage,
      });
      const updated = cameraFromApi(response);
      updateObject((o) => ({
        ...o,
        cams: o.cams.map((c) => (c.id === updated.id ? updated : c)),
      }));
      setPassport(null);
      notify("Паспорт камеры сохранён");
    } catch (error) {
      notify(error.message);
    } finally {
      setSaving(false);
    }
  };
  const incrementPassportRevision = async () => {
    setSaving(true);
    try {
      const response = await objectApi.incrementFovRevision(passport.id);
      const updated = cameraFromApi(response);
      setPassport({ ...updated, coverageText: updated.coverage.join(", ") });
      updateObject((o) => ({
        ...o,
        cams: o.cams.map((c) => (c.id === updated.id ? updated : c)),
      }));
      notify(`Сохранён ракурс rev. ${updated.fovRevision}`);
    } catch (error) {
      notify(error.message);
    } finally {
      setSaving(false);
    }
  };
  const setSchedule = (patch) =>
    updateObject((o) => ({ ...o, schedule: { ...scheduleOf(o), ...patch } }));
  const saveObjectSettings = async () => {
    if (!object.name.trim()) {
      notify("Введите название объекта");
      return;
    }
    if (new Set(schedule.times).size !== schedule.times.length) {
      notify("Времена проверок не должны повторяться");
      return;
    }
    setSaving(true);
    try {
      const [savedObject, savedSchedule] = await Promise.all([
        objectApi.update(object.id, {
          name: object.name,
          object_type: object.type,
          address: object.address || "",
          timezone: object.timezone || "Europe/Moscow",
        }),
        objectApi.updateSchedule(object.id, {
          effective_from: dateInZone(object.timezone || "Europe/Moscow"),
          times: schedule.times,
          confirmation_threshold: schedule.confirm,
          absence_threshold: schedule.absence,
        }),
      ]);
      const normalized = objectFromApi(savedObject);
      normalized.schedule = {
        times: savedSchedule.times,
        confirm: savedSchedule.confirmation_threshold,
        absence: savedSchedule.absence_threshold,
        version: savedSchedule.version,
        effectiveFrom: savedSchedule.effective_from,
      };
      normalized.snapshots = object.snapshots;
      normalized.inspections = object.inspections;
      updateObject(() => normalized);
      notify(`Настройки сохранены · расписание v${savedSchedule.version}`);
    } catch (error) {
      notify(error.message);
    } finally {
      setSaving(false);
    }
  };
  const setSlot = (i, value) => {
    const times = [...scheduleOf(object).times];
    times[i] = value;
    setSchedule({ times });
  };
  const addSlot = () => {
    const times = scheduleOf(object).times;
    const last = Number(times.at(-1).slice(0, 2));
    const next = `${String(Math.min(23, last + 2)).padStart(2, "0")}:00`;
    setSchedule({ times: [...times, times.includes(next) ? "23:00" : next] });
  };
  const removeSlot = () =>
    setSchedule({ times: scheduleOf(object).times.slice(0, -1) });
  const matrixCols = {
    gridTemplateColumns: `minmax(230px, 1.7fr) repeat(${schedule.times.length}, minmax(64px, 0.5fr)) minmax(230px, 1.4fr)`,
  };
  const filmDays = (() => {
    const end = new Date(viewDate + "T12:00:00");
    const start = filmFrom
      ? new Date(filmFrom + "T12:00:00")
      : new Date(end.getTime() - 6 * 86400000);
    const out = [];
    for (
      let d = new Date(start);
      d <= end && out.length < 14;
      d.setDate(d.getDate() + 1)
    )
      out.push(d.toISOString().slice(0, 10));
    return out.length ? out : [viewDate];
  })();
  const periodCols = {
    gridTemplateColumns: `minmax(170px, 1fr) repeat(${filmDays.length}, minmax(74px, 1fr))`,
  };
  const shotsFor = (cam, day) =>
    object.snapshots
      .filter((s) => s.date === day)
      .sort((a, b) => a.time.localeCompare(b.time))
      .map((s) => {
        const shot = s.cams.find((x) => x.id === cam.id && x.photo);
        return shot
          ? {
              key: `${s.id}-${cam.id}`,
              snapId: s.id,
              time: s.time,
              date: s.date,
              photo: shot.photo,
              imageId: shot.imageId,
              objectId: s.remoteObjectId || object.id,
              source: shot.source || s.source || "camera",
              fovRevision: shot.fovRevision || cam.fovRevision || 1,
            }
          : null;
      })
      .filter(Boolean);
  const pickShot = (cam, x) => {
    if (!filmCompare) {
      setPhoto({
        cams: [{ ...cam, photo: x.photo }],
        time: x.time,
        date: x.date,
        snapId: x.snapId,
      });
      return;
    }
    const item = {
      ...x,
      camId: cam.id,
      camName: cam.name,
      camCode: cam.code,
      fovRevision: x.fovRevision,
    };
    if (filmCompare.some((f) => f.key === x.key))
      setFilmCompare(filmCompare.filter((f) => f.key !== x.key));
    else if (filmCompare.length && filmCompare[0].camId !== cam.id)
      notify("Сравниваются снимки одной камеры");
    else if (
      filmCompare.length &&
      filmCompare[0].fovRevision !== item.fovRevision
    )
      notify("Между снимками менялся ракурс: ревизии FOV не совпадают");
    else setFilmCompare([...filmCompare, item].slice(-2));
    setComparisonResult(null);
  };
  const analyzeFilmComparison = async () => {
    if (filmCompare?.length !== 2) return;
    if (!filmCompare.every((item) => item.imageId && item.objectId)) {
      notify("Для анализа выберите два снимка из выполненных проверок");
      return;
    }
    setComparisonLoading(true);
    setComparisonResult(null);
    try {
      const result = await comparisonApi.create(
        filmCompare[0].objectId,
        filmCompare[0].imageId,
        filmCompare[1].imageId,
      );
      setComparisonResult(result);
    } catch (error) {
      setComparisonResult({
        state: "error",
        error_detail: error.message,
      });
    } finally {
      setComparisonLoading(false);
    }
  };
  const filmCols = {
    gridTemplateColumns: `minmax(230px, 1.7fr) repeat(${schedule.times.length}, minmax(64px, 1fr))`,
  };
  const shiftDay = (delta) => {
    const d = new Date(viewDate + "T12:00:00");
    d.setDate(d.getDate() + delta);
    setViewDate(d.toISOString().slice(0, 10));
    setDayCell(null);
  };
  const hasData = object.snapshots.length > 0;
  const dayCounts = [
    ["success", summary.confirmed, "подтверждается", "подтверждаются"],
    [
      "warning",
      summary.deviations,
      "возможное отклонение",
      "возможных отклонения",
    ],
    [
      "neutral",
      summary.insufficient,
      "недостаточно данных",
      "недостаточно данных",
    ],
    [
      "muted",
      summary.excluded,
      "вне визуального контроля",
      "вне визуального контроля",
    ],
  ].filter(([, n]) => n > 0);
  const dayStatus =
    account?.kind === "user" && dayReportLoading ? (
      <span className="day-empty">Загружаем оценку дня…</span>
    ) : account?.kind === "user" && dayReportError ? (
      <span className="day-empty">Оценка дня недоступна</span>
    ) : !todayPlan.length ? (
      <span className="day-empty">Нет работ по плану на эту дату</span>
    ) : (
      <div className="day-counts">
        {dayCounts.map(([tone, n, one, many]) => (
          <span className={`day-count ${tone}`} key={tone}>
            <i />
            <strong>{n}</strong>
            {n === 1 ? one : many}
          </span>
        ))}
      </div>
    );
  const modelBlock = (snapshot, title = "Ответ модели") =>
    devMode && snapshot ? (
      <details className="dev-answer">
        <summary>
          <IconCode size={17} />
          {title}
          <span className="dev-tag">
            {!snapshot.analysisAttempt
              ? "ответа модели нет"
              : snapshot.analysisAttempt.error_code
                ? "ошибка ответа"
                : "проверен по схеме"}
          </span>
        </summary>
        {snapshot.analysisAttempt ? (
          <pre>
            {JSON.stringify(
              {
                provider: snapshot.analysisAttempt.provider,
                model: snapshot.analysisAttempt.model,
                prompt_version: snapshot.analysisAttempt.prompt_version,
                request_id: snapshot.analysisAttempt.request_id,
                duration_ms: snapshot.analysisAttempt.duration_ms,
                input_tokens: snapshot.analysisAttempt.input_tokens,
                output_tokens: snapshot.analysisAttempt.output_tokens,
                error_code: snapshot.analysisAttempt.error_code,
                error_detail: snapshot.analysisAttempt.error_detail,
                attempts: (snapshot.attempts || []).map((item) => ({
                  attempt: item.attempt_number,
                  model: item.model,
                  state: item.state,
                  error_code: item.error_code,
                })),
                normalized_response:
                  snapshot.analysisAttempt.normalized_response,
                raw_response: snapshot.analysisAttempt.raw_response,
              },
              null,
              2,
            )}
          </pre>
        ) : (
          <p className="helper">
            Для этой проверки модель ещё не вызывалась: анализ не запускался или
            ещё выполняется.
          </p>
        )}
      </details>
    ) : null;
  const cellMeta = {
    positive: { icon: IconCheck, title: "Признак найден" },
    none: { icon: IconMinus, title: "Проверка есть, признака нет" },
    missing: { icon: IconClock, title: "Проверки не было" },
    uncovered: { icon: IconEyeOff, title: "Камеры не покрывают этап" },
  };
  const needsManual = (p) =>
    p.evidence.source !== "inspection" &&
    (confirmBy(p) === "inspection" ||
      p.evidence.type === "neutral" ||
      p.evidence.type === "warning");
  const methodTag = (stage, source) => {
    const inspectionSource = source === "inspection";
    const inspectionMethod =
      inspectionSource ||
      source === "inspection-pending" ||
      confirmBy(stage) === "inspection";
    return (
      <span className="source-tag">
        {inspectionMethod ? (
          <IconClipboardCheck size={14} />
        ) : (
          <IconCamera size={14} />
        )}
        {inspectionSource
          ? "Инженер"
          : inspectionMethod
            ? "Осмотром"
            : "По камерам"}
      </span>
    );
  };
  const openInspection = (stage, date = viewDate) =>
    setInspectionForm({
      stageId: stage.id,
      date,
      until: "",
      verdict: "confirmed",
      author: "Алексей Петров",
      role: "Эксперт визуального контроля",
      comment: "",
      files: [],
      error: "",
    });
  const closeInspection = () => {
    inspectionForm?.files?.forEach((item) => URL.revokeObjectURL(item.preview));
    setInspectionForm(null);
  };
  const addInspectionFiles = (selectedFiles) => {
    const allowed = new Set(["image/jpeg", "image/png", "application/pdf"]);
    const candidates = [...selectedFiles];
    const invalid = candidates.find(
      (file) => !allowed.has(file.type) || file.size > 20 * 1024 * 1024,
    );
    if (invalid) {
      setInspectionForm((current) => ({
        ...current,
        error: allowed.has(invalid.type)
          ? `Файл «${invalid.name}» больше 20 МБ`
          : `Файл «${invalid.name}» не поддерживается`,
      }));
      return;
    }
    setInspectionForm((current) => {
      const room = 3 - current.files.length;
      if (candidates.length > room) {
        return {
          ...current,
          error: "К осмотру можно приложить не более трёх файлов",
        };
      }
      return {
        ...current,
        error: "",
        files: [
          ...current.files,
          ...candidates.map((file) => ({
            file,
            preview: URL.createObjectURL(file),
          })),
        ],
      };
    });
  };
  const saveInspection = async (event) => {
    event.preventDefault();
    const author = inspectionForm.author.trim();
    const comment = inspectionForm.comment.trim();
    if (!author || !comment) {
      setInspectionForm({
        ...inspectionForm,
        error: "Укажите автора и опишите результат осмотра",
      });
      return;
    }
    if (!inspectionStage) {
      setInspectionForm({ ...inspectionForm, error: "Выберите этап плана" });
      return;
    }
    if (
      inspectionForm.date < inspectionStage.start ||
      inspectionForm.date > inspectionStage.end
    ) {
      setInspectionForm({
        ...inspectionForm,
        error: "Дата осмотра должна входить в период выбранного этапа",
      });
      return;
    }
    if (inspectionForm.until && !inspectionAllowsPeriod) {
      setInspectionForm({
        ...inspectionForm,
        error:
          "Период действия доступен для невидимых или частично видимых работ",
      });
      return;
    }
    setSaving(true);
    try {
      const remoteObject = await ensureAnalysisObject();
      const remoteStageId = inspectionForm.stageId;
      const response = await inspectionApi.create(
        remoteObject.id,
        {
          planItemId: remoteStageId,
          observedDate: inspectionForm.date,
          validUntil: inspectionForm.until,
          verdict: inspectionForm.verdict,
          author,
          role: inspectionForm.role.trim(),
          comment,
        },
        inspectionForm.files.map((item) => item.file),
      );
      const record = inspectionFromApi(response, inspectionForm.stageId);
      updateObject((item) => ({
        ...item,
        inspections: [
          record,
          ...(item.inspections || []).map((inspection) =>
            inspection.stageId === record.stageId
              ? { ...inspection, superseded: true }
              : inspection,
          ),
        ],
      }));
      closeInspection();
      notify("Осмотр сохранён и учтён в оценке дня");
    } catch (error) {
      setInspectionForm((current) => ({
        ...current,
        error: error.message,
      }));
    } finally {
      setSaving(false);
    }
  };
  const FACT_LABEL = {
    excavator: "Экскаваторы",
    pit: "Открытый котлован",
    earthworks: "Земляные работы · высокая уверенность",
    crane: "Монтажные элементы башенного крана",
  };
  const factLabels = (p) => {
    const facts = factsFor(p);
    const keys = facts.includes("earthworks")
      ? ["excavator", "pit", "earthworks"]
      : [];
    if (facts.includes("crane")) keys.push("crane");
    return keys.map((k) => [k, FACT_LABEL[k]]);
  };
  const inspectionCard = (i, stage) => (
    <div className={`inspection-card ${INSPECTION_RESULTS[i.verdict].type}`}>
      <div className="inspection-card-head">
        <Badge type={INSPECTION_RESULTS[i.verdict].type}>
          {INSPECTION_RESULTS[i.verdict].label}
        </Badge>
        <span className="source-tag">
          <IconUser size={14} />
          {i.author}
          {i.role ? ` · ${i.role}` : ""}
        </span>
      </div>
      {stage && <strong className="inspection-stage">{stage.name}</strong>}
      <p>{i.comment}</p>
      <div className="inspection-meta">
        <span>
          <IconCalendar size={15} />
          {i.until && i.until !== i.date
            ? `${shortDate(i.date)} — ${shortDate(i.until)}`
            : dateLabel(i.date)}
        </span>
        {!!i.photos?.length && (
          <button
            className="text-button small"
            onClick={() =>
              setPhoto({
                cams: i.photos.map((photo, n) => ({
                  id: `${i.id}-${n}`,
                  name: "Материал осмотра",
                  photo,
                })),
                time: shortDate(i.date),
              })
            }
          >
            <IconPhoto size={15} />
            {i.photos.length}{" "}
            {plural(i.photos.length, "материал", "материала", "материалов")}
          </button>
        )}
        {(i.attachments || [])
          .filter((attachment) => attachment.content_type === "application/pdf")
          .map((attachment) => (
            <a
              className="text-button small"
              href={attachment.url}
              target="_blank"
              rel="noreferrer"
              key={attachment.id}
            >
              <IconFileDescription size={15} />
              {attachment.original_name}
            </a>
          ))}
      </div>
    </div>
  );
  const evidenceDetail = (p, e) => (
    <div className={`stage-evidence ${e.cells ? "" : "single-check-evidence"}`}>
      <div>
        <span className="eyebrow">
          {e.cells && e.type === "warning" && e.source === "cameras"
            ? "ОСНОВАНИЯ ВОЗМОЖНОГО ОТКЛОНЕНИЯ"
            : "НАЙДЕННЫЕ СВИДЕТЕЛЬСТВА"}
        </span>
        {p.observable === "Нет" && !e.inspection ? (
          <p>
            Работы внутри корпуса не видны с внешних камер. Подтвердить этап
            может только осмотр инженера.
          </p>
        ) : (
          <>
            {e.explanation && (
              <p className="evidence-explanation">{e.explanation}</p>
            )}
            {e.cells && e.type === "warning" && e.source === "cameras" && (
              <ul className="absence-facts">
                {e.cells
                  .filter((cell) => cell.state === "none" && cell.explanation)
                  .map((cell) => (
                    <li key={cell.time}>
                      <strong>{cell.time}</strong>
                      <span>{cell.explanation}</span>
                      {cell.check && (
                        <button
                          className="text-button small"
                          onClick={() => objnav("result/" + cell.check.id)}
                        >
                          Открыть проверку и снимки
                          <IconArrowUpRight size={14} />
                        </button>
                      )}
                    </li>
                  ))}
              </ul>
            )}
            {e.sources.length && e.explanation ? (
              <ul className="evidence-facts">
                {e.sources.map((source) => (
                  <li key={source.evidenceId || `${source.id}-${source.time}`}>
                    <IconCheck size={17} />
                    <div>
                      <strong>
                        {source.evidenceDescription || "Визуальный признак"}
                      </strong>
                      <div className="evidence-cameras">
                        <button
                          className="text-button small"
                          onClick={() =>
                            setPhoto({ cams: [source], time: source.time })
                          }
                        >
                          <IconCamera size={14} />
                          {source.name} · {source.time}
                          {typeof source.confidence === "number"
                            ? ` · ${Math.round(source.confidence * 100)}%`
                            : ""}
                        </button>
                      </div>
                    </div>
                  </li>
                ))}
              </ul>
            ) : e.sources.length ? (
              <ul className="evidence-facts">
                {factLabels(p).map(([fact, label]) => {
                  const sources = e.sources.filter((c) =>
                    c.facts?.includes(fact),
                  );
                  return sources.length ? (
                    <li key={fact}>
                      <IconCheck size={17} />
                      <div>
                        <strong>{label}</strong>
                        <div className="evidence-cameras">
                          {sources.map((c) => (
                            <button
                              className="text-button small"
                              key={`${c.id}-${c.time}`}
                              onClick={() =>
                                setPhoto({ cams: [c], time: c.time })
                              }
                            >
                              <IconCamera size={14} />
                              {c.name} · {c.time}
                            </button>
                          ))}
                        </div>
                      </div>
                    </li>
                  ) : null;
                })}
              </ul>
            ) : !e.explanation ? (
              <p>
                Пока нет обработанных снимков со свидетельствами этого этапа.
              </p>
            ) : null}
            {!!e.limitations?.length && (
              <p className="helper">Ограничения: {e.limitations.join("; ")}</p>
            )}
            <p className="evidence-method">
              {e.cells ? (
                e.source === "inspection" ? (
                  <>
                    Итог за день подтверждён осмотром инженера. По камерам
                    найдено независимых наблюдений: {e.positives}.
                  </>
                ) : e.type === "warning" ? (
                  <>
                    Основание: в {e.usable} {plural(e.usable, "пригодной проверке", "пригодных проверках", "пригодных проверках")} не найдены видимые
                    признаки этапа. Вывод требует проверки инженером.
                  </>
                ) : (
                  <>
                    Наблюдений со свидетельствами: {e.positives}. Для
                    подтверждения нужно минимум {e.required}.{" "}
                    {e.type !== "success"
                      ? "Ожидаем следующие проверки."
                      : "Признаки повторяются в независимых проверках."}
                  </>
                )
              ) : e.explanation ? (
                `Уверенность анализа: ${Math.round((e.confidence || 0) * 100)}%. Дневная оценка учитывает повторные наблюдения.`
              ) : e.sources.length ? (
                "Свидетельства найдены в этой проверке. Для дневной оценки учитываются повторные наблюдения."
              ) : (
                "В этой проверке недостаточно свидетельств для оценки этапа."
              )}
            </p>
            {e.inspection && (
              <>
                <span className="eyebrow">ОСМОТР ИНЖЕНЕРА</span>
                {inspectionCard(e.inspection)}
              </>
            )}
            {e.cells && !!p.children?.length && (
              <div className="substages">
                <span className="eyebrow">ПОДЭТАПЫ</span>
                {p.children.map((ch) => (
                  <div className="substage" key={ch.id}>
                    <span className="substage-name">
                      <strong>{ch.name}</strong>
                      <small>
                        {shortDate(ch.start)} — {shortDate(ch.end)}
                      </small>
                    </span>
                    {methodTag(ch)}
                    <Badge type="neutral">В составе группы</Badge>
                  </div>
                ))}
                <small>
                  Дневной итог рассчитывается для всей группы. Подэтапы здесь
                  помогают проверить её состав.
                </small>
              </div>
            )}
          </>
        )}
      </div>
      {e.cells && (
        <div className="stage-checks">
          <span className="eyebrow">ИНТЕРВАЛЫ ДНЯ</span>
          <div>
            {e.cells.map((cell) => (
              <button
                key={cell.time}
                className={cell.state === "positive" ? "has-evidence" : ""}
                disabled={!cell.check}
                onClick={() => objnav("result/" + cell.check.id)}
                aria-label={`${cell.time}: ${cellMeta[cell.state].title}`}
              >
                <span>{cell.time}</span>
                {cell.state === "positive" ? (
                  <IconCheck size={16} />
                ) : (
                  <span>—</span>
                )}
              </button>
            ))}
          </div>
          <small>
            Проверьте выводы по исходным снимкам перед принятием решения.
          </small>
        </div>
      )}
    </div>
  );
  const latestCamera = (c) => {
    const s = [...object.snapshots]
      .sort((a, b) =>
        `${b.date} ${b.time}`.localeCompare(`${a.date} ${a.time}`),
      )
      .find((s) => s.cams.some((x) => x.id === c.id && x.photo));
    const match = s?.cams.find((x) => x.id === c.id);
    return {
      ...c,
      photo: match?.photo || c.photo,
      lastTime: s?.time,
      lastDate: s?.date,
    };
  };

  const photoTile = (
    c,
    contextTime = "12:00",
    actions = true,
    contextDate = viewDate,
  ) => (
    <article className="photo-tile" key={c.id}>
      {c.photo ? (
        <button
          className="photo-open"
          aria-label={`Открыть фото ${c.name}`}
          onClick={() => setPhoto({ cams: [c], time: contextTime })}
        >
          <img src={c.photo} alt={`Строительная площадка — ${c.name}`} />
          <span>
            <IconMaximize size={19} />
          </span>
        </button>
      ) : (
        <div className="photo-missing">
          <IconCamera size={39} stroke={1.4} />
          <span>Нет снимка</span>
        </div>
      )}
      <div className="photo-caption">
        <strong>{c.name}</strong>
        <small>{c.zone || "Зона не указана"}</small>
        <span className="photo-time">
          <IconClock size={15} />
          {c.photo
            ? `Снимок в ${contextTime} · ${shortDate(contextDate)}`
            : "Фото ещё не загружено"}
        </span>
      </div>
      {actions && (
        <button className="text-button" onClick={() => startCheck()}>
          {c.photo ? "Загрузить новый снимок" : "Загрузить снимок"}
          <IconArrowRight size={17} />
        </button>
      )}
    </article>
  );

  if (!authReady) {
    return (
      <main className="app-loading" aria-live="polite">
        <IconBuildingSkyscraper size={46} stroke={1.5} />
        <strong>СтройКонтроль</strong>
        <span>Проверяем сессию…</span>
      </main>
    );
  }

  const logout = async () => {
    try {
      await authApi.logout();
    } finally {
      setObjects([]);
      setAccount(null);
      setAuthMode("login");
      setProfile(false);
      nav("/login");
    }
  };
  const header = (
    <header className="topbar">
      {route !== "/login" && !wizard && (
        <button
          className="navigation-toggle"
          aria-label={
            navigationOpen ? "Закрыть навигацию" : "Открыть навигацию"
          }
          aria-expanded={navigationOpen}
          aria-controls="workspace-navigation"
          onClick={() => setNavigationOpen(!navigationOpen)}
        >
          {navigationOpen ? <IconX size={22} /> : <IconMenu2 size={22} />}
        </button>
      )}
      <a className="brand" href={account ? "#/objects" : "#/login"}>
        <IconBuildingSkyscraper size={43} stroke={1.6} />
        <strong>СтройКонтроль</strong>
      </a>
      {(route === "/login" || account?.demo) && (
        <span className="demo-tag">Демо</span>
      )}
      {account && (
        <div className="topbar-right">
          <button
            className="avatar"
            aria-label="Меню профиля"
            onClick={() => setProfile(!profile)}
          >
            АП
          </button>
          {profile && (
            <div className="profile-menu">
              <strong>
                {account?.demo ? "Алексей Петров" : account?.email}
              </strong>
              <small>
                {account?.demo
                  ? "Демонстрационный доступ"
                  : "Личное рабочее пространство"}
              </small>
              <label className="dev-toggle">
                <input
                  type="checkbox"
                  checked={devMode}
                  onChange={(e) => setDevMode(e.target.checked)}
                />
                <span>
                  Режим разработчика
                  <small>Ответ модели у проверки и у ячейки интервала</small>
                </span>
              </label>
              <button
                onClick={() => {
                  setHelp(true);
                  setProfile(false);
                }}
              >
                <IconInfoCircle size={18} />О сервисе
              </button>
              <button onClick={logout}>
                <IconLogout size={18} />
                Выйти
              </button>
            </div>
          )}
        </div>
      )}
    </header>
  );
  const signIn = async (e) => {
    e.preventDefault();
    setAuthSubmitting(true);
    try {
      const { user } = await authApi.login(login.name.trim(), login.password);
      const storedObjects = (await objectApi.listDetails()).map(objectFromApi);
      setObjects(storedObjects);
      setAccount({ kind: "user", demo: user.is_demo, email: user.email });
      setLogin({ name: "", password: "", error: "" });
      nav(startRoute(storedObjects));
    } catch (error) {
      setLogin({ ...login, error: error.message });
    } finally {
      setAuthSubmitting(false);
    }
  };
  const signUp = async (e) => {
    e.preventDefault();
    const email = signup.email.trim();
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) {
      setSignup({ ...signup, error: "Укажите корректный адрес почты" });
      return;
    }
    if (signup.password.length < 8) {
      setSignup({ ...signup, error: "Пароль от 8 символов" });
      return;
    }
    setAuthSubmitting(true);
    try {
      const { user } = await authApi.register(email, signup.password);
      setObjects([]);
      setAccount({ kind: "user", email: user.email });
      setSignup({ email: "", password: "", error: "" });
      nav("/objects");
      notify(`Аккаунт ${email} создан`);
    } catch (error) {
      setSignup({ ...signup, error: error.message });
    } finally {
      setAuthSubmitting(false);
    }
  };
  if (route === "/login")
    return (
      <>
        {header}
        <div className="login-layout">
          <div className="login-photo">
            <img src={NORTH} alt="Строительство жилого комплекса" />
            <div>
              <h1>Стройка в поле зрения</h1>
              <p>
                План работ, снимки камер и визуальные свидетельства — на одном
                экране. Каждый вывод открывается до исходной фотографии.
              </p>
              <ul className="login-points">
                {[
                  "Подневная оценка этапов по контрольным интервалам",
                  "Объяснимые свидетельства вместо процента готовности",
                  "Паспорта камер фиксируют ракурс и зоны наблюдения",
                ].map((x) => (
                  <li key={x}>
                    <IconCircleCheck size={18} />
                    {x}
                  </li>
                ))}
              </ul>
            </div>
          </div>
          <div className="login-form">
            <span className="eyebrow">ВИЗУАЛЬНЫЙ КОНТРОЛЬ СТРОИТЕЛЬСТВА</span>
            <div className="view-switch auth-switch">
              {[
                ["login", "Вход"],
                ["signup", "Регистрация"],
              ].map(([key, title]) => (
                <button
                  key={key}
                  className={authMode === key ? "selected" : ""}
                  aria-pressed={authMode === key}
                  onClick={() => setAuthMode(key)}
                >
                  {title}
                </button>
              ))}
            </div>
            {authMode === "login" ? (
              <form className="auth-form" onSubmit={signIn}>
                <h1>С возвращением</h1>
                <p>Войдите, чтобы открыть строительные объекты.</p>
                <Field label="Логин или адрес почты">
                  <input
                    autoComplete="username"
                    value={login.name}
                    onChange={(e) =>
                      setLogin({ ...login, name: e.target.value, error: "" })
                    }
                  />
                </Field>
                <Field label="Пароль" error={login.error}>
                  <input
                    type="password"
                    autoComplete="current-password"
                    value={login.password}
                    onChange={(e) =>
                      setLogin({
                        ...login,
                        password: e.target.value,
                        error: "",
                      })
                    }
                  />
                </Field>
                <Button kind="primary" type="submit" disabled={authSubmitting}>
                  {authSubmitting ? "Входим…" : "Войти"}
                  <IconArrowRight size={19} />
                </Button>
                <div className="inline-note">
                  <IconInfoCircle size={19} />
                  <span>
                    Заполненный пример: <b>demo / demo</b> — два объекта и
                    черновик для знакомства с сервисом.
                  </span>
                </div>
              </form>
            ) : (
              <form className="auth-form" onSubmit={signUp}>
                <h1>Создать аккаунт</h1>
                <p>
                  Доступ открывается сразу: переходить по ссылке из письма не
                  нужно.
                </p>
                <Field label="Адрес почты">
                  <input
                    type="email"
                    autoComplete="email"
                    placeholder="you@company.ru"
                    value={signup.email}
                    onChange={(e) =>
                      setSignup({
                        ...signup,
                        email: e.target.value,
                        error: "",
                      })
                    }
                  />
                </Field>
                <Field label="Пароль" help="От 8 символов" error={signup.error}>
                  <input
                    type="password"
                    autoComplete="new-password"
                    value={signup.password}
                    onChange={(e) =>
                      setSignup({
                        ...signup,
                        password: e.target.value,
                        error: "",
                      })
                    }
                  />
                </Field>
                <Button kind="primary" type="submit" disabled={authSubmitting}>
                  {authSubmitting ? "Создаём аккаунт…" : "Зарегистрироваться"}
                  <IconArrowRight size={19} />
                </Button>
                <div className="inline-note">
                  <IconInfoCircle size={19} />
                  <span>
                    Рабочее пространство создаётся пустым: объекты другого
                    пользователя в нём не видны.
                  </span>
                </div>
              </form>
            )}
          </div>
        </div>
      </>
    );

  return (
    <>
      {header}
      {wizard ? (
        <aside className="wizard-sidebar">
          <button className="wizard-back" onClick={() => nav("/objects")}>
            <IconArrowLeft size={18} /> Мои объекты
          </button>
          <h2>Новый объект</h2>
          <div className="steps">
            {["Объект", "Камеры", "План работ", "Проверка"].map((s, i) => (
              <button
                className={`step ${i === step ? "current" : ""} ${i < step ? "done" : ""}`}
                key={s}
                onClick={() => {
                  if (i <= step)
                    nav("/new/" + ["object", "cameras", "plan", "review"][i]);
                }}
                aria-current={i === step ? "step" : undefined}
              >
                <span className="step-circle">
                  {i < step ? <IconCheck size={20} /> : i + 1}
                </span>
                <span>
                  <strong>{s}</strong>
                  <small>
                    {i < step
                      ? "Заполнено"
                      : [
                          "Основная информация",
                          "Настройте камеры",
                          "Укажите этапы",
                          "Проверьте данные",
                        ][i]}
                  </small>
                </span>
              </button>
            ))}
          </div>
          <div className="wizard-object">
            <strong>{draft.name || "Новый объект"}</strong>
            <span>{draft.type}</span>
          </div>
        </aside>
      ) : (
        <>
          {navigationOpen && (
            <button
              className="navigation-backdrop"
              aria-label="Закрыть боковую панель"
              onClick={() => setNavigationOpen(false)}
            />
          )}
          <aside
            id="workspace-navigation"
            className={`sidebar ${navigationOpen ? "is-open" : ""}`}
          >
            <div className="object-switch">
              <button
                className="object-switch-trigger"
                aria-haspopup="listbox"
                aria-expanded={switcherOpen}
                onClick={() => setSwitcherOpen(!switcherOpen)}
              >
                <span className="object-switch-icon">
                  {route === "/objects" ? (
                    <IconLayoutGrid size={19} />
                  ) : (
                    <IconBuildings size={19} />
                  )}
                </span>
                <span className="object-switch-text">
                  <strong>
                    {route === "/objects" ? "Все объекты" : object.name}
                  </strong>
                  <small>
                    {route === "/objects"
                      ? `${objects.length} ${plural(objects.length, "объект", "объекта", "объектов")} · сводка`
                      : object.type}
                  </small>
                </span>
                <IconSelector size={17} />
              </button>
              {switcherOpen && (
                <>
                  <button
                    className="switch-backdrop"
                    aria-label="Закрыть список объектов"
                    onClick={() => setSwitcherOpen(false)}
                  />
                  <div className="object-switch-menu" role="listbox">
                    <button
                      role="option"
                      aria-selected={route === "/objects"}
                      className={`switch-option summary ${route === "/objects" ? "selected" : ""}`}
                      onClick={() => nav("/objects")}
                    >
                      <IconLayoutGrid size={18} />
                      <span className="switch-option-text">
                        <strong>Все объекты</strong>
                        <small>Сводка, отклонения, техника</small>
                      </span>
                      {route === "/objects" && <IconCheck size={16} />}
                    </button>
                    <div className="switch-group">ОБЪЕКТЫ</div>
                    {objects.map((item) => {
                      const st = statusFor(
                        item,
                        viewDate,
                        portfolioReports[item.id],
                        account?.kind === "user",
                      );
                      const current =
                        route !== "/objects" && item.id === object.id;
                      return (
                        <button
                          key={item.id}
                          role="option"
                          aria-selected={current}
                          className={`switch-option ${current ? "selected" : ""}`}
                          onClick={() => nav(`/object/${item.id}/day`)}
                        >
                          <span
                            className={`switch-dot ${st.tone}`}
                            title={st.label}
                          />
                          <span className="switch-option-text">
                            <strong>{item.name}</strong>
                            <small>{st.label}</small>
                          </span>
                          {current && <IconCheck size={16} />}
                        </button>
                      );
                    })}
                    <button className="switch-add" onClick={newObject}>
                      <IconPlus size={17} />
                      Добавить объект
                    </button>
                  </div>
                </>
              )}
            </div>
            {route === "/objects" && (
              <nav className="sidebar-objects" aria-label="Объекты">
                <div className="sidebar-group">ОБЪЕКТЫ</div>
                {objects.map((item) => {
                  const st = statusFor(
                    item,
                    viewDate,
                    portfolioReports[item.id],
                    account?.kind === "user",
                  );
                  return (
                    <button
                      key={item.id}
                      className="nav-item object-link"
                      onClick={() => nav(`/object/${item.id}/day`)}
                    >
                      <span className={`switch-dot ${st.tone}`} />
                      <span className="switch-option-text">
                        <strong>{item.name}</strong>
                        <small>{st.label}</small>
                      </span>
                    </button>
                  );
                })}
              </nav>
            )}
            {route !== "/objects" && (
              <nav aria-label="Разделы объекта">
                {[
                  ["day", IconLayoutDashboard, "Контроль дня"],
                  ["plan", IconCalendar, "План работ"],
                  ["history", IconHistory, "История"],
                  ["inspections", IconClipboardCheck, "Осмотры"],
                  ["settings", IconSettings, "Настройки объекта"],
                ].map(([key, Icon, title]) => (
                  <button
                    className={`nav-item ${navigationTab === key ? "selected" : ""}`}
                    aria-current={navigationTab === key ? "page" : undefined}
                    key={key}
                    onClick={() => objnav(key)}
                  >
                    <Icon size={21} />
                    {title}
                    {key === "inspections" && !!object.inspections?.length && (
                      <span className="nav-count">
                        {object.inspections.length}
                      </span>
                    )}
                  </button>
                ))}
              </nav>
            )}
            <div className="sidebar-bottom">
              <button className="nav-item" onClick={() => setHelp(true)}>
                <IconInfoCircle size={21} />О сервисе
              </button>
              <span>Визуальный контроль строительства</span>
            </div>
          </aside>
        </>
      )}
      <main
        className={
          wizard
            ? "wizard-main"
            : `main ${tab === "snapshot" ? "check-page" : ""}`
        }
      >
        {wizard ? (
          <>
            <div className="wizard-body">
              {step === 1 ? (
                <>
                  <div className="camera-wizard-heading">
                    <div>
                      <h1>Настройка камер</h1>
                      <p>Укажите количество и названия точек наблюдения.</p>
                    </div>
                    <figure>
                      <img src={NORTH} alt="Пример строительной площадки" />
                      <figcaption>Пример зоны обзора</figcaption>
                    </figure>
                  </div>
                  <CameraForm
                    cams={draft.cams}
                    onValidityChange={setCameraValid}
                    onChange={(cams) => setDraft({ ...draft, cams })}
                  />
                </>
              ) : step === 0 ? (
                <>
                  <div className="page-heading">
                    <h1>Новый строительный объект</h1>
                    <p>Начните с основной информации о площадке.</p>
                  </div>
                  <div className="form-stack narrow">
                    <Field label="Название объекта" error={formError}>
                      <input
                        placeholder="Например, ЖК Северный парк"
                        value={draft.name}
                        onChange={(e) => {
                          setDraft({ ...draft, name: e.target.value });
                          setFormError("");
                        }}
                      />
                    </Field>
                    <Field
                      label="Тип объекта"
                      help="Определяет доступные этапы плана"
                    >
                      <select
                        value={draft.type}
                        onChange={(e) =>
                          setDraft({ ...draft, type: e.target.value })
                        }
                      >
                        {objectTypeOptions(draft.type)}
                      </select>
                    </Field>
                    <Field label="Адрес или описание">
                      <textarea
                        rows={3}
                        placeholder="Где находится объект"
                        value={draft.address}
                        onChange={(e) =>
                          setDraft({ ...draft, address: e.target.value })
                        }
                      />
                    </Field>
                    <Field
                      label="Часовой пояс"
                      help="По нему определяются дата и контрольные интервалы"
                    >
                      <select
                        value={draft.timezone || "Europe/Moscow"}
                        onChange={(e) =>
                          setDraft({ ...draft, timezone: e.target.value })
                        }
                      >
                        <option value="Europe/Moscow">Москва, UTC+3</option>
                        <option value="Asia/Yekaterinburg">
                          Екатеринбург, UTC+5
                        </option>
                        <option value="Asia/Novosibirsk">
                          Новосибирск, UTC+7
                        </option>
                      </select>
                    </Field>
                    <div className="inline-note">
                      <IconInfoCircle size={20} />
                      <span>Далее вы добавите камеры и календарный план.</span>
                    </div>
                  </div>
                </>
              ) : step === 2 ? (
                <>
                  <div className="page-heading">
                    <h1>План работ</h1>
                    <p>
                      Укажите этапы, которые нужно сопоставлять со снимками.
                    </p>
                  </div>
                  <PlanEditor
                    plan={draft.plan}
                    onChange={(plan) => setDraft({ ...draft, plan })}
                    cams={draft.cams}
                    objectType={draft.type}
                    directoryItems={stageDirectory}
                    compact
                  />
                </>
              ) : (
                <>
                  <div className="page-heading">
                    <h1>Всё готово к началу</h1>
                    <p>Проверьте настройки перед созданием объекта.</p>
                  </div>
                  <div className="review-summary">
                    <IconBuildingSkyscraper size={38} />
                    <div>
                      <h2>{draft.name}</h2>
                      <p>
                        {draft.type} · {draft.address || "Адрес не указан"}
                      </p>
                    </div>
                  </div>
                  <div className="review-columns">
                    <section>
                      <h2>{draft.cams.length} камеры</h2>
                      {draft.cams.map((c) => (
                        <div className="review-row" key={c.id}>
                          <IconCamera size={20} />
                          <div>
                            <b>{c.name}</b>
                            <small>{c.zone || "Зона не указана"}</small>
                          </div>
                        </div>
                      ))}
                      <button
                        className="text-button"
                        onClick={() => nav("/new/cameras")}
                      >
                        Изменить камеры
                      </button>
                    </section>
                    <section>
                      <h2>{draft.plan.length} этапа в плане</h2>
                      {draft.plan.map((p) => (
                        <div className="review-row" key={p.id}>
                          <IconCalendar size={20} />
                          <div>
                            <b>{p.name}</b>
                            <small>
                              {shortDate(p.start)} — {shortDate(p.end)}
                            </small>
                          </div>
                        </div>
                      ))}
                      <button
                        className="text-button"
                        onClick={() => nav("/new/plan")}
                      >
                        Изменить план
                      </button>
                    </section>
                  </div>
                  <div className="inline-note">
                    <IconClock size={20} />
                    <span>
                      Контрольные проверки: {scheduleOf(draft).times.join(", ")}
                    </span>
                  </div>
                  {formError && <p className="error">{formError}</p>}
                </>
              )}
            </div>
            <footer className="wizard-footer">
              <button
                className="text-button"
                disabled={saving}
                onClick={() => completeObject(true)}
              >
                <IconDeviceFloppy size={22} />
                Сохранить черновик
              </button>
              <div>
                <Button
                  onClick={() =>
                    step
                      ? nav(
                          "/new/" +
                            ["object", "cameras", "plan", "review"][step - 1],
                        )
                      : nav("/objects")
                  }
                >
                  Назад
                </Button>
                <Button
                  kind="primary"
                  disabled={
                    saving ||
                    (step === 1 && !cameraValid) ||
                    (step === 2 && !draft.plan.length)
                  }
                  onClick={() => {
                    if (step === 0 && !draft.name.trim()) {
                      setFormError("Введите название объекта");
                      return;
                    }
                    if (step === 3) completeObject();
                    else
                      nav(
                        "/new/" +
                          ["object", "cameras", "plan", "review"][step + 1],
                      );
                  }}
                >
                  {saving
                    ? "Сохраняем…"
                    : step === 3
                      ? "Создать объект"
                      : "Продолжить"}
                </Button>
              </div>
            </footer>
          </>
        ) : route === "/objects" ? (
          <PortfolioDashboard
            objects={objects}
            reports={portfolioReports}
            movements={portfolioMovements}
            serverBacked={account?.kind === "user"}
            date={viewDate}
            today={TODAY}
            onDate={setViewDate}
            onAdd={newObject}
            onOpen={(id) => nav(`/object/${id}/day`)}
            Modal={Modal}
          />
        ) : (
          <>
            <div className="heading-row project-heading">
              <div>
                <h1>{object.name}</h1>
                <p className="subtitle">
                  <span>{object.type}</span>
                  <span className="dot-sep" aria-hidden="true" />
                  <IconMapPin size={16} />
                  {object.address || "Адрес не указан"}
                </p>
              </div>
              <Button
                kind="primary"
                onClick={() => startCheck()}
                disabled={!cams.length || tab === "snapshot"}
              >
                <IconPlus size={20} />
                Новая проверка
              </Button>
            </div>
            {tab === "day" ? (
              <>
                <div className="day-bar">
                  <div className="day-picker">
                    <button
                      className="icon-button"
                      aria-label="Предыдущий день"
                      onClick={() => shiftDay(-1)}
                    >
                      <IconChevronLeft size={20} />
                    </button>
                    <span className="day-date">
                      <strong>{dateLabel(viewDate)}</strong>
                      <small>
                        {viewDate === TODAY ? "Сегодня" : "Прошедший день"} ·{" "}
                        {timezoneLabel(object.timezone)}
                      </small>
                    </span>
                    <button
                      className="icon-button"
                      aria-label="Следующий день"
                      disabled={viewDate >= TODAY}
                      onClick={() => shiftDay(1)}
                    >
                      <IconChevronRight size={20} />
                    </button>
                    {viewDate !== TODAY && (
                      <button
                        className="text-button small"
                        onClick={() => {
                          setViewDate(TODAY);
                          setDayCell(null);
                        }}
                      >
                        К сегодняшнему дню
                      </button>
                    )}
                  </div>
                  <div className="day-verdict">
                    <span className="eyebrow">ЭТАПЫ НА ЭТУ ДАТУ</span>
                    {dayStatus}
                  </div>
                  <div className="day-coverage">
                    {account?.kind === "user" && dayReportLoading ? (
                      <strong>…</strong>
                    ) : (
                      <strong>
                        {summary.received} из {summary.expected}
                      </strong>
                    )}
                    <small>
                      {account?.kind === "user" && dayReportLoading
                        ? "считаем проверки"
                        : "проверок за день"}
                    </small>
                  </div>
                </div>
                {account?.kind === "user" && dayReportLoading ? (
                  <div className="inline-note">
                    <IconLoader2 className="spin" size={20} />
                    <span>Собираем результаты проверок за выбранный день.</span>
                  </div>
                ) : account?.kind === "user" && dayReportError ? (
                  <div className="inline-note error-note">
                    <IconAlertTriangle size={20} />
                    <span>{dayReportError}</span>
                    <Button
                      onClick={() => setDayReportNonce((value) => value + 1)}
                    >
                      Повторить
                    </Button>
                  </div>
                ) : todayPlan.length ? (
                  <>
                    {(todayPlan.some((p) => p.evidence.type === "warning" && p.evidence.source === "cameras") || movementSignal) && (
                      <div className="day-observations">
                        {todayPlan
                          .filter((p) => p.evidence.type === "warning" && p.evidence.source === "cameras")
                          .map((p) => (
                            <article className="day-observation stage-warning" key={p.id}>
                              <IconAlertTriangle size={22} />
                              <div>
                                <strong>Работы по этапу не видны на контрольных снимках</strong>
                                <p>{p.name}: {p.evidence.count}. Нужна проверка на площадке.</p>
                                <button
                                  className="text-button small"
                                  onClick={() => setExpandedStage(p.id)}
                                >
                                  Показать объяснения по времени
                                  <IconArrowRight size={15} />
                                </button>
                              </div>
                            </article>
                          ))}
                        {movementSignal && (
                          <article className="day-observation movement-warning">
                            <IconPlayerPause size={22} />
                            <div>
                              <strong>
                                {equipmentLabel(movementSignal.equipment_type).replace(/^./, (letter) => letter.toLocaleUpperCase("ru-RU"))} без видимых перемещений {movementSignal.idle_days} {plural(movementSignal.idle_days, "день", "дня", "дней")}
                              </strong>
                              <p>
                                Камера «{movementSignal.camera_name}» · {shortDate(movementSignal.start_date)} — {shortDate(movementSignal.end_date)} · {movementSignal.observation_count} {plural(movementSignal.observation_count, "наблюдение", "наблюдения", "наблюдений")}. Положение на контрольных кадрах не менялось; это не доказывает непрерывный простой.
                              </p>
                              {!!movementSignal.images?.length && (
                                <button
                                  className="text-button small"
                                  onClick={() => {
                                    const frames = [movementSignal.images[0], movementSignal.images.at(-1)];
                                    setPhoto({
                                      kind: "movement",
                                      time: `${shortDate(movementSignal.start_date)} — ${shortDate(movementSignal.end_date)}`,
                                      cams: frames.map((image) => ({
                                        id: image.id,
                                        name: movementSignal.camera_name,
                                        zone: new Date(image.observed_at).toLocaleString("ru-RU", { day: "numeric", month: "long", hour: "2-digit", minute: "2-digit" }),
                                        photo: image.url,
                                      })),
                                    });
                                  }}
                                >
                                  Сравнить первый и последний кадры
                                  <IconArrowRight size={15} />
                                </button>
                              )}
                            </div>
                          </article>
                        )}
                      </div>
                    )}
                    <div className="section-heading">
                      <div>
                        <h2>
                          Этапы по интервалам <span>{todayPlan.length}</span>
                        </h2>
                        <p className="helper">
                          В ячейках — результаты проверок по времени, справа —
                          итог этапа за день
                        </p>
                      </div>
                      <button
                        className="text-button"
                        onClick={() => objnav("settings")}
                      >
                        <IconSettings size={17} />
                        Расписание: {schedule.times.join(" · ")}
                      </button>
                      {devMode && summary.rulesVersion && (
                        <span className="dev-tag">
                          {summary.rulesVersion} · расписание v
                          {summary.scheduleVersion}
                        </span>
                      )}
                    </div>
                    <div className="matrix">
                      <div className="matrix-head" style={matrixCols}>
                        <span>Этап</span>
                        {schedule.times.map((t) => (
                          <span key={t} className="matrix-time">
                            {t}
                          </span>
                        ))}
                        <span>Дневная оценка</span>
                      </div>
                      {todayPlan.map((p) => (
                        <React.Fragment key={p.id}>
                          <div
                            className={`matrix-row ${expandedStage === p.id ? "expanded" : ""}`}
                            style={matrixCols}
                          >
                            <button
                              className="matrix-stage"
                              aria-expanded={expandedStage === p.id}
                              onClick={() =>
                                setExpandedStage(
                                  expandedStage === p.id ? null : p.id,
                                )
                              }
                            >
                              <IconChevronRight
                                size={17}
                                className="matrix-caret"
                              />
                              <span>
                                <strong>
                                  {p.name}
                                  {!!p.children?.length && (
                                    <span className="substage-count">
                                      {p.children.length}{" "}
                                      {plural(
                                        p.children.length,
                                        "подэтап",
                                        "подэтапа",
                                        "подэтапов",
                                      )}
                                    </span>
                                  )}
                                </strong>
                                <small>
                                  {p.zone} · {shortDate(p.start)} —{" "}
                                  {shortDate(p.end)}
                                </small>
                              </span>
                            </button>
                            {p.evidence.cells.map((cell) => {
                              const CellIcon = cellMeta[cell.state].icon;
                              return (
                                <button
                                  key={cell.time}
                                  className={`matrix-cell ${cell.state}`}
                                  title={`${cell.time} · ${cellMeta[cell.state].title}`}
                                  aria-label={`${p.name}, ${cell.time}: ${cellMeta[cell.state].title}`}
                                  onClick={() => setDayCell({ stage: p, cell })}
                                >
                                  <CellIcon size={18} />
                                </button>
                              );
                            })}
                            <div className="matrix-verdict">
                              <div className="verdict-line">
                                <Badge type={p.evidence.type}>
                                  {p.evidence.label}
                                </Badge>
                                {methodTag(p, p.evidence.source)}
                              </div>
                              <small>{p.evidence.count}</small>
                              {needsManual(p) && (
                                <button
                                  className="text-button small"
                                  onClick={() => openInspection(p)}
                                >
                                  <IconClipboardCheck size={15} />
                                  Подтвердить вручную
                                </button>
                              )}
                            </div>
                          </div>
                          {expandedStage === p.id && (
                            <div className="matrix-detail">
                              {evidenceDetail(p, p.evidence)}
                            </div>
                          )}
                        </React.Fragment>
                      ))}
                    </div>
                    <div className="matrix-legend">
                      {[
                        ["positive", "признак найден"],
                        ["none", "проверка есть, признака нет"],
                        ["missing", "проверки не было"],
                        ["uncovered", "камеры не покрывают"],
                      ].map(([state, label]) => {
                        const CellIcon = cellMeta[state].icon;
                        return (
                          <span key={state}>
                            <i className={`matrix-cell ${state}`}>
                              <CellIcon size={14} />
                            </i>
                            {label}
                          </span>
                        );
                      })}
                    </div>
                  </>
                ) : (
                  <Empty
                    icon={IconCalendar}
                    title="Нет работ по плану на эту дату"
                    detail="Добавьте этапы с датами для визуального контроля."
                    action={
                      <Button onClick={() => objnav("plan")}>
                        Открыть план
                      </Button>
                    }
                  />
                )}
                <div className="section-heading">
                  <div>
                    <h2>
                      Снимки камер <span>{cams.length}</span>
                    </h2>
                    <p className="helper">
                      Те же интервалы дня, по одной строке на камеру
                    </p>
                  </div>
                  <button
                    className="text-button"
                    onClick={() => {
                      setHistoryView("film");
                      objnav("history");
                    }}
                  >
                    Плёнка за период
                    <IconArrowUpRight size={17} />
                  </button>
                </div>
                {cams.length ? (
                  <div className="matrix film-matrix">
                    <div className="matrix-head" style={filmCols}>
                      <span>Камера</span>
                      {schedule.times.map((t) => (
                        <span key={t} className="matrix-time">
                          {t}
                        </span>
                      ))}
                    </div>
                    {cams.map((c) => (
                      <div className="matrix-row" key={c.id} style={filmCols}>
                        <button
                          className="matrix-stage"
                          onClick={() => openPassport(c)}
                          aria-label={`Паспорт камеры ${c.name}`}
                        >
                          <IconFileDescription
                            size={17}
                            className="matrix-caret"
                          />
                          <span>
                            <strong>
                              {c.name}
                              {c.code && (
                                <span className="substage-count">{c.code}</span>
                              )}
                            </strong>
                            <small>{c.zone || "Зона не указана"}</small>
                          </span>
                        </button>
                        {schedule.times.map((time) => {
                          const check = dayChecks.find((s) => s.time === time);
                          const shot = check?.cams.find(
                            (x) => x.id === c.id && x.photo,
                          );
                          return shot ? (
                            <button
                              key={time}
                              className="film-cell"
                              aria-label={`Снимок ${c.name} в ${time}`}
                              onClick={() =>
                                setPhoto({
                                  cams: [shot],
                                  time,
                                  date: viewDate,
                                  snapId: check.id,
                                })
                              }
                            >
                              <img
                                src={shot.photo}
                                alt={`${c.name}, ${time}`}
                              />
                              {(shot.source || check.source) === "manual" && (
                                <em
                                  className="manual-mark"
                                  title="Загружено вручную"
                                >
                                  <IconUpload size={11} />
                                </em>
                              )}
                            </button>
                          ) : (
                            <div key={time} className="film-cell empty">
                              {check ? "нет кадра" : "ожидается"}
                            </div>
                          );
                        })}
                      </div>
                    ))}
                  </div>
                ) : (
                  <Empty
                    title="Добавьте первую камеру"
                    action={
                      <Button
                        kind="primary"
                        onClick={() => {
                          objnav("settings");
                          setTimeout(() => setEditingCams([]), 0);
                        }}
                      >
                        Добавить камеру
                      </Button>
                    }
                  />
                )}
              </>
            ) : tab === "settings" ? (
              <>
                {editingCams ? (
                  <>
                    <div className="section-heading">
                      <div>
                        <h2>Настройка камер</h2>
                        <p className="helper">
                          Количество, названия и зоны обзора
                        </p>
                      </div>
                      <Button onClick={() => setEditingCams(null)}>
                        Отмена
                      </Button>
                    </div>
                    <CameraForm
                      cams={editingCams}
                      existing
                      needCamera={false}
                      onChange={setEditingCams}
                      onConfirm={saveCameras}
                    />
                  </>
                ) : (
                  <>
                    <div className="settings-card">
                      <h3>Реквизиты объекта</h3>
                      <div className="two-fields">
                        <Field label="Название объекта">
                          <input
                            value={object.name}
                            onChange={(e) =>
                              updateObject((o) => ({
                                ...o,
                                name: e.target.value,
                              }))
                            }
                          />
                        </Field>
                        <Field label="Тип объекта">
                          <select
                            value={object.type}
                            onChange={(e) =>
                              updateObject((o) => ({
                                ...o,
                                type: e.target.value,
                              }))
                            }
                          >
                            {objectTypeOptions(object.type)}
                          </select>
                        </Field>
                      </div>
                      <div className="two-fields">
                        <Field label="Адрес или описание площадки">
                          <input
                            value={object.address || ""}
                            onChange={(e) =>
                              updateObject((o) => ({
                                ...o,
                                address: e.target.value,
                              }))
                            }
                          />
                        </Field>
                        <Field
                          label="Часовой пояс"
                          help="Определяет даты и контрольные интервалы"
                        >
                          <select
                            value={object.timezone || "Europe/Moscow"}
                            onChange={(e) =>
                              updateObject((o) => ({
                                ...o,
                                timezone: e.target.value,
                              }))
                            }
                          >
                            <option value="Europe/Moscow">Москва, UTC+3</option>
                            <option value="Asia/Yekaterinburg">
                              Екатеринбург, UTC+5
                            </option>
                            <option value="Asia/Novosibirsk">
                              Новосибирск, UTC+7
                            </option>
                          </select>
                        </Field>
                      </div>
                    </div>
                    <div className="settings-card">
                      <h3>Расписание проверок</h3>
                      <p className="helper">
                        Количество и времена задают контрольные интервалы дня,
                        столбцы в контроле дня и знаменатель покрытия.
                      </p>
                      <div className="schedule-count">
                        <span className="field-label">Проверок в день</span>
                        <div className="counter">
                          <button
                            aria-label="Меньше проверок"
                            disabled={schedule.times.length <= 1}
                            onClick={removeSlot}
                          >
                            <IconMinus size={18} />
                          </button>
                          <span>{schedule.times.length}</span>
                          <button
                            aria-label="Больше проверок"
                            disabled={schedule.times.length >= 8}
                            onClick={addSlot}
                          >
                            <IconPlus size={18} />
                          </button>
                        </div>
                        <small>От одной до восьми проверок</small>
                      </div>
                      <div className="schedule-times">
                        {schedule.times.map((t, i) => (
                          <label key={i}>
                            <span>Проверка {i + 1}</span>
                            <input
                              type="time"
                              value={t}
                              onChange={(e) => setSlot(i, e.target.value)}
                            />
                          </label>
                        ))}
                      </div>
                      {new Set(schedule.times).size !==
                        schedule.times.length && (
                        <span className="error">
                          Времена проверок не должны повторяться
                        </span>
                      )}
                      <div className="two-fields">
                        <Field
                          label="Порог подтверждения"
                          help="Сколько независимых интервалов подтверждают этап"
                        >
                          <input
                            type="number"
                            min="1"
                            max="8"
                            value={schedule.confirm}
                            onChange={(e) =>
                              setSchedule({
                                confirm: Math.max(1, Number(e.target.value)),
                              })
                            }
                          />
                        </Field>
                        <Field
                          label="Порог отсутствия признаков"
                          help="Сколько пригодных интервалов дают возможное отклонение"
                        >
                          <input
                            type="number"
                            min="1"
                            max="8"
                            value={schedule.absence}
                            onChange={(e) =>
                              setSchedule({
                                absence: Math.max(1, Number(e.target.value)),
                              })
                            }
                          />
                        </Field>
                      </div>
                      {schedule.confirm > schedule.times.length && (
                        <div className="inline-note warning-note">
                          <IconAlertTriangle size={19} />
                          <span>
                            При {schedule.times.length}{" "}
                            {plural(
                              schedule.times.length,
                              "проверке",
                              "проверках",
                              "проверках",
                            )}{" "}
                            в день этап не сможет получить подтверждение: порог
                            выше числа интервалов.
                          </span>
                        </div>
                      )}
                      <p className="helper">
                        Изменение расписания действует с текущей даты и не
                        переписывает ранее рассчитанные дни.
                      </p>
                      <Button
                        kind="primary"
                        disabled={saving}
                        onClick={saveObjectSettings}
                      >
                        <IconDeviceFloppy size={18} />
                        {saving ? "Сохраняем…" : "Сохранить настройки"}
                      </Button>
                    </div>
                    <div className="section-heading">
                      <div>
                        <h2>
                          {archive ? "Архив камер" : "Камеры объекта"}{" "}
                          <span>
                            {archive
                              ? object.cams.filter((c) => c.archived).length
                              : cams.length}
                          </span>
                        </h2>
                        <p className="helper">
                          Именованные точки наблюдения строительной площадки
                        </p>
                      </div>
                      <div className="actions">
                        <Button onClick={() => setArchive(!archive)}>
                          <IconArchive size={18} />
                          {archive ? "Активные камеры" : "Архив"}
                        </Button>
                        <Button
                          kind="primary"
                          onClick={() =>
                            setEditingCams(cams.map((c) => ({ ...c })))
                          }
                        >
                          <IconAdjustments size={18} />
                          Настроить камеры
                        </Button>
                      </div>
                    </div>
                    <div className="camera-list">
                      {(archive
                        ? object.cams.filter((c) => c.archived)
                        : cams
                      ).map((c) => (
                        <article className="camera-list-row" key={c.id}>
                          {c.photo ? (
                            <button
                              onClick={() =>
                                setPhoto({ cams: [c], time: "12:00" })
                              }
                            >
                              <img src={c.photo} alt={c.name} />
                            </button>
                          ) : (
                            <div className="camera-list-empty">
                              <IconCamera size={36} stroke={1.4} />
                              <span>Нет снимка</span>
                            </div>
                          )}
                          <div>
                            <h3>
                              {c.name}
                              {c.code && (
                                <span className="substage-count">{c.code}</span>
                              )}
                            </h3>
                            <p>
                              <IconMapPin size={16} />
                              {c.zone || "Зона не указана"}
                            </p>
                            <small>
                              {(() => {
                                const l = latestCamera(c);
                                return l.lastDate
                                  ? `Последний снимок · ${shortDate(l.lastDate)} ${l.lastTime}`
                                  : "Фото ещё не загружено";
                              })()}
                            </small>
                          </div>
                          <div className="camera-row-actions">
                            {archive ? (
                              <Button
                                disabled={saving}
                                onClick={() => setCameraActive(c, true)}
                              >
                                Восстановить
                              </Button>
                            ) : (
                              <>
                                <button
                                  className="text-button"
                                  onClick={() => openPassport(c)}
                                >
                                  <IconFileDescription size={18} />
                                  Паспорт
                                </button>
                                <button
                                  className="text-button"
                                  onClick={() =>
                                    setEditingCams(cams.map((c) => ({ ...c })))
                                  }
                                >
                                  <IconPencil size={18} />
                                  Изменить
                                </button>
                                <button
                                  className="icon-button"
                                  aria-label={`Архивировать ${c.name}`}
                                  onClick={() =>
                                    setConfirm({
                                      title: `Архивировать «${c.name}»?`,
                                      text: "Камера исчезнет из новых проверок. Все снимки и результаты сохранятся в истории.",
                                      action: () => setCameraActive(c, false),
                                    })
                                  }
                                >
                                  <IconArchive size={20} />
                                </button>
                              </>
                            )}
                          </div>
                        </article>
                      ))}
                    </div>
                    {(archive
                      ? !object.cams.some((c) => c.archived)
                      : !cams.length) && (
                      <Empty
                        title={archive ? "Архив пуст" : "Камер пока нет"}
                        detail={
                          archive
                            ? "Здесь появятся камеры, которые вы архивируете."
                            : "Добавьте камеры и дайте им понятные названия."
                        }
                      />
                    )}
                    <div className="inline-note">
                      <IconInfoCircle size={20} />
                      <span>
                        Последний снимок не означает, что камера сейчас
                        подключена. {EDGE_NOTE}
                      </span>
                    </div>
                    {!object.archived && (
                      <div className="settings-card danger-zone">
                        <h3>Архив объекта</h3>
                        <p className="helper">
                          Объект исчезнет из текущей работы, но камеры, план и
                          вся история сохранятся.
                        </p>
                        <Button
                          disabled={saving}
                          onClick={() =>
                            setConfirm({
                              title: `Архивировать «${object.name}»?`,
                              text: "Объект можно будет открыть в списке архивных объектов. Данные не удаляются.",
                              action: archiveObject,
                            })
                          }
                        >
                          <IconArchive size={18} />
                          Архивировать объект
                        </Button>
                      </div>
                    )}
                  </>
                )}
              </>
            ) : tab === "plan" ? (
              <PlanEditor
                plan={object.plan}
                cams={cams}
                objectType={object.type}
                directoryItems={stageDirectory}
                onChange={savePlan}
              />
            ) : tab === "snapshot" ? (
              <PhotoCheck
                key={checkKey}
                cams={cams}
                date={snapshotDate}
                time={snapshotTime}
                timezoneLabel={timezoneLabel(object.timezone)}
                setDate={setSnapshotDate}
                setTime={setSnapshotTime}
                existing={object.snapshots}
                onComplete={finishCheck}
                onOpenExisting={(id) => objnav("result/" + id)}
                onCancel={() => objnav("day")}
              />
            ) : tab === "result" ? (
              snap ? (
                <>
                  <div className="section-heading">
                    <div>
                      <button
                        className="text-button small"
                        onClick={() => objnav("history")}
                      >
                        <IconArrowLeft size={17} />К истории
                      </button>
                      <h2>Проверка по фото · {snap.time}</h2>
                      <p className="helper">
                        {dateLabel(snap.date)} ·{" "}
                        {timezoneLabel(object.timezone)} ·{" "}
                        {snap.cams.filter((c) => c.photo).length} из{" "}
                        {snap.cams.length} камер
                      </p>
                    </div>
                    <Button kind="primary" onClick={() => objnav("day")}>
                      <IconArrowLeft size={18} />К контролю дня
                    </Button>
                  </div>
                  <div className="demo-analysis-note">
                    {snap.state === "error" ? (
                      <IconAlertTriangle size={20} />
                    ) : (
                      <IconInfoCircle size={20} />
                    )}
                    <span>
                      {snap.real && snap.state === "error"
                        ? snap.analysisAttempt?.error_code ===
                          "invalid_model_response"
                          ? "Ни основная, ни резервная модель не вернули ответ, прошедший проверку формата. Исходные ответы сохранены; запустите анализ повторно."
                          : "Не удалось получить результат ни от основной, ни от резервной модели. Фотографии сохранены; запустите анализ повторно."
                        : snap.real && snap.partial
                          ? "Анализ завершён частично: один или несколько кадров не удалось прочитать. Доступные результаты сохранены."
                          : snap.real
                            ? `Анализ завершён. Свидетельства ниже получены из загруженных фотографий.${
                                snap.analysisAttempt?.attempt_number > 1
                                  ? ` Ответ получен с попытки ${snap.analysisAttempt.attempt_number}, модель ${snap.analysisAttempt.model}.`
                                  : ""
                              }`
: "Фотографии сохранены."}
                    </span>
                    {snap.real && snap.state === "error" && (
                      <Button
                        disabled={saving}
                        onClick={() => retryAnalysis(snap)}
                      >
                        <IconRefresh size={18} />
                        Повторить анализ
                      </Button>
                    )}
                  </div>
                  <div className="section-heading">
                    <h2>Фотографии проверки</h2>
                    <Button
                      onClick={() =>
                        setPhoto({
                          cams: snap.cams.filter((c) => c.photo),
                          time: snap.time,
                        })
                      }
                      disabled={!snap.cams.some((c) => c.photo)}
                    >
                      <IconMaximize size={18} />
                      Сравнить камеры
                    </Button>
                  </div>
                  <div className="photo-grid">
                    {snap.cams.map((c) => (
                      <div key={c.id}>
                        {photoTile(c, snap.time, false, snap.date)}
                        {c.failed ? (
                          <Badge type="warning">Кадр не прочитан</Badge>
                        ) : c.photo ? (
                          <Badge
                            type={snap.real ? "success" : "neutral"}
                          >
                            {snap.real ? "Обработан" : "Сохранён"}
                          </Badge>
                        ) : (
                          <Badge type="neutral">Нет снимка</Badge>
                        )}
                      </div>
                    ))}
                  </div>
                  {snap.partial && (
                    <div className="retry-banner">
                      <div>
                        <strong>Не все снимки удалось обработать</strong>
                        <p>
                          Доступные результаты сохранены. Повторите анализ, если
                          качество исходных кадров позволяет.
                        </p>
                      </div>
                      <Button
                        disabled={saving}
                        onClick={() => retryAnalysis(snap)}
                      >
                        <IconRefresh size={18} />
                        Повторить анализ
                      </Button>
                    </div>
                  )}
                  <div className="section-heading">
                    <h2>Визуальные свидетельства</h2>
                    <span className="subtle">На момент {snap.time}</span>
                  </div>
                  <div className="evidence-list">
                    {(snap.plan || object.plan)
                      .filter((p) => p.start <= snap.date && p.end >= snap.date)
                      .map((p) => {
                        const e = checkEvidence(p, snap);
                        return (
                          <article key={p.id} className="result-stage">
                            <div className="result-stage-heading">
                              <h3>{p.name}</h3>
                              <Badge type={e.type}>
                                {e.type === "success"
                                  ? "Есть свидетельства"
                                  : e.label}
                              </Badge>
                            </div>
                            {evidenceDetail(p, e)}
                          </article>
                        );
                      })}
                  </div>
                  {modelBlock(snap)}
                  <div className="inline-note">
                    <IconInfoCircle size={20} />
                    <span>
                      Результат проверки — свидетельства на один момент времени.
                      Дневная оценка учитывает несколько проверок.
                    </span>
                  </div>
                  <Button kind="primary" onClick={() => objnav("day")}>
                    Вернуться к контролю дня
                    <IconArrowRight size={18} />
                  </Button>
                </>
              ) : (
                <Empty
                  title="Проверка не найдена"
                  action={
                    <Button onClick={() => startCheck()}>
                      Создать проверку
                    </Button>
                  }
                />
              )
            ) : tab === "inspections" ? (
              <>
                <div className="section-heading">
                  <div>
                    <h2>
                      Осмотры инженера{" "}
                      <span>{(object.inspections || []).length}</span>
                    </h2>
                    <p className="helper">
                      Подтверждайте здесь этапы, которые нельзя надёжно
                      проверить по камерам
                    </p>
                  </div>
                  <Button
                    kind="primary"
                    disabled={!object.plan.length}
                    onClick={() => openInspection(object.plan[0], viewDate)}
                  >
                    <IconPlus size={20} />
                    Новый осмотр
                  </Button>
                </div>
                {(object.inspections || []).length ? (
                  <>
                    <div className="toolbar">
                      <select
                        aria-label="Этап осмотра"
                        value={inspectionFilters.stageId}
                        onChange={(event) =>
                          setInspectionFilters({
                            ...inspectionFilters,
                            stageId: event.target.value,
                          })
                        }
                      >
                        <option value="all">Все этапы</option>
                        {object.plan.map((stage) => (
                          <option value={stage.id} key={stage.id}>
                            {stage.name}
                          </option>
                        ))}
                      </select>
                      <input
                        aria-label="Дата действия осмотра"
                        type="date"
                        value={inspectionFilters.date}
                        onChange={(event) =>
                          setInspectionFilters({
                            ...inspectionFilters,
                            date: event.target.value,
                          })
                        }
                      />
                      <select
                        aria-label="Вывод осмотра"
                        value={inspectionFilters.verdict}
                        onChange={(event) =>
                          setInspectionFilters({
                            ...inspectionFilters,
                            verdict: event.target.value,
                          })
                        }
                      >
                        <option value="all">Любой вывод</option>
                        {Object.entries(INSPECTION_RESULTS).map(
                          ([key, value]) => (
                            <option value={key} key={key}>
                              {value.label}
                            </option>
                          ),
                        )}
                      </select>
                      <button
                        className="text-button"
                        onClick={() =>
                          setInspectionFilters({
                            stageId: "all",
                            date: "",
                            verdict: "all",
                          })
                        }
                      >
                        Сбросить
                      </button>
                    </div>
                    {filteredInspections.length ? (
                      <div className="inspection-list">
                        {[...filteredInspections]
                          .sort((a, b) => b.date.localeCompare(a.date))
                          .map((i) => {
                            const stage = object.plan.find(
                              (p) => p.id === i.stageId,
                            );
                            const superseded =
                              i.superseded ||
                              object.inspections.some(
                                (o) =>
                                  o.stageId === i.stageId && o.date > i.date,
                              );
                            return (
                              <div className="inspection-item" key={i.id}>
                                {inspectionCard(i, stage)}
                                <div className="inspection-item-side">
                                  <span
                                    className={`source-tag ${superseded ? "muted" : ""}`}
                                  >
                                    {superseded
                                      ? "Отменён более поздним осмотром"
                                      : `Действует ${
                                          i.until && i.until !== i.date
                                            ? `по ${shortDate(i.until)}`
                                            : `на ${shortDate(i.date)}`
                                        }`}
                                  </span>
                                  {stage && (
                                    <button
                                      className="text-button small"
                                      onClick={() => {
                                        setViewDate(i.date);
                                        objnav("day");
                                      }}
                                    >
                                      Открыть день осмотра
                                      <IconArrowRight size={16} />
                                    </button>
                                  )}
                                </div>
                              </div>
                            );
                          })}
                      </div>
                    ) : (
                      <Empty
                        icon={IconSearch}
                        title="Осмотры не найдены"
                        detail="Измените дату, этап или вывод осмотра."
                        action={
                          <Button
                            onClick={() =>
                              setInspectionFilters({
                                stageId: "all",
                                date: "",
                                verdict: "all",
                              })
                            }
                          >
                            Сбросить фильтры
                          </Button>
                        }
                      />
                    )}
                  </>
                ) : (
                  <Empty
                    icon={IconClipboardCheck}
                    title="Осмотров ещё не было"
                    detail="Осмотр закрывает этап, который внешние камеры подтвердить не могут."
                    action={
                      <Button
                        kind="primary"
                        disabled={!object.plan.length}
                        onClick={() => openInspection(object.plan[0], viewDate)}
                      >
                        Новый осмотр
                      </Button>
                    }
                  />
                )}
                <div className="inline-note">
                  <IconInfoCircle size={20} />
                  <span>
                    Добавьте осмотр, если этап не виден камерам. В контроле дня
                    будет указано имя специалиста и дата осмотра.
                  </span>
                </div>
              </>
            ) : tab === "history" ? (
              <>
                <div className="section-heading">
                  <div>
                    <h2>История контроля</h2>
                    <p className="helper">
                      Проверки целиком или плёнка снимков по камерам
                    </p>
                  </div>
                  <div
                    className="view-switch"
                    role="group"
                    aria-label="Представление истории"
                  >
                    {[
                      ["list", "Проверки"],
                      ["film", "Плёнка по камерам"],
                    ].map(([key, label]) => (
                      <button
                        key={key}
                        className={historyView === key ? "selected" : ""}
                        aria-pressed={historyView === key}
                        onClick={() => setHistoryView(key)}
                      >
                        {label}
                      </button>
                    ))}
                  </div>
                </div>
                {historyView === "film" ? (
                  <>
                    <div className="toolbar">
                      <label className="inline-field">
                        Период с
                        <input
                          aria-label="Начало периода"
                          type="date"
                          max={viewDate}
                          value={filmDays[0]}
                          onChange={(e) => setFilmFrom(e.target.value)}
                        />
                        по {shortDate(viewDate)}
                      </label>
                      <button
                        className={`button ${filmCompare ? "primary" : ""}`}
                        onClick={() => {
                          setFilmCompare(filmCompare ? null : []);
                          setComparisonResult(null);
                        }}
                      >
                        <IconEye size={18} />
                        {filmCompare
                          ? "Выйти из сравнения"
                          : "Сравнить снимки камеры"}
                      </button>
                    </div>
                    {filmCompare && (
                      <p className="inline-note">
                        <IconInfoCircle size={19} />
                        <span>
                          Выберите два снимка одной камеры. Сравнение снимков
                          разных камер не выполняется.
                        </span>
                      </p>
                    )}
                    {object.cams.length ? (
                      <div className="matrix film-period" style={periodCols}>
                        <div className="matrix-head" style={periodCols}>
                          <span>Камера</span>
                          {filmDays.map((d) => (
                            <span key={d} className="matrix-time">
                              {d.split("-").reverse().slice(0, 2).join(".")}
                            </span>
                          ))}
                        </div>
                        {object.cams.map((c) => (
                          <div
                            className="matrix-row"
                            key={c.id}
                            style={periodCols}
                          >
                            <button
                              className="matrix-stage"
                              onClick={() => openPassport(c)}
                              aria-label={`Паспорт камеры ${c.name}`}
                            >
                              <IconFileDescription
                                size={17}
                                className="matrix-caret"
                              />
                              <span>
                                <strong>
                                  {c.name}
                                  {c.code && (
                                    <span className="substage-count">
                                      {c.code}
                                    </span>
                                  )}
                                </strong>
                                <small>
                                  {c.archived
                                    ? "В архиве · историческое имя"
                                    : `${c.zone || "Зона не указана"} · ракурс rev. ${c.fovRevision || 1}`}
                                </small>
                              </span>
                            </button>
                            {filmDays.map((day) => {
                              const shots = shotsFor(c, day);
                              return (
                                <div className="film-day" key={day}>
                                  {shots.length ? (
                                    shots.map((x) => {
                                      const picked = filmCompare?.some(
                                        (f) => f.key === x.key,
                                      );
                                      return (
                                        <button
                                          key={x.key}
                                          className={`film-thumb ${picked ? "picked" : ""}`}
                                          title={`${c.name} · ${shortDate(day)} ${x.time}`}
                                          aria-label={`Снимок ${c.name} ${shortDate(day)} в ${x.time}`}
                                          onClick={() => pickShot(c, x)}
                                        >
                                          <img
                                            src={x.photo}
                                            alt={`${c.name}, ${x.time}`}
                                          />
                                          {x.source === "manual" && (
                                            <em
                                              className="manual-mark"
                                              title="Загружено вручную"
                                            >
                                              <IconUpload size={11} />
                                            </em>
                                          )}
                                          <span>{x.time}</span>
                                        </button>
                                      );
                                    })
                                  ) : (
                                    <span className="film-none">—</span>
                                  )}
                                </div>
                              );
                            })}
                          </div>
                        ))}
                      </div>
                    ) : (
                      <Empty
                        title="У объекта пока нет камер"
                        detail="Добавьте камеры в настройках объекта."
                      />
                    )}
                    {filmCompare?.length === 2 && (
                      <div className="compare-panel">
                        <div className="section-heading">
                          <div>
                            <h2>Сравнение снимков</h2>
                            <p className="helper">
                              Камера «{filmCompare[0].camName}» · один ракурс
                            </p>
                          </div>
                          <Button
                            onClick={() => {
                              setFilmCompare([]);
                              setComparisonResult(null);
                            }}
                          >
                            Очистить выбор
                          </Button>
                        </div>
                        <div className="compare-pair">
                          {filmCompare.map((f) => (
                            <figure key={f.key}>
                              <img src={f.photo} alt={`${f.date} ${f.time}`} />
                              <figcaption>
                                {dateLabel(f.date)} · {f.time}
                              </figcaption>
                            </figure>
                          ))}
                        </div>
                        <div className="compare-result">
                          {comparisonResult?.state === "completed" ? (
                            <>
                              <Badge
                                type={
                                  comparisonResult.result.status === "unchanged"
                                    ? "success"
                                    : comparisonResult.result.status ===
                                        "changed"
                                      ? "warning"
                                      : "neutral"
                                }
                              >
                                {comparisonResult.result.status === "unchanged"
                                  ? "Заметного перемещения не найдено"
                                  : comparisonResult.result.status === "changed"
                                    ? "Положение изменилось"
                                    : "Сопоставить не удалось"}
                              </Badge>
                              <p>{comparisonResult.result.description}</p>
                              <p className="helper">
                                Уверенность:{" "}
                                {Math.round(
                                  comparisonResult.result.confidence * 100,
                                )}
                                %
                                {comparisonResult.result.equipment_type !==
                                  "unknown" &&
                                  ` · ${comparisonResult.result.equipment_type}`}
                              </p>
                              {!!comparisonResult.result.limitations
                                ?.length && (
                                <p className="helper">
                                  Ограничения:{" "}
                                  {comparisonResult.result.limitations.join(
                                    "; ",
                                  )}
                                </p>
                              )}
                            </>
                          ) : comparisonResult?.state === "error" ? (
                            <>
                              <Badge type="warning">
                                Сравнение не выполнено
                              </Badge>
                              <p className="helper">
                                {comparisonResult.error_detail ||
                                  "Повторите попытку позже."}
                              </p>
                              <Button onClick={analyzeFilmComparison}>
                                Повторить
                              </Button>
                            </>
                          ) : (
                            <>
                              <Badge type="neutral">
                                Снимки для сравнения выбраны
                              </Badge>
                              <p className="helper">
                                Модель сопоставит технику только на этих двух
                                контрольных снимках. Это не доказывает
                                непрерывный простой между проверками.
                              </p>
                              <Button
                                kind="primary"
                                disabled={
                                  comparisonLoading ||
                                  !filmCompare.every(
                                    (item) => item.imageId && item.objectId,
                                  )
                                }
                                onClick={analyzeFilmComparison}
                              >
                                {comparisonLoading
                                  ? "Сравниваем…"
                                  : filmCompare.every(
                                        (item) => item.imageId && item.objectId,
                                      )
                                    ? "Запустить сравнение"
                                    : "Нужны снимки из проверок"}
                              </Button>
                            </>
                          )}
                        </div>
                      </div>
                    )}
                  </>
                ) : (
                  <>
                    <div className="toolbar">
                      <input
                        aria-label="Дата в истории"
                        type="date"
                        value={historyDate}
                        onChange={(e) => setHistoryDate(e.target.value)}
                      />
                      <select
                        aria-label="Камера в истории"
                        value={historyCamera}
                        onChange={(e) => setHistoryCamera(e.target.value)}
                      >
                        <option value="all">Все камеры</option>
                        {object.cams.map((c) => (
                          <option value={c.id} key={c.id}>
                            {c.name}
                            {c.archived ? " · в архиве" : ""}
                          </option>
                        ))}
                      </select>
                      <select
                        aria-label="Происхождение снимков"
                        value={historySource}
                        onChange={(e) => setHistorySource(e.target.value)}
                      >
                        <option value="all">Любое происхождение</option>
                        <option value="camera">Снимки с камер</option>
                        <option value="manual">Загружено вручную</option>
                      </select>
                      <select
                        aria-label="Состояние анализа"
                        value={historyStatus}
                        onChange={(e) => setHistoryStatus(e.target.value)}
                      >
                        <option value="all">Любое состояние</option>
                        <option value="completed">Анализ готов</option>
                        <option value="partial">Анализ частично</option>
                        <option value="error">Ошибка анализа</option>
                        <option value="draft">Черновик</option>
                      </select>
                      <button
                        className="text-button"
                        onClick={() => {
                          setHistoryDate("");
                          setHistoryCamera("all");
                          setHistoryStatus("all");
                          setHistorySource("all");
                        }}
                      >
                        Сбросить
                      </button>
                    </div>
                    <div className="history-list">
                      {object.snapshots
                        .filter(
                          (s) =>
                            (!historyDate || s.date === historyDate) &&
                            (historyCamera === "all" ||
                              s.cams.some(
                                (c) => c.id === historyCamera && c.photo,
                              )) &&
                            (historyStatus === "all" ||
                              snapshotState(s) === historyStatus) &&
                            (historySource === "all" ||
                              snapshotSource(s) === historySource),
                        )
                        .map((s) => (
                          <button
                            className="history-row"
                            key={s.id}
                            onClick={() => objnav("result/" + s.id)}
                          >
                            <span className="history-time">
                              {s.time}
                              <small>{shortDate(s.date)}</small>
                            </span>
                            <div className="history-thumbs">
                              {s.cams
                                .filter((c) => c.photo)
                                .slice(0, 2)
                                .map((c) => (
                                  <img key={c.id} src={c.photo} alt={c.name} />
                                ))}
                            </div>
                            <div className="history-row-detail">
                              <strong>
                                {snapshotSource(s) === "manual" ? (
                                  <IconUpload size={15} />
                                ) : (
                                  <IconCamera size={15} />
                                )}
                                {SOURCE_LABELS[snapshotSource(s)]}
                              </strong>
                              <small>
                                {s.cams.filter((c) => c.photo).length} из{" "}
                                {s.cams.length} камер · исходные снимки
                                сохранены
                              </small>
                            </div>
                            <Badge
                              type={
                                (
                                  HISTORY_STATE_META[snapshotState(s)] ||
                                  HISTORY_STATE_META.draft
                                ).type
                              }
                            >
                              {
                                (
                                  HISTORY_STATE_META[snapshotState(s)] ||
                                  HISTORY_STATE_META.draft
                                ).label
                              }
                            </Badge>
                            <IconChevronRight size={22} />
                          </button>
                        ))}
                    </div>
                    {!object.snapshots.some(
                      (s) =>
                        (!historyDate || s.date === historyDate) &&
                        (historyCamera === "all" ||
                          s.cams.some(
                            (c) => c.id === historyCamera && c.photo,
                          )) &&
                        (historyStatus === "all" ||
                          snapshotState(s) === historyStatus) &&
                        (historySource === "all" ||
                          snapshotSource(s) === historySource),
                    ) && (
                      <Empty
                        icon={IconHistory}
                        title="Проверок не найдено"
                        detail="Измените фильтры или загрузите первую проверку по фото."
                        action={
                          <Button onClick={() => startCheck()}>
                            Новая проверка
                          </Button>
                        }
                      />
                    )}
                  </>
                )}
              </>
            ) : null}
          </>
        )}
      </main>
      {toast && (
        <div className="toast" role="status">
          <IconCircleCheck size={21} />
          {toast}
        </div>
      )}
      {confirm && (
        <Modal title={confirm.title} onClose={() => setConfirm(null)}>
          <p>{confirm.text}</p>
          <div className="modal-actions">
            <Button onClick={() => setConfirm(null)}>Отмена</Button>
            <Button
              kind="primary"
              onClick={() => {
                confirm.action();
                setConfirm(null);
              }}
            >
              Архивировать
            </Button>
          </div>
        </Modal>
      )}
      {photo && (
        <Modal
          title={`Исходные снимки · ${photo.time}`}
          wide
          onClose={() => setPhoto(null)}
        >
          <div className={`viewer ${photo.cams.length > 1 ? "compare" : ""}`}>
            {photo.cams.map((c) => (
              <figure key={c.id}>
                <img src={c.photo} alt={c.name} />
                <figcaption>
                  <strong>{c.name}</strong>
                  <span>{c.zone}</span>
                </figcaption>
              </figure>
            ))}
          </div>
          <p className="helper">
            {photo.kind === "movement"
              ? "Первый и последний контрольные кадры одной камеры. Они не доказывают непрерывный простой между наблюдениями."
              : <>{photo.date ? `${dateLabel(photo.date)} · ` : ""}Снимки одного контрольного времени. Количество техники между камерами не суммируется.</>}
          </p>
          {photo.snapId && (
            <div className="actions">
              <Button
                kind="primary"
                onClick={() => {
                  const snapshotId = photo.snapId;
                  setPhoto(null);
                  objnav(`result/${snapshotId}`);
                }}
              >
                Открыть проверку
                <IconArrowRight size={18} />
              </Button>
            </div>
          )}
        </Modal>
      )}
      {passport && (
        <Modal title="Паспорт камеры" onClose={() => setPassport(null)} wide>
          <div className="passport">
            <div className="passport-head">
              <span className="passport-code">{passport.code || "CAM-??"}</span>
              <span>
                <strong>{passport.name}</strong>
                <small>
                  {object.name} · {labelOf(VIEW_TYPES, passport.viewType)} ·{" "}
                  {labelOf(ORIENTATIONS, passport.orientation)} · ракурс rev.{" "}
                  {passport.fovRevision || 1}
                </small>
              </span>
            </div>
            <div className="passport-body">
              <div className="passport-photo">
                {passport.photo ? (
                  <img
                    src={passport.photo}
                    alt={`Ракурс камеры ${passport.name}`}
                  />
                ) : (
                  <div className="photo-missing">
                    <IconCamera size={36} stroke={1.4} />
                    <span>Нет снимка</span>
                  </div>
                )}
                <small>Текущий ракурс камеры</small>
                <div className="passport-side">
                  <span className="eyebrow">РАСПИСАНИЕ СЪЁМКИ</span>
                  <div className="passport-chips">
                    {schedule.times.map((t) => (
                      <span className="chip" key={t}>
                        {t}
                      </span>
                    ))}
                  </div>
                  <button
                    className="text-button small"
                    onClick={() => {
                      setPassport(null);
                      objnav("settings");
                    }}
                  >
                    Изменить расписание объекта
                    <IconArrowRight size={16} />
                  </button>
                </div>
                <div className="passport-side">
                  <span className="eyebrow">РЕВИЗИЯ РАКУРСА</span>
                  <p className="passport-revision">
                    rev. {passport.fovRevision || 1}
                  </p>
                  <p className="helper">
                    Снимки разных ревизий не сравниваются между собой: смена
                    ракурса разрывает цепочку наблюдений за техникой.
                  </p>
                  <button
                    className="text-button small"
                    disabled={saving}
                    onClick={incrementPassportRevision}
                  >
                    <IconRefresh size={16} />
                    Зафиксировать новый ракурс
                  </button>
                </div>
              </div>
              <div className="passport-fields">
                <div className="two-fields">
                  <Field
                    label="Код камеры"
                    help="Не меняется при переименовании"
                  >
                    <input value={passport.code || ""} disabled />
                  </Field>
                  <Field label="Название">
                    <input
                      value={passport.name}
                      onChange={(e) =>
                        setPassport({ ...passport, name: e.target.value })
                      }
                    />
                  </Field>
                </div>
                <Field label="Описание ракурса">
                  <input
                    placeholder="Что именно видно с этой точки"
                    value={passport.viewDescription || ""}
                    onChange={(e) =>
                      setPassport({
                        ...passport,
                        viewDescription: e.target.value,
                      })
                    }
                  />
                </Field>
                <div className="two-fields">
                  <Field
                    label="Тип точки наблюдения"
                    help={`Код для интеграции: ${passport.viewType || VIEW_TYPES[0][0]}`}
                  >
                    <select
                      value={passport.viewType || VIEW_TYPES[0][0]}
                      onChange={(e) =>
                        setPassport({ ...passport, viewType: e.target.value })
                      }
                    >
                      {VIEW_TYPES.map(([key, title]) => (
                        <option key={key} value={key}>
                          {title}
                        </option>
                      ))}
                    </select>
                  </Field>
                  <Field
                    label="Ориентация камеры"
                    help={`Код для интеграции: ${passport.orientation || "не задан"}`}
                  >
                    <select
                      value={passport.orientation || ""}
                      onChange={(e) =>
                        setPassport({
                          ...passport,
                          orientation: e.target.value,
                        })
                      }
                    >
                      <option value="">Не указана</option>
                      {ORIENTATIONS.map(([key, title]) => (
                        <option key={key} value={key}>
                          {title}
                        </option>
                      ))}
                    </select>
                  </Field>
                </div>
                <div className="two-fields">
                  <Field label="Расположение на объекте">
                    <input
                      placeholder="северо-восточная часть объекта"
                      value={passport.placement || ""}
                      onChange={(e) =>
                        setPassport({ ...passport, placement: e.target.value })
                      }
                    />
                  </Field>
                  <Field label="Зона обзора" help="Короткая подпись в списках">
                    <input
                      value={passport.zone || ""}
                      onChange={(e) =>
                        setPassport({ ...passport, zone: e.target.value })
                      }
                    />
                  </Field>
                </div>
                <Field
                  label="Покрытие"
                  help="Участки объекта в кадре, через запятую"
                >
                  <input
                    placeholder="котлован, корпус 1, проезд"
                    value={passport.coverageText}
                    onChange={(e) =>
                      setPassport({
                        ...passport,
                        coverageText: e.target.value,
                      })
                    }
                  />
                </Field>
                {!!passport.coverageText.trim() && (
                  <div className="passport-chips">
                    {passport.coverageText
                      .split(",")
                      .map((x) => x.trim())
                      .filter(Boolean)
                      .map((x) => (
                        <span className="chip" key={x}>
                          {x}
                        </span>
                      ))}
                  </div>
                )}
              </div>
            </div>
            <div className="inline-note">
              <IconInfoCircle size={20} />
              <span>{EDGE_NOTE}</span>
            </div>
            <div className="actions">
              <Button kind="primary" disabled={saving} onClick={savePassport}>
                {saving ? "Сохраняем…" : "Сохранить паспорт"}
              </Button>
              <Button onClick={() => setPassport(null)}>Закрыть</Button>
            </div>
          </div>
        </Modal>
      )}
      {dayCell && (
        <Modal
          title={`${dayCell.stage.name} · ${dayCell.cell.time}`}
          onClose={() => setDayCell(null)}
        >
          <div className="cell-modal">
            <Badge
              type={
                dayCell.cell.state === "positive"
                  ? "success"
                  : dayCell.cell.state === "uncovered"
                    ? "muted"
                    : "neutral"
              }
            >
              {cellMeta[dayCell.cell.state].title}
            </Badge>
            <p>
              {dayCell.cell.state === "missing"
                ? `Проверка в ${dayCell.cell.time} ещё не выполнена, поэтому интервал не участвует в дневной оценке.`
                : dayCell.cell.state === "uncovered"
                  ? "Ни одна камера этого интервала не наблюдает этап, поэтому вывод об отсутствии работ по нему не делается."
                  : dayCell.cell.state === "positive"
                    ? "В этом интервале найдены признаки этапа. Подтверждение засчитывается один раз, повтор тех же снимков независимым наблюдением не считается."
                    : "Снимки интервала обработаны, признаков этапа на них нет. Интервал считается пригодным для вывода об отсутствии работ."}
            </p>
            {!!dayCell.cell.sources.length && (
              <div className="cell-photos">
                {dayCell.cell.sources.map((c) => (
                  <figure key={c.id}>
                    <button
                      onClick={() =>
                        setPhoto({ cams: [c], time: dayCell.cell.time })
                      }
                    >
                      <img src={c.photo} alt={c.name} />
                    </button>
                    <figcaption>
                      {c.name}
                      <small>{c.zone || "Зона не указана"}</small>
                    </figcaption>
                  </figure>
                ))}
              </div>
            )}
            {modelBlock(dayCell.cell.check, "Ответ модели за этот интервал")}
            <div className="actions">
              {dayCell.cell.check ? (
                <Button
                  kind="primary"
                  onClick={() => {
                    objnav("result/" + dayCell.cell.check.id);
                    setDayCell(null);
                  }}
                >
                  Открыть проверку
                  <IconArrowRight size={18} />
                </Button>
              ) : (
                <Button
                  kind="primary"
                  disabled={!cams.length}
                  onClick={() => {
                    setDayCell(null);
                    startCheck(dayCell.cell.time);
                  }}
                >
                  Загрузить снимки на {dayCell.cell.time}
                </Button>
              )}
              {needsManual(dayCell.stage) && (
                <Button
                  onClick={() => {
                    const stage = dayCell.stage;
                    setDayCell(null);
                    openInspection(stage);
                  }}
                >
                  <IconClipboardCheck size={18} />
                  Подтвердить вручную
                </Button>
              )}
            </div>
          </div>
        </Modal>
      )}
      {inspectionForm && (
        <Modal title="Осмотр инженера" onClose={closeInspection}>
          <form
            className="form-stack inspection-form"
            onSubmit={saveInspection}
          >
            <Field label="Этап плана">
              <select
                value={inspectionForm.stageId}
                onChange={(e) =>
                  setInspectionForm({
                    ...inspectionForm,
                    stageId: e.target.value,
                    until: "",
                    error: "",
                  })
                }
              >
                {object.plan.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
            </Field>
            <div className="two-fields">
              <Field label="Дата наблюдения">
                <input
                  type="date"
                  min={inspectionStage?.start}
                  max={inspectionStage?.end}
                  value={inspectionForm.date}
                  onChange={(e) =>
                    setInspectionForm({
                      ...inspectionForm,
                      date: e.target.value,
                    })
                  }
                />
              </Field>
              <Field
                label="Действует по"
                help={
                  inspectionAllowsPeriod
                    ? "Необязательно, в пределах дат этапа"
                    : "Период доступен для невидимых или частично видимых работ"
                }
              >
                <input
                  type="date"
                  min={inspectionForm.date}
                  max={inspectionStage?.end}
                  disabled={!inspectionAllowsPeriod}
                  value={inspectionForm.until}
                  onChange={(e) =>
                    setInspectionForm({
                      ...inspectionForm,
                      until: e.target.value,
                    })
                  }
                />
              </Field>
            </div>
            <div className="field">
              <span className="field-label">Вывод осмотра</span>
              <div className="verdict-switch">
                {Object.entries(INSPECTION_RESULTS).map(([key, v]) => (
                  <button
                    type="button"
                    key={key}
                    className={`chip ${inspectionForm.verdict === key ? "selected" : ""}`}
                    aria-pressed={inspectionForm.verdict === key}
                    onClick={() =>
                      setInspectionForm({ ...inspectionForm, verdict: key })
                    }
                  >
                    {v.label}
                  </button>
                ))}
              </div>
            </div>
            <div className="two-fields">
              <Field label="Кто проводил осмотр">
                <input
                  value={inspectionForm.author}
                  onChange={(e) =>
                    setInspectionForm({
                      ...inspectionForm,
                      author: e.target.value,
                    })
                  }
                />
              </Field>
              <Field label="Должность">
                <input
                  value={inspectionForm.role}
                  onChange={(e) =>
                    setInspectionForm({
                      ...inspectionForm,
                      role: e.target.value,
                    })
                  }
                />
              </Field>
            </div>
            <Field label="Что установлено на месте">
              <textarea
                rows="3"
                placeholder="Опишите, что осмотрено и на каком основании сделан вывод"
                value={inspectionForm.comment}
                onChange={(e) =>
                  setInspectionForm({
                    ...inspectionForm,
                    comment: e.target.value,
                  })
                }
              />
            </Field>
            <div className="field">
              <span className="field-label">Материалы осмотра</span>
              <div className="inspection-attachments">
                {inspectionForm.files.map((item, i) => (
                  <figure key={i}>
                    {item.file.type === "application/pdf" ? (
                      <span className="attachment-file">
                        <IconFileDescription size={25} />
                        <small>{item.file.name}</small>
                      </span>
                    ) : (
                      <img src={item.preview} alt={item.file.name} />
                    )}
                    <button
                      type="button"
                      className="icon-button"
                      aria-label="Убрать материал"
                      onClick={() => {
                        URL.revokeObjectURL(item.preview);
                        setInspectionForm({
                          ...inspectionForm,
                          files: inspectionForm.files.filter((_, n) => n !== i),
                          error: "",
                        });
                      }}
                    >
                      <IconX size={16} />
                    </button>
                  </figure>
                ))}
                {inspectionForm.files.length < 3 && (
                  <label className="attach-button">
                    <IconUpload size={19} />
                    Добавить файл
                    <input
                      type="file"
                      multiple
                      accept="image/jpeg,image/png,application/pdf"
                      onChange={(event) => {
                        addInspectionFiles(event.target.files);
                        event.target.value = "";
                      }}
                    />
                  </label>
                )}
              </div>
              <small>
                До трёх файлов JPEG, PNG или PDF, каждый не больше 20 МБ.
              </small>
            </div>
            {inspectionForm.error && (
              <p className="error" role="alert">
                {inspectionForm.error}
              </p>
            )}
            <div className="actions">
              <Button kind="primary" type="submit" disabled={saving}>
                {saving ? "Сохраняем…" : "Сохранить осмотр"}
              </Button>
              <Button type="button" onClick={closeInspection} disabled={saving}>
                Отмена
              </Button>
            </div>
          </form>
        </Modal>
      )}
      {help && (
        <AboutModal
          onClose={() => setHelp(false)}
          onCameras={() => {
            setHelp(false);
            nav("/new/cameras");
          }}
        />
      )}
    </>
  );
}
