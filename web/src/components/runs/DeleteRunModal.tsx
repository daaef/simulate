"use client";

import { useRef } from "react";
import type { RunRow } from "../../lib/api";
import { useFocusTrap } from "../../lib/useFocusTrap";

interface DeleteRunModalProps {
  run: RunRow;
  onConfirm: () => void;
  onCancel: () => void;
}

export default function DeleteRunModal({ run, onConfirm, onCancel }: DeleteRunModalProps) {
  const panelRef = useRef<HTMLDivElement>(null);
  useFocusTrap(true, panelRef);

  return (
    <div
      style={{
        position: "fixed",
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        backgroundColor: "rgba(0, 0, 0, 0.5)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 1000,
      }}
      role="presentation"
    >
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="delete-run-title"
        style={{
          backgroundColor: "var(--bg-secondary)",
          padding: "24px",
          borderRadius: "8px",
          width: "400px",
          border: "1px solid var(--border-primary)",
        }}
      >
        <h3 id="delete-run-title" style={{ margin: "0 0 12px 0", color: "var(--text-primary)" }}>
          Archive run #{run.id}?
        </h3>
        <p style={{ margin: "0 0 20px 0", color: "var(--text-secondary)", fontSize: "14px" }}>
          This will archive run #{run.id} — it will be hidden from the runs list but can be restored
          from the Archives page at any time.
        </p>
        <div style={{ display: "flex", gap: "12px" }}>
          <button
            type="button"
            onClick={onConfirm}
            style={{
              flex: 1,
              padding: "10px 16px",
              backgroundColor: "var(--method-delete-bg)",
              color: "var(--method-delete-text)",
              border: "1px solid var(--method-delete-border)",
              borderRadius: "6px",
              cursor: "pointer",
              fontWeight: 500,
            }}
          >
            Archive
          </button>
          <button
            type="button"
            onClick={onCancel}
            className="secondary"
            style={{
              flex: 1,
              padding: "10px 16px",
              borderRadius: "6px",
              cursor: "pointer",
              fontWeight: 500,
            }}
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}
