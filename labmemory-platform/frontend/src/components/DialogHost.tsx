import { useEffect, type ReactElement } from "react";
import { useDialog, type DialogVariant } from "../dialog";

const ICONS: Record<DialogVariant, ReactElement> = {
  info: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="9" />
      <path d="M12 8v0M12 12v4" />
    </svg>
  ),
  success: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
      <path d="M20 6L9 17l-5-5" />
    </svg>
  ),
  warning: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M10.29 3.86L1.82 18a2 2 0 002 3h16.36a2 2 0 002-3L13.71 3.86a2 2 0 00-3.42 0z" />
      <path d="M12 9v4M12 17v0" />
    </svg>
  ),
  error: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="9" />
      <path d="M15 9l-6 6M9 9l6 6" />
    </svg>
  ),
};

const VARIANT_LABEL: Record<DialogVariant, string> = {
  info: "提示",
  success: "操作成功",
  warning: "注意",
  error: "出错了",
};

export default function DialogHost() {
  const { open, kind, options, close } = useDialog();

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") close(false);
      else if (e.key === "Enter" && kind === "alert") close(true);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, kind, close]);

  if (!open) return null;

  const variant = options.variant || "info";
  const title = options.title || (kind === "alert" ? VARIANT_LABEL[variant] : "请确认");
  const isConfirm = kind === "confirm";
  const confirmText = options.confirmText || (isConfirm ? "确定" : "知道了");
  const cancelText = options.cancelText || "取消";

  return (
    <div className="dialog-backdrop" onClick={() => close(false)}>
      <div
        className={`dialog dialog-${variant}${options.danger ? " dialog-danger" : ""}`}
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
      >
        <div className="dialog-icon">{ICONS[variant]}</div>
        <div className="dialog-body">
          <h3 className="dialog-title">{title}</h3>
          <p className="dialog-message">{options.message}</p>
        </div>
        <div className="dialog-actions">
          {isConfirm && (
            <button className="btn" onClick={() => close(false)}>
              {cancelText}
            </button>
          )}
          <button
            className={`btn ${options.danger ? "danger" : "primary"}`}
            onClick={() => close(true)}
            autoFocus
          >
            {confirmText}
          </button>
        </div>
      </div>
    </div>
  );
}
