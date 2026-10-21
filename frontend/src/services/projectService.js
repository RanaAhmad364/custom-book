const DATABASE_NAME = "memorybook-projects";
const DATABASE_VERSION = 1;
const STORE_NAME = "projects";
const projectsByOwner = new Map();
let databasePromise;
let nextProjectNumber = 1;

function ownerKey(owner) {
  const normalized = owner?.trim().toLowerCase();
  if (!normalized) throw new Error("Sign in is required to save a book project.");
  return normalized;
}

function documentPages(selections) {
  const pageCount = Number(selections.pageCount) || 24;
  const coverId = crypto.randomUUID();
  return [
    { id: coverId, type: "cover", label: "Cover", background: { color: "#e8ece5" }, layout: "cover", elements: [] },
    ...Array.from({ length: pageCount }, (_, index) => ({
      id: crypto.randomUUID(),
      type: "page",
      label: `Page ${index + 1}`,
      background: { color: "#fffdf9" },
      layout: "blank",
      elements: [],
    })),
  ];
}

function createProjectDocument(project, selections) {
  const size = selections.bookSize === "11 × 8.5 in"
    ? { width: 11, height: 8.5 }
    : selections.bookSize === "8 × 8 in"
      ? { width: 8, height: 8 }
      : { width: 10, height: 10 };
  const pages = documentPages(selections);
  return {
    schemaVersion: 1,
    metadata: {
      id: project.id,
      owner: project.owner,
      title: project.title,
      createdAt: project.createdAt,
      updatedAt: project.createdAt,
    },
    book: {
      size,
      pageCount: Number(selections.pageCount) || 24,
      coverType: selections.coverType,
      startingLayout: selections.startingLayout,
      startingOption: selections.startingOption,
      template: selections.template ? {
        id: selections.template.id,
        title: selections.template.title,
        category: selections.template.category,
        image: selections.template.image,
      } : null,
    },
    pageOrder: pages.map((page) => page.id),
    pages,
    assets: (selections.photos ?? []).map((photo) => ({
      id: photo.id,
      name: photo.name,
      mimeType: photo.mimeType ?? "image/jpeg",
      src: photo.preview,
      width: photo.width ?? null,
      height: photo.height ?? null,
    })),
    styles: { fontFamily: "DM Sans", color: "#1d2824", background: "#fffdf9" },
    cover: {
      pageId: pages[0].id,
      title: project.title,
      finish: selections.coverType,
      design: {
        bleedInches: 0.125,
        front: {
          title: project.title,
          subtitle: "",
          backgroundColor: "#e8ece5",
          textColor: "#20352d",
          fontFamily: "Georgia",
          layout: "center",
          photoAssetId: null,
        },
        spine: { title: project.title, backgroundColor: "#e8ece5", textColor: "#20352d", fontFamily: "Georgia" },
        back: { title: project.title, description: "", backgroundColor: "#f4eee5", textColor: "#20352d", fontFamily: "Georgia" },
      },
    },
  };
}

function requestResult(request) {
  return new Promise((resolve, reject) => {
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error ?? new Error("Could not access saved projects."));
  });
}

function openDatabase() {
  if (databasePromise) return databasePromise;
  databasePromise = new Promise((resolve, reject) => {
    if (!("indexedDB" in globalThis)) {
      reject(new Error("This browser does not support local project storage."));
      return;
    }
    const request = indexedDB.open(DATABASE_NAME, DATABASE_VERSION);
    request.onupgradeneeded = () => {
      const database = request.result;
      if (!database.objectStoreNames.contains(STORE_NAME)) {
        const store = database.createObjectStore(STORE_NAME, { keyPath: "key" });
        store.createIndex("owner", "owner", { unique: false });
      }
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error ?? new Error("Could not open local project storage."));
    request.onblocked = () => reject(new Error("Project storage is blocked by another open MemoryBook tab."));
  });
  return databasePromise;
}

async function storeProject(project) {
  const database = await openDatabase();
  const transaction = database.transaction(STORE_NAME, "readwrite");
  const completion = new Promise((resolve, reject) => {
    transaction.oncomplete = resolve;
    transaction.onerror = () => reject(transaction.error ?? new Error("Could not save the project locally."));
    transaction.onabort = () => reject(transaction.error ?? new Error("The local project save was cancelled."));
  });
  transaction.objectStore(STORE_NAME).put({ ...project, key: `${project.owner}::${project.id}` });
  await completion;
  const ownerProjects = projectsByOwner.get(project.owner) ?? [];
  projectsByOwner.set(project.owner, [project, ...ownerProjects.filter((item) => item.id !== project.id)]);
}

async function readProject(owner, projectId) {
  const database = await openDatabase();
  const record = await requestResult(database.transaction(STORE_NAME).objectStore(STORE_NAME).get(`${owner}::${projectId}`));
  if (!record) return null;
  const { key, ...project } = record;
  return project;
}

export const projectService = {
  async createProject(owner, selections) {
    const key = ownerKey(owner);
    if (!selections?.title?.trim()) throw new Error("Add a title before creating your book.");
    await new Promise((resolve) => window.setTimeout(resolve, 180));
    const project = {
      ...selections,
      id: `created-${Date.now()}-${nextProjectNumber++}`,
      owner: key,
      title: selections.title.trim(),
      status: "draft",
      progress: selections.photos?.length ? 12 : 5,
      updated: "Just now",
      createdAt: new Date().toISOString(),
      image: selections.photos?.[0]?.preview || selections.template?.image || selections.book?.image || "https://images.unsplash.com/photo-1507842217343-583bb7270b66?auto=format&fit=crop&w=900&q=85",
      category: selections.template?.category || "Custom",
      pages: `${selections.pageCount} pages`,
    };
    project.document = createProjectDocument(project, selections);
    await storeProject(project);
    return project;
  },

  async listProjects(owner) {
    const key = ownerKey(owner);
    const database = await openDatabase();
    const records = await requestResult(database.transaction(STORE_NAME).objectStore(STORE_NAME).index("owner").getAll(key));
    const projects = records.map(({ key: recordKey, ...project }) => project);
    projectsByOwner.set(key, projects);
    return projects;
  },

  async getProject(owner, projectId) {
    const key = ownerKey(owner);
    const cached = projectsByOwner.get(key)?.find((project) => project.id === projectId);
    return cached ?? readProject(key, projectId);
  },

  async saveDocument(owner, projectId, document) {
    const key = ownerKey(owner);
    const project = await readProject(key, projectId);
    if (!project) throw new Error("This project could not be found in your local workspace.");
    if (document.schemaVersion !== 1 || document.metadata?.id !== projectId || document.metadata?.owner !== key) {
      throw new Error("The project document is invalid or belongs to another account.");
    }
    const saved = {
      ...project,
      title: document.metadata.title,
      document,
      updated: "Just now",
      pages: `${document.book.pageCount} pages`,
      image: document.assets.find((asset) => asset.id === document.pages[0]?.elements?.find((element) => element.type === "image")?.assetId)?.src ?? project.image,
    };
    await storeProject(saved);
    return saved;
  },

  saveRecovery(owner, projectId, document) {
    const key = `${ownerKey(owner)}::${projectId}`;
    const recovery = {
      ...document,
      assets: document.assets.map(({ src, ...asset }) => asset),
      pages: document.pages.map((page) => ({
        ...page,
        elements: page.elements.map(({ src, ...element }) => element),
      })),
    };
    try {
      localStorage.setItem(`memorybook-recovery:${key}`, JSON.stringify(recovery));
    } catch (failure) {
      throw new Error(failure instanceof Error ? `Could not keep a local recovery copy: ${failure.message}` : "Could not keep a local recovery copy.");
    }
  },

  getRecovery(owner, projectId) {
    const key = `${ownerKey(owner)}::${projectId}`;
    try {
      const value = localStorage.getItem(`memorybook-recovery:${key}`);
      return value ? JSON.parse(value) : null;
    } catch (failure) {
      throw new Error(failure instanceof Error ? `Could not read the local recovery copy: ${failure.message}` : "Could not read the local recovery copy.");
    }
  },

  clearRecovery(owner, projectId) {
    const key = `${ownerKey(owner)}::${projectId}`;
    localStorage.removeItem(`memorybook-recovery:${key}`);
  },

  async updateProject(owner, projectId, changes) {
    const project = await this.getProject(owner, projectId);
    if (!project) return null;
    const updated = { ...project, ...changes };
    if (updated.document && changes.title) {
      updated.document = { ...updated.document, metadata: { ...updated.document.metadata, title: changes.title } };
    }
    await storeProject(updated);
    return updated;
  },

  async deleteProject(owner, projectId) {
    const key = ownerKey(owner);
    const database = await openDatabase();
    const transaction = database.transaction(STORE_NAME, "readwrite");
    const completion = new Promise((resolve, reject) => {
      transaction.oncomplete = resolve;
      transaction.onerror = () => reject(transaction.error ?? new Error("Could not remove the project."));
      transaction.onabort = () => reject(transaction.error ?? new Error("Project deletion was cancelled."));
    });
    transaction.objectStore(STORE_NAME).delete(`${key}::${projectId}`);
    await completion;
    projectsByOwner.set(key, (projectsByOwner.get(key) ?? []).filter((project) => project.id !== projectId));
  },

  async duplicateProject(owner, projectId) {
    const project = await this.getProject(owner, projectId);
    if (!project) return null;
    const key = ownerKey(owner);
    const id = `created-${Date.now()}-${nextProjectNumber++}`;
    const copy = {
      ...project,
      id,
      title: `${project.title} (copy)`,
      createdAt: new Date().toISOString(),
      updated: "Just now",
      document: {
        ...project.document,
        metadata: { ...project.document.metadata, id, title: `${project.title} (copy)`, createdAt: new Date().toISOString() },
        pageOrder: project.document.pages.map(() => crypto.randomUUID()),
        pages: project.document.pages.map((page) => ({ ...page, id: crypto.randomUUID(), elements: page.elements.map((element) => ({ ...element, id: crypto.randomUUID() })) })),
      },
    };
    copy.document.pageOrder = copy.document.pages.map((page) => page.id);
    await storeProject({ ...copy, owner: key });
    return copy;
  },
};
