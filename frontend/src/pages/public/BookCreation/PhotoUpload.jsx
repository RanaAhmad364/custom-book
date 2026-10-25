import { useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../../../features/auth/AuthContext.jsx";
import { useBookCreation } from "../../../features/bookCreation/BookCreationContext.jsx";
import { projectService } from "../../../services/projectService.js";
import { Camera, Check, CloudUpload, Image, LoaderCircle, RotateCcw, Trash2 } from "lucide-react";
import { CreationFooter, CreationHeading, CreationShell } from "./CreationShell.jsx";

const MAX_FILE_SIZE = 15 * 1024 * 1024;
const MAX_TOTAL_SIZE = 100 * 1024 * 1024;
const MAX_PHOTOS = 40;
const IMAGE_TYPES = new Set(["image/jpeg", "image/png", "image/webp"]);
const delay = (ms) => new Promise((resolve) => window.setTimeout(resolve, ms));

function readDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => typeof reader.result === "string" ? resolve(reader.result) : reject(new Error("We couldn’t read this image."));
    reader.onerror = () => reject(new Error("We couldn’t read this image. Try selecting it again."));
    reader.readAsDataURL(file);
  });
}

async function getImageQuality(file, preview) {
  try {
    const image = new window.Image();
    image.src = preview;
    await image.decode();
    const megapixels = (image.naturalWidth * image.naturalHeight) / 1_000_000;
    if (Math.min(image.naturalWidth, image.naturalHeight) < 900 || megapixels < 1) return { quality: "Low resolution", dimensions: `${image.naturalWidth} × ${image.naturalHeight}`, warning: true };
    if (megapixels < 4) return { quality: "Good for print", dimensions: `${image.naturalWidth} × ${image.naturalHeight}`, warning: false };
    return { quality: "High resolution", dimensions: `${image.naturalWidth} × ${image.naturalHeight}`, warning: false };
  } catch {
    return { quality: "Could not analyze", dimensions: "", warning: true };
  }
}

export default function PhotoUpload() {
  const inputRef = useRef(null);
  const fileById = useRef(new Map());
  const [dragging, setDragging] = useState(false);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState("");
  const { user } = useAuth();
  const { selections, addPhoto, updatePhoto, removePhoto, reset } = useBookCreation();
  const navigate = useNavigate();

  async function upload(file) {
    const id = `photo-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    fileById.current.set(id, file);
    const photo = { id, name: file.name, size: file.size, status: "uploading", progress: 0, preview: "", quality: "", dimensions: "", warning: false, retryable: true, error: "" };
    addPhoto(photo);
    if (!IMAGE_TYPES.has(file.type.toLowerCase())) {
      updatePhoto(id, { status: "error", retryable: false, error: "Choose an image file such as JPG, PNG, HEIC, or WebP." });
      return;
    }
    if (file.size > MAX_FILE_SIZE) {
      updatePhoto(id, { status: "error", retryable: false, error: "This image is larger than 15 MB. Choose a smaller image." });
      return;
    }
    if (file.size === 0) {
      updatePhoto(id, { status: "error", retryable: false, error: "This file is empty. Choose another image." });
      return;
    }
    try {
      for (let progress = 15; progress < 90; progress += 25) {
        await delay(100);
        updatePhoto(id, { progress });
      }
      const preview = await readDataUrl(file);
      const quality = await getImageQuality(file, preview);
      updatePhoto(id, { ...quality, preview, status: "ready", progress: 100 });
    } catch (failure) {
      updatePhoto(id, { status: "error", error: failure instanceof Error ? failure.message : "We couldn’t prepare this image." });
    }
  }

  function addFiles(fileList) {
    setError("");
    const incoming = Array.from(fileList ?? []);
    if (!incoming.length) return;
    const slots = MAX_PHOTOS - selections.photos.length;
    if (slots <= 0) {
      setError(`You can add up to ${MAX_PHOTOS} photos to this book.`);
      return;
    }
    const totalSelected = selections.photos.reduce((total, photo) => total + photo.size, 0);
    let remainingBytes = MAX_TOTAL_SIZE - totalSelected;
    const accepted = [];
    for (const file of incoming.slice(0, slots)) {
      if (file.size <= remainingBytes) {
        accepted.push(file);
        remainingBytes -= file.size;
      } else {
        setError(`Photo selection is limited to ${MAX_PHOTOS} images and 100 MB total. Remove a photo or choose a smaller file.`);
      }
    }
    if (incoming.length > slots) setError(`Only the first ${slots} photo${slots === 1 ? "" : "s"} were added. You can add up to ${MAX_PHOTOS}.`);
    accepted.forEach((file) => { void upload(file); });
  }

  function retry(photo) {
    const file = fileById.current.get(photo.id);
    if (!file) {
      updatePhoto(photo.id, { status: "error", error: "The original file is no longer available. Please select the photo again." });
      return;
    }
    updatePhoto(photo.id, { status: "uploading", progress: 0, error: "" });
    void processRetry(photo.id, file);
  }

  async function processRetry(id, file) {
    try {
      for (let progress = 20; progress < 90; progress += 25) {
        await delay(100);
        updatePhoto(id, { progress });
      }
      const preview = await readDataUrl(file);
      const quality = await getImageQuality(file, preview);
      updatePhoto(id, { ...quality, preview, status: "ready", progress: 100 });
    } catch (failure) {
      updatePhoto(id, { status: "error", error: failure instanceof Error ? failure.message : "We couldn’t prepare this image." });
    }
  }

  async function startDesigning() {
    setError("");
    if (!selections.title.trim()) {
      setError("Add a title for your book in the setup step before continuing.");
      return;
    }
    if (!user?.email) {
      navigate("/login", { state: { from: { pathname: "/create/photos" } } });
      return;
    }
    setCreating(true);
    try {
      const project = await projectService.createProject(user.email, {
        startingOption: selections.startingOption,
        title: selections.title,
        bookSize: selections.bookSize,
        pageCount: selections.pageCount,
        coverType: selections.coverType,
        startingLayout: selections.startingLayout,
        book: selections.selectedBook,
        template: selections.selectedTemplate,
        photos: selections.photos.filter((photo) => photo.status === "ready").map(({ id, name, mimeType, size, preview, quality, dimensions, warning }) => ({
          id,
          name,
          mimeType,
          size,
          preview,
          quality,
          dimensions,
          warning,
          file: fileById.current.get(id),
        })),
      });
      reset();
      navigate(`/create/design/${project.id}`, { state: { project } });
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "We couldn’t create your book. Please try again.");
    } finally {
      setCreating(false);
    }
  }

  return <CreationShell current="/create/photos">
    <CreationHeading eyebrow="Gather your moments" title={<>Bring your photos<br /><em>into the story.</em></>} description="Add photos now or continue with an empty book. You can always bring in more moments later." />
    <div className="creation-upload-preview-note"><CloudUpload size={15} /> Photos upload securely to your project when you start designing.</div>
    <div className={`creation-dropzone${dragging ? " is-dragging" : ""}`} role="button" tabIndex={0} onClick={() => inputRef.current?.click()} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); inputRef.current?.click(); } }} onDragOver={(event) => { event.preventDefault(); setDragging(true); }} onDragLeave={() => setDragging(false)} onDrop={(event) => { event.preventDefault(); setDragging(false); addFiles(event.dataTransfer.files); }}>
      <input ref={inputRef} className="creation-visually-hidden" type="file" accept="image/jpeg,image/png,image/webp" multiple onChange={(event) => { addFiles(event.target.files); event.target.value = ""; }} />
      <span className="creation-drop-icon"><CloudUpload size={25} /></span><strong>Drop your photos here</strong><p>or choose from your device</p><span className="button button-outline">Choose photos</span><small>JPG, PNG, HEIC, WebP · up to 15 MB each · up to {MAX_PHOTOS} photos</small>
    </div>
    {error ? <p className="creation-form-error" role="alert">{error}</p> : null}
    <section className="creation-photo-section">
      <div className="creation-photo-section-heading"><div><span className="eyebrow">Your selection</span><h2>{selections.photos.length ? `${selections.photos.length} photo${selections.photos.length === 1 ? "" : "s"}` : "Your photo tray"}</h2></div>{selections.photos.length ? <button type="button" onClick={() => inputRef.current?.click()}><Image size={15} /> Add more</button> : null}</div>
      {selections.photos.length ? <div className="creation-photo-grid">{selections.photos.map((photo) => <article className="creation-photo-card" key={photo.id}>
        <div className="creation-photo-thumb">{photo.preview ? <img src={photo.preview} alt="" /> : <span><Image size={23} /></span>}
          {photo.status === "uploading" ? <div className="creation-photo-progress"><span style={{ width: `${photo.progress}%` }} /></div> : null}
          <button type="button" aria-label={`Remove ${photo.name}`} onClick={() => { fileById.current.delete(photo.id); removePhoto(photo.id); }}><Trash2 size={14} /></button>
        </div>
        <div className="creation-photo-info"><strong title={photo.name}>{photo.name}</strong>{photo.status === "uploading" ? <small><LoaderCircle size={12} /> Preparing image · {photo.progress}%</small> : photo.status === "error" ? <><small className="is-error">{photo.error}</small>{photo.retryable ? <button type="button" onClick={() => retry(photo)}><RotateCcw size={12} /> Retry</button> : null}</> : <small className={photo.warning ? "is-warning" : "is-good"}><Check size={12} /> {photo.quality}{photo.dimensions ? ` · ${photo.dimensions}` : ""}</small>}</div>
      </article>)}</div> : <div className="creation-photo-empty"><Camera size={18} /><span>There are no photos yet. Add a few favorites or continue to create an empty book.</span></div>}
    </section>
    <CreationFooter backTo="/create/setup" backLabel="Back to book setup" nextLabel={user?.email ? "Start designing" : "Sign in to save your book"} onNext={startDesigning} busy={creating} disabled={selections.photos.some((photo) => photo.status === "uploading")} />
  </CreationShell>;
}
