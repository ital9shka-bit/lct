import React, { useEffect, useRef, useState } from "react";
import {
  IconArrowLeft,
  IconArrowRight,
  IconCamera,
  IconCheck,
  IconClock,
  IconInfoCircle,
  IconLoader2,
  IconPhoto,
  IconScan,
  IconUpload,
  IconX,
} from "@tabler/icons-react";

const MAX_IMAGE_BYTES = 20 * 1024 * 1024;
const ALLOWED_TYPES = new Set(["image/jpeg", "image/png"]);
const phases = [
  "Сохраняем фотографии",
  "Передаём снимки на анализ",
  "Сопоставляем результат с планом",
];
const samples = [
  "/assets/example-cam-01.png",
  "/assets/example-cam-02.png",
  "/assets/example-cam-03.png",
];

const uploadOf = (file, sample = false) => ({
  file,
  name: file.name,
  url: URL.createObjectURL(file),
  sample,
});

const errorFor = (file) => {
  if (!ALLOWED_TYPES.has(file.type)) return "Выберите файл JPEG или PNG";
  if (file.size > MAX_IMAGE_BYTES)
    return "Размер файла не должен превышать 20 МБ";
  return "";
};

export default function PhotoCheck({
  cams,
  date,
  time,
  timezoneLabel,
  setDate,
  setTime,
  existing,
  onComplete,
  onOpenExisting,
  onCancel,
}) {
  const [step, setStep] = useState(1);
  const [uploads, setUploads] = useState({});
  const [phase, setPhase] = useState(-1);
  const [error, setError] = useState("");
  const [sampleLoading, setSampleLoading] = useState(false);
  const inputs = useRef({});
  const bulkInput = useRef(null);
  const uploadsRef = useRef(uploads);
  const busy = phase >= 0;

  useEffect(() => {
    uploadsRef.current = uploads;
  }, [uploads]);
  useEffect(
    () => () => {
      Object.values(uploadsRef.current).forEach((item) =>
        URL.revokeObjectURL(item.url),
      );
    },
    [],
  );

  const duplicate = existing.find(
    (item) => item.date === date && item.time === time,
  );
  const count = cams.filter((camera) => uploads[camera.id]).length;
  const exampleCount = cams.filter((camera) => uploads[camera.id]?.sample).length;

  const assign = (cameraId, file, sample = false) => {
    const message = errorFor(file);
    if (message) {
      setError(`${file.name}: ${message}`);
      return;
    }
    setError("");
    setUploads((current) => {
      if (current[cameraId]) URL.revokeObjectURL(current[cameraId].url);
      return { ...current, [cameraId]: uploadOf(file, sample) };
    });
  };

  const assignMany = (fileList) => {
    const files = [...fileList];
    const invalid = files.find(errorFor);
    if (invalid) {
      setError(`${invalid.name}: ${errorFor(invalid)}`);
      return;
    }
    const free = cams.filter((camera) => !uploads[camera.id]);
    if (files.length > free.length) {
      setError(`Можно добавить ещё ${free.length} фото`);
      return;
    }
    setError("");
    setUploads((current) => {
      const next = { ...current };
      files.forEach((file, index) => {
        next[free[index].id] = uploadOf(file);
      });
      return next;
    });
  };

  const useExample = async () => {
    if (sampleLoading) return;
    setSampleLoading(true);
    setError("");
    try {
      const files = await Promise.all(
        cams.map(async (_camera, index) => {
          const response = await fetch(samples[index % samples.length]);
          if (!response.ok)
            throw new Error("Не удалось загрузить фотографии примера");
          const blob = await response.blob();
          return new File([blob], `camera-${index + 1}.png`, {
            type: "image/png",
          });
        }),
      );
      setUploads((current) => {
        Object.values(current).forEach((item) => URL.revokeObjectURL(item.url));
        return Object.fromEntries(
          cams.map((camera, index) => [
            camera.id,
            uploadOf(files[index], true),
          ]),
        );
      });
      setStep(2);
    } catch (cause) {
      setError(cause.message || "Не удалось подготовить фотографии примера");
    } finally {
      setSampleLoading(false);
    }
  };

  const analyse = async () => {
    if (busy || !count || duplicate || !date || !time) return;
    setError("");
    setPhase(0);
    try {
      await onComplete({ date, time, uploads }, (state) =>
        setPhase(state === "uploading" ? 0 : state === "queued" ? 1 : 2),
      );
    } catch (cause) {
      setError(
        cause.message || "Не удалось выполнить анализ. Попробуйте ещё раз.",
      );
      setPhase(-1);
    }
  };

  if (busy)
    return (
      <section
        className="processing-screen"
        aria-live="polite"
        aria-busy="true"
      >
        <div className="processing-icon">
          <IconScan size={40} stroke={1.4} />
        </div>
        <span className="eyebrow">ПРОВЕРКА ПО ФОТО · {time}</span>
        <h2>Анализируем состояние объекта</h2>
        <p>Страница обновится автоматически, когда результат будет готов.</p>
        <div className="processing-photos">
          {cams
            .filter((camera) => uploads[camera.id])
            .slice(0, 3)
            .map((camera) => (
              <img
                key={camera.id}
                src={uploads[camera.id].url}
                alt={camera.name}
              />
            ))}
        </div>
        <ol className="processing-phases">
          {phases.map((label, index) => (
            <li
              key={label}
              className={
                index < phase ? "done" : index === phase ? "current" : ""
              }
              aria-current={index === phase ? "step" : undefined}
            >
              {index < phase ? (
                <IconCheck size={21} />
              ) : index === phase ? (
                <IconLoader2 className="spin" size={21} />
              ) : (
                <span>{index + 1}</span>
              )}
              <strong>{label}</strong>
            </li>
          ))}
        </ol>
        <small>Обычно обработка занимает до полутора минут.</small>
      </section>
    );

  return (
    <section className="check-wizard">
      <div className="section-heading">
        <div>
          <button className="back-link" onClick={onCancel}>
            <IconArrowLeft size={16} />
            Вернуться к объекту
          </button>
          <h2>Новая проверка по фотографиям</h2>
        </div>
      </div>
      <ol className="check-steps">
        <li className={step === 1 ? "active" : "done"}>
          <span>{step === 2 ? <IconCheck size={17} /> : "1"}</span>Дата и время
        </li>
        <li className={step === 2 ? "active" : ""}>
          <span>2</span>Фотографии камер
        </li>
      </ol>
      {step === 1 ? (
        <>
          <div className="example-prompt">
            <div className="example-prompt-images" aria-hidden="true">
              {samples.map((source, index) => (
                <img key={source} src={source} alt="" className={`example-thumb-${index + 1}`} />
              ))}
            </div>
            <div className="example-prompt-copy">
              <strong>Хотите попробовать без своих фотографий?</strong>
              <p>Подставим готовые снимки для камер этого объекта. Вы увидите их перед отправкой и сможете заменить любым своим фото.</p>
              <button className="button primary" disabled={sampleLoading || !!duplicate} onClick={useExample}>
                {sampleLoading ? <IconLoader2 className="spin" size={19} /> : <IconPhoto size={19} />}
                {sampleLoading ? "Подставляем фотографии…" : "Подставить примерные фотографии"}
              </button>
              <small>Анализ через GateLLM запустится только после вашего подтверждения.</small>
            </div>
          </div>
          <div className="check-date-card">
          <div className="check-date-icon">
            <IconClock size={28} />
          </div>
          <h3>Когда сделаны фотографии?</h3>
          <p>
            Дата и время заполнены по выбранной проверке. Измените их, если
            снимки сделаны в другой момент.
          </p>
          <div className="snapshot-fields">
            <label className="field">
              Дата проверки
              <input
                type="date"
                value={date}
                onChange={(event) => setDate(event.target.value)}
              />
            </label>
            <label className="field">
              Контрольное время
              <input
                type="time"
                value={time}
                onChange={(event) => setTime(event.target.value)}
              />
            </label>
            <span>
              <IconClock size={17} />
              {timezoneLabel}
            </span>
          </div>
          <div className="inline-note">
            <IconInfoCircle size={19} />
            <span>
              Добавляйте в одну проверку фотографии, сделанные примерно в одно
              время.
            </span>
          </div>
          </div>
        </>
      ) : (
        <>
          <div className="check-context">
            <button className="text-button" onClick={() => setStep(1)}>
              <IconClock size={18} />
              {date.split("-").reverse().join(".")} · {time}{" "}
              <span>Изменить</span>
            </button>
            <span>{timezoneLabel}</span>
          </div>
          {exampleCount > 0 && (
            <div className="example-loaded" role="status">
              <IconPhoto size={22} />
              <div>
                <strong>Примерные фото добавлены: {exampleCount} из {cams.length}</strong>
                <p>Посмотрите снимки ниже или замените нужное фото. Проверка ещё не запущена.</p>
              </div>
              <button className="button primary" disabled={!count || !!duplicate || !date || !time} onClick={analyse}>
                Запустить AI-анализ
              </button>
            </div>
          )}
          {count < cams.length && (
            <div
              className="bulk-drop"
              onDragOver={(event) => event.preventDefault()}
              onDrop={(event) => {
                event.preventDefault();
                assignMany(event.dataTransfer.files);
              }}
            >
              <IconUpload size={25} />
              <div>
                <strong>Перетащите несколько фотографий сюда</strong>
                <p>
                  Файлы займут свободные камеры по порядку. Проверьте соответствие
                  перед анализом.
                </p>
              </div>
              <input
                ref={bulkInput}
                type="file"
                accept="image/jpeg,image/png"
                multiple
                onChange={(event) => {
                  assignMany(event.target.files);
                  event.target.value = "";
                }}
              />
              <button
                className="button"
                onClick={() => bulkInput.current?.click()}
              >
                Выбрать файлы
              </button>
            </div>
          )}
          <div className="upload-summary">
            <strong>
              Выбрано фото: {count} из {cams.length}
            </strong>
            <span>
              {count === cams.length
                ? "Все камеры заполнены"
                : "Можно продолжить с неполным набором"}
            </span>
          </div>
          <div className="upload-grid">
            {cams.map((camera, index) => (
              <section key={camera.id} className="upload-camera">
                <div className="upload-camera-head">
                  <span className="camera-number">{index + 1}</span>
                  <div>
                    <h3>Камера {index + 1}</h3>
                    <small>
                      {camera.name} · {camera.zone || "Зона не указана"}
                    </small>
                  </div>
                  {uploads[camera.id] && (
                    <button
                      className="icon-button"
                      aria-label={`Убрать снимок ${camera.name}`}
                      onClick={() =>
                        setUploads((current) => {
                          URL.revokeObjectURL(current[camera.id].url);
                          return Object.fromEntries(
                            Object.entries(current).filter(
                              ([id]) => id !== camera.id,
                            ),
                          );
                        })
                      }
                    >
                      <IconX size={18} />
                    </button>
                  )}
                </div>
                <input
                  ref={(element) => {
                    inputs.current[camera.id] = element;
                  }}
                  className="visually-hidden"
                  type="file"
                  accept="image/jpeg,image/png"
                  onChange={(event) => {
                    const file = event.target.files?.[0];
                    if (file) assign(camera.id, file);
                    event.target.value = "";
                  }}
                />
                <button
                  type="button"
                  className={`dropzone ${uploads[camera.id] ? "filled" : ""}`}
                  aria-label={`Выбрать фото: ${camera.name}`}
                  onClick={() => inputs.current[camera.id]?.click()}
                  onDragOver={(event) => event.preventDefault()}
                  onDrop={(event) => {
                    event.preventDefault();
                    const file = event.dataTransfer.files?.[0];
                    if (file) assign(camera.id, file);
                  }}
                >
                  {uploads[camera.id] ? (
                    <>
                      <img
                        src={uploads[camera.id].url}
                        alt={`Снимок камеры ${index + 1} — ${camera.name}`}
                      />
                      <span className="replace-photo">Заменить фото</span>
                    </>
                  ) : (
                    <>
                      <IconCamera size={36} stroke={1.3} />
                      <strong>Перетащите фотографию</strong>
                      <span>или выберите файл</span>
                      <small>JPEG или PNG · до 20 МБ</small>
                    </>
                  )}
                </button>
                {uploads[camera.id] && (
                  <small className="file-name">{uploads[camera.id].name}</small>
                )}
              </section>
            ))}
          </div>
          {count > 0 && count < cams.length && (
            <p className="helper">
              Без фото:{" "}
              {cams
                .filter((camera) => !uploads[camera.id])
                .map((camera) => camera.name)
                .join(", ")}
              . Для этих зон результат может быть неполным.
            </p>
          )}
        </>
      )}
      {duplicate && (
        <div className="inline-note">
          <IconInfoCircle size={20} />
          <span>
            Проверка на это время уже есть. Выберите другое время или{" "}
            <button
              className="text-button"
              onClick={() => onOpenExisting(duplicate.id)}
            >
              откройте результат
            </button>
            .
          </span>
        </div>
      )}
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      <div className="snapshot-bottom">
        <button
          className="button"
          onClick={step === 1 ? onCancel : () => setStep(1)}
        >
          <IconArrowLeft size={18} />
          {step === 1 ? "Отмена" : "Назад"}
        </button>
        <button
          className="button primary"
          disabled={!date || !time || !!duplicate || (step === 2 && !count)}
          onClick={step === 1 ? () => setStep(2) : analyse}
        >
          {step === 1 ? "Загрузить свои фото" : "Запустить AI-анализ"}
          <IconArrowRight size={19} />
        </button>
      </div>
      {step === 2 && count > 0 && (
        <p className="fine-print">После запуска {count} фото будут сохранены и отправлены в GateLLM на анализ.</p>
      )}
    </section>
  );
}
