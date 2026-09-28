class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function request(path, options = {}) {
  let response;
  const isForm = options.body instanceof FormData;
  try {
    response = await fetch(path, {
      credentials: "include",
      ...options,
      headers: {
        ...(options.body && !isForm
          ? { "Content-Type": "application/json" }
          : {}),
        ...options.headers,
      },
    });
  } catch {
    throw new ApiError("Сервис временно недоступен", 0);
  }
  if (response.status === 204) return null;
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    throw new ApiError(
      body?.detail || "Не удалось выполнить запрос",
      response.status,
    );
  }
  return body;
}

export const authApi = {
  me: () => request("/auth/me"),
  login: (identifier, password) =>
    request("/auth/login", {
      method: "POST",
      body: JSON.stringify({ identifier, password }),
    }),
  register: (email, password) =>
    request("/auth/register", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),
  logout: () => request("/auth/logout", { method: "POST" }),
};

export const objectApi = {
  list: () => request("/objects"),
  listDetails: async () => {
    const rows = await request("/objects");
    return Promise.all(
      rows.map(async (item) => {
        const [details, snapshots, inspections] = await Promise.all([
          request(`/objects/${item.id}`),
          request(`/objects/${item.id}/snapshots`),
          request(`/objects/${item.id}/inspections`),
        ]);
        return { ...details, snapshots, inspections };
      }),
    );
  },
  get: (id) => request(`/objects/${id}`),
  create: (payload) =>
    request("/objects", { method: "POST", body: JSON.stringify(payload) }),
  update: (id, payload) =>
    request(`/objects/${id}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),
  syncCameras: (id, cameras) =>
    request(`/objects/${id}/cameras`, {
      method: "PUT",
      body: JSON.stringify(cameras),
    }),
  updateCamera: (id, payload) =>
    request(`/cameras/${id}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),
  incrementFovRevision: (id) =>
    request(`/cameras/${id}/fov-revision`, { method: "POST" }),
  syncPlan: (id, plan) =>
    request(`/objects/${id}/plan`, {
      method: "PUT",
      body: JSON.stringify(plan),
    }),
  updateSchedule: (id, schedule) =>
    request(`/objects/${id}/schedule`, {
      method: "PUT",
      body: JSON.stringify(schedule),
    }),
  stageDirectory: (objectType) =>
    request(`/stage-directory?object_type=${encodeURIComponent(objectType)}`),
};

export const snapshotApi = {
  list: (objectId, params = {}) => {
    const query = new URLSearchParams(
      Object.entries(params).filter(([, value]) => value),
    );
    return request(
      `/objects/${objectId}/snapshots${query.size ? `?${query}` : ""}`,
    );
  },
  history: (objectId, params = {}) => {
    const query = new URLSearchParams(
      Object.entries(params).filter(([, value]) => value),
    );
    return request(
      `/objects/${objectId}/history${query.size ? `?${query}` : ""}`,
    );
  },
  create: (objectId, observedDate, observedTime, source = "manual") =>
    request(`/objects/${objectId}/snapshots`, {
      method: "POST",
      body: JSON.stringify({
        observed_date: observedDate,
        observed_time: observedTime,
        source,
      }),
    }),
  upload: (snapshotId, cameraId, file, source = "manual") => {
    const body = new FormData();
    body.append("camera_id", cameraId);
    body.append("source", source);
    body.append("file", file, file.name);
    return request(`/snapshots/${snapshotId}/images`, {
      method: "POST",
      body,
    });
  },
  removeImage: (imageId) =>
    request(`/snapshot-images/${imageId}`, { method: "DELETE" }),
  analyze: (snapshotId, idempotencyKey) =>
    request(`/snapshots/${snapshotId}/analyze`, {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
    }),
  get: (snapshotId) => request(`/snapshots/${snapshotId}`),
  remove: (snapshotId) =>
    request(`/snapshots/${snapshotId}`, { method: "DELETE" }),
};

export const inspectionApi = {
  list: (objectId, params = {}) => {
    const query = new URLSearchParams(
      Object.entries(params).filter(([, value]) => value),
    );
    return request(
      `/objects/${objectId}/inspections${query.size ? `?${query}` : ""}`,
    );
  },
  create: (objectId, payload, files = []) => {
    const body = new FormData();
    body.append("plan_item_id", payload.planItemId);
    body.append("observed_date", payload.observedDate);
    if (payload.validUntil) body.append("valid_until", payload.validUntil);
    body.append("verdict", payload.verdict);
    body.append("author", payload.author);
    body.append("role", payload.role || "");
    body.append("comment", payload.comment);
    files.forEach((file) => body.append("files", file, file.name));
    return request(`/objects/${objectId}/inspections`, {
      method: "POST",
      body,
    });
  },
  day: (objectId, date) => request(`/objects/${objectId}/days/${date}`),
};

export const comparisonApi = {
  list: (objectId) => request(`/objects/${objectId}/comparisons`),
  create: (objectId, firstImageId, secondImageId) =>
    request(`/objects/${objectId}/comparisons`, {
      method: "POST",
      body: JSON.stringify({
        first_image_id: firstImageId,
        second_image_id: secondImageId,
      }),
    }),
  movement: (objectId, date) =>
    request(`/objects/${objectId}/movement?date=${encodeURIComponent(date)}`),
};

export { ApiError };
