import { apiRequest } from "./apiClient.js";

const projectVersions = new Map();

function ownerKey(owner) {
  const normalized = owner?.trim().toLowerCase();
  if (!normalized) throw new Error("Sign in is required to save a book project.");
  return normalized;
}

function versionKey(owner, projectId) {
  return `${ownerKey(owner)}::${projectId}`;
}

function rememberVersion(owner, project) {
  if (Number.isInteger(project?.version)) projectVersions.set(versionKey(owner, project.id), project.version);
}

function projectShape(owner, record) {
  rememberVersion(owner, record);
  const document = record.document;
  const book = document?.book ?? {};
  const template = book.template ?? {};
  const firstImage = document?.assets?.find((asset) => asset.src)?.src;
  return {
    ...record,
    owner: ownerKey(owner),
    image: firstImage || record.image || template.image || book.image || "",
    category: record.category || template.category || "Custom",
    pages: record.pageCount ?? book.pageCount ?? 0,
    progress: record.status === "completed" ? 100 : document?.pages?.length ? 12 : 5,
    updated: record.updatedAt ? new Date(record.updatedAt).toLocaleDateString() : "Just now",
    createdAt: record.createdAt,
  };
}

function projectPath(projectId) {
  return `/projects/${encodeURIComponent(projectId)}`;
}

function databaseId(value) {
  return typeof value === "string" && /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(value)
    ? value
    : undefined;
}

function expectedVersion(owner, projectId) {
  const version = projectVersions.get(versionKey(owner, projectId));
  if (!Number.isInteger(version)) throw new Error("The project version is unavailable. Reload the project before saving.");
  return `"${version}"`;
}

function buildProjectDocument(project, selections, uploadedAssets = []) {
  const pageCount = Number(selections.pageCount) || 24;
  const selectedTemplate = selections.template?.designTemplateId !== undefined
    ? selections.template.designTemplateId
      ? { ...selections.template, id: selections.template.designTemplateId }
      : null
    : selections.template;
  const pages = [
    { id: crypto.randomUUID(), type: "cover", label: "Cover", background: { color: "#e8ece5" }, layout: "cover", elements: [] },
    ...Array.from({ length: pageCount }, (_, index) => ({
      id: crypto.randomUUID(),
      type: "page",
      label: `Page ${index + 1}`,
      background: { color: "#fffdf9" },
      layout: "blank",
      elements: [],
    })),
  ];
  const size = selections.bookSize === "11 × 8.5 in"
    ? { width: 11, height: 8.5 }
    : selections.bookSize === "8 × 8 in"
      ? { width: 8, height: 8 }
      : { width: 10, height: 10 };
  const now = new Date().toISOString();
  return {
    schemaVersion: 1,
    metadata: { id: project.id, owner: project.owner, title: project.title, createdAt: project.createdAt, updatedAt: now },
    book: {
      size,
      pageCount,
      coverType: selections.coverType,
      startingLayout: selections.startingLayout,
      startingOption: selections.startingOption,
      template: selectedTemplate ? {
        id: selectedTemplate.id,
        title: selectedTemplate.title ?? selectedTemplate.name,
        category: selectedTemplate.category,
        image: selectedTemplate.image ?? selectedTemplate.previewImage,
      } : null,
    },
    pageOrder: pages.map((page) => page.id),
    pages,
    assets: uploadedAssets,
    styles: { fontFamily: "DM Sans", color: "#1d2824", background: "#fffdf9" },
    cover: {
      pageId: pages[0].id,
      title: project.title,
      finish: selections.coverType,
      design: {
        bleedInches: 0.125,
        front: {
          title: project.title, subtitle: "", backgroundColor: "#e8ece5", textColor: "#20352d",
          fontFamily: "Georgia", layout: "center", photoAssetId: null,
        },
        spine: { title: project.title, backgroundColor: "#e8ece5", textColor: "#20352d", fontFamily: "Georgia" },
        back: { title: project.title, description: "", backgroundColor: "#f4eee5", textColor: "#20352d", fontFamily: "Georgia" },
      },
    },
  };
}

function recoveryKey(owner, projectId) {
  return `memorybook-recovery:${versionKey(owner, projectId)}`;
}

function responseProject(response, owner) {
  const project = response.data?.project;
  if (!project) throw new Error("The project service returned an invalid response.");
  return projectShape(owner, project);
}

async function upload(owner, projectId, file, assetId) {
  const body = new FormData();
  body.append("file", file, file.name);
  if (assetId) body.append("assetId", assetId);
  const response = await apiRequest(`${projectPath(projectId)}/assets`, {
    method: "POST",
    body,
    headers: { "If-Match": expectedVersion(owner, projectId) },
  });
  if (Number.isInteger(response.data?.projectVersion)) {
    projectVersions.set(versionKey(owner, projectId), response.data.projectVersion);
  }
  if (!response.data?.asset) throw new Error("The asset service returned an invalid response.");
  return response.data.asset;
}

export const projectService = {
  async createProject(owner, selections) {
    const key = ownerKey(owner);
    if (!selections?.title?.trim()) throw new Error("Add a title before creating your book.");
    const { data } = await apiRequest("/projects", {
      method: "POST",
      body: {
        title: selections.title.trim(),
        pageCount: Number(selections.pageCount) || 24,
        productId: databaseId(selections.book?.id),
        templateId: databaseId(
          selections.template?.designTemplateId !== undefined
            ? selections.template.designTemplateId
            : selections.template?.id,
        ),
      },
    });
    let project = responseProject({ data }, key);
    const uploadedAssets = [];
    for (const photo of selections.photos ?? []) {
      if (!photo.file) throw new Error(`The original image for "${photo.name}" is unavailable. Please select it again.`);
      const asset = await upload(key, project.id, photo.file, photo.id);
      uploadedAssets.push(asset);
    }
    const document = project.document
      ? {
        ...structuredClone(project.document),
        metadata: {
          ...project.document.metadata,
          title: project.title,
          updatedAt: new Date().toISOString(),
        },
        assets: [...project.document.assets, ...uploadedAssets],
      }
      : buildProjectDocument(project, selections, uploadedAssets);
    const saved = await apiRequest(projectPath(project.id), {
      method: "PATCH",
      body: { title: document.metadata.title, pageCount: document.book.pageCount, document },
      headers: { "If-Match": expectedVersion(key, project.id) },
    });
    project = responseProject(saved, key);
    return project;
  },

  async listProjects(owner, filters = {}) {
    const key = ownerKey(owner);
    const params = new URLSearchParams();
    for (const [name, value] of Object.entries(filters)) {
      if (value !== undefined && value !== null && value !== "") params.set(name, String(value));
    }
    const suffix = params.size ? `?${params.toString()}` : "";
    const { data } = await apiRequest(`/projects${suffix}`);
    if (!Array.isArray(data?.items)) throw new Error("The project service returned an invalid project list.");
    return data.items.map((item) => projectShape(key, item));
  },

  async getProject(owner, projectId) {
    const key = ownerKey(owner);
    const { data } = await apiRequest(projectPath(projectId));
    return responseProject({ data }, key);
  },

  async saveDocument(owner, projectId, document) {
    const key = ownerKey(owner);
    if (document.schemaVersion !== 1 || document.metadata?.id !== projectId || document.metadata?.owner?.toLowerCase() !== key) {
      throw new Error("The project document is invalid or belongs to another account.");
    }
    const { data } = await apiRequest(projectPath(projectId), {
      method: "PATCH",
      body: { title: document.metadata.title, pageCount: document.book.pageCount, document },
      headers: { "If-Match": expectedVersion(key, projectId) },
    });
    return responseProject({ data }, key);
  },

  saveRecovery(owner, projectId, document) {
    const key = ownerKey(owner);
    const recovery = {
      ...document,
      assets: document.assets.map(({ src, ...asset }) => asset),
      pages: document.pages.map((page) => ({
        ...page,
        elements: page.elements.map(({ src, ...element }) => element),
      })),
    };
    try {
      localStorage.setItem(recoveryKey(key, projectId), JSON.stringify(recovery));
    } catch (failure) {
      throw new Error(failure instanceof Error ? `Could not keep a local recovery copy: ${failure.message}` : "Could not keep a local recovery copy.");
    }
  },

  getRecovery(owner, projectId) {
    try {
      const value = localStorage.getItem(recoveryKey(owner, projectId));
      return value ? JSON.parse(value) : null;
    } catch (failure) {
      throw new Error(failure instanceof Error ? `Could not read the local recovery copy: ${failure.message}` : "Could not read the local recovery copy.");
    }
  },

  clearRecovery(owner, projectId) {
    localStorage.removeItem(recoveryKey(owner, projectId));
  },

  async updateProject(owner, projectId, changes) {
    const key = ownerKey(owner);
    const body = typeof changes === "string" ? { title: changes } : changes;
    const { data } = await apiRequest(projectPath(projectId), {
      method: "PATCH",
      body,
      headers: { "If-Match": expectedVersion(key, projectId) },
    });
    return responseProject({ data }, key);
  },

  async deleteProject(owner, projectId) {
    const key = ownerKey(owner);
    await apiRequest(projectPath(projectId), {
      method: "DELETE",
      headers: { "If-Match": expectedVersion(key, projectId) },
    });
    projectVersions.delete(versionKey(key, projectId));
  },

  async duplicateProject(owner, projectId) {
    const key = ownerKey(owner);
    const { data } = await apiRequest(`${projectPath(projectId)}/duplicate`, { method: "POST" });
    return responseProject({ data }, key);
  },

  async uploadAsset(owner, projectId, file) {
    return upload(ownerKey(owner), projectId, file);
  },

  async listAssets(owner, projectId) {
    ownerKey(owner);
    const { data } = await apiRequest(`${projectPath(projectId)}/assets`);
    return data.items;
  },

  async deleteAsset(owner, projectId, assetId) {
    const key = ownerKey(owner);
    const { data } = await apiRequest(`${projectPath(projectId)}/assets/${encodeURIComponent(assetId)}`, {
      method: "DELETE",
      headers: { "If-Match": expectedVersion(key, projectId) },
    });
    if (Number.isInteger(data?.projectVersion)) projectVersions.set(versionKey(key, projectId), data.projectVersion);
  },

  async createPage(owner, projectId, page) {
    return this.savePage(owner, projectId, `/pages`, "POST", page);
  },

  async updatePage(owner, projectId, pageId, page) {
    return this.savePage(owner, projectId, `/pages/${encodeURIComponent(pageId)}`, "PATCH", page);
  },

  async savePage(owner, projectId, suffix, method, page) {
    const key = ownerKey(owner);
    const { data } = await apiRequest(`${projectPath(projectId)}${suffix}`, {
      method,
      body: page,
      headers: { "If-Match": expectedVersion(key, projectId) },
    });
    return responseProject({ data }, key);
  },

  async deletePage(owner, projectId, pageId) {
    const key = ownerKey(owner);
    const { data } = await apiRequest(`${projectPath(projectId)}/pages/${encodeURIComponent(pageId)}`, {
      method: "DELETE",
      headers: { "If-Match": expectedVersion(key, projectId) },
    });
    return responseProject({ data }, key);
  },

  async createRevision(owner, projectId) {
    const key = ownerKey(owner);
    const { data } = await apiRequest(`${projectPath(projectId)}/revisions`, {
      method: "POST",
      headers: { "If-Match": expectedVersion(key, projectId) },
    });
    return data.revision;
  },

  async getRevision(owner, projectId, revisionId) {
    ownerKey(owner);
    const { data } = await apiRequest(`${projectPath(projectId)}/revisions/${encodeURIComponent(revisionId)}`);
    return data.revision;
  },

  async restoreRevision(owner, projectId, revisionId) {
    const key = ownerKey(owner);
    const { data } = await apiRequest(`${projectPath(projectId)}/revisions/${encodeURIComponent(revisionId)}/restore`, {
      method: "POST",
      headers: { "If-Match": expectedVersion(key, projectId) },
    });
    return responseProject({ data }, key);
  },
};
