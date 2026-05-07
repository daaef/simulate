"use client";

import type { RunRow } from "../../lib/api";

interface DeleteRunModalProps {
  run: RunRow;
  onConfirm: () => void;
  onCancel: () => void;
}

export default function DeleteRunModal({ run, onConfirm, onCancel }: DeleteRunModalProps) {
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
    >
      <div
        style={{
          backgroundColor: "var(--bg-secondary)",
          padding: "24px",
          borderRadius: "8px",
          width: "400px",
          border: "1px solid var(--border-primary)",
        }}
      >
        <h3 style={{ margin: "0 0 12px 0", color: "var(--text-primary)" }}>Confirm Delete</h3>
        <p style={{ margin: "0 0 20px 0", color: "var(--text-secondary)", fontSize: "14px" }}>
          Are you sure you want to delete run #{run.id}? This will permanently remove all associated files and cannot be undone.
        </p>
        <div style={{ display: "flex", gap: "12px" }}>
          <button
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
            Delete
          </button>
          <button
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
