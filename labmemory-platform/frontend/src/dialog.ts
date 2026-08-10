import { create } from "zustand";

export type DialogVariant = "info" | "success" | "warning" | "error";
export type DialogKind = "alert" | "confirm";

export interface DialogOptions {
  title?: string;
  message: string;
  variant?: DialogVariant;
  danger?: boolean;
  confirmText?: string;
  cancelText?: string;
}

interface DialogState {
  open: boolean;
  kind: DialogKind;
  options: DialogOptions;
  resolve?: (value: boolean) => void;
  close: (value: boolean) => void;
}

const DEFAULT_OPTIONS: DialogOptions = { message: "" };

export const useDialog = create<DialogState>((set, get) => ({
  open: false,
  kind: "alert",
  options: DEFAULT_OPTIONS,
  resolve: undefined,
  close: (value: boolean) => {
    const resolve = get().resolve;
    set({ open: false, kind: "alert", options: DEFAULT_OPTIONS, resolve: undefined });
    resolve?.(value);
  },
}));

function openDialog(kind: DialogKind, options: DialogOptions | string): Promise<boolean> {
  const opts: DialogOptions = typeof options === "string" ? { message: options } : options;
  return new Promise<boolean>((resolve) => {
    useDialog.setState({ open: true, kind, options: opts, resolve });
  });
}

export const dialog = {
  alert(options: DialogOptions | string): Promise<void> {
    return openDialog("alert", options).then(() => undefined);
  },
  confirm(options: DialogOptions | string): Promise<boolean> {
    return openDialog("confirm", options);
  },
};
