import { useEffect, useRef } from "react";
import { ArrowRight, X } from "lucide-react";
import { Link } from "react-router-dom";

export function NoticeDialog({ title, description, actionLabel, actionTo, onClose }) {
  const dialogRef = useRef(null);
  const closeRef = useRef(onClose);
  closeRef.current = onClose;

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return undefined;
    dialog.showModal();
    const handleClose = () => closeRef.current();
    dialog.addEventListener("close", handleClose);
    return () => dialog.removeEventListener("close", handleClose);
  }, []);

  return (
    <dialog
      className="notice-dialog"
      ref={dialogRef}
      onClick={(event) => {
        if (event.target === event.currentTarget) event.currentTarget.close();
      }}
    >
      <button
        className="dialog-close"
        type="button"
        aria-label="Close dialog"
        onClick={() => dialogRef.current?.close()}
      >
        <X size={18} />
      </button>
      <span className="eyebrow">MemoryBook</span>
      <h2>{title}</h2>
      <p>{description}</p>
      <div className="dialog-actions">
        <button
          className="button button-outline"
          type="button"
          onClick={() => dialogRef.current?.close()}
        >
          Not now
        </button>
        <Link
          className="button button-dark"
          to={actionTo}
          onClick={() => dialogRef.current?.close()}
        >
          {actionLabel} <ArrowRight size={16} />
        </Link>
      </div>
    </dialog>
  );
}
