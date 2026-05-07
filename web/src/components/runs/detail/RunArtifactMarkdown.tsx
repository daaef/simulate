"use client";

import { memo } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

const REPORT_CHUNK_SIZE = 50000;

const MarkdownPane = memo(function MarkdownPane({ text }: { text: string }) {
  return <ReactMarkdown remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown>;
});

interface RunArtifactMarkdownProps {
  text: string | null;
  emptyMessage: string;
  chunkIndex?: number;
  onChunkChange?: (chunkIndex: number) => void;
}

export default function RunArtifactMarkdown({
  text,
  emptyMessage,
  chunkIndex = 0,
  onChunkChange,
}: RunArtifactMarkdownProps) {
  if (!text) {
    return <div className="muted">{emptyMessage}</div>;
  }

  const chunked = typeof onChunkChange === "function";
  const currentChunk = chunked ? chunkIndex : 0;
  const visibleText = chunked
    ? text.substring(currentChunk * REPORT_CHUNK_SIZE, (currentChunk + 1) * REPORT_CHUNK_SIZE)
    : text;
  const totalChunks = Math.ceil(text.length / REPORT_CHUNK_SIZE);

  return (
    <div className="artifact markdown-view">
      <MarkdownPane text={visibleText} />
      {chunked && text.length > REPORT_CHUNK_SIZE ? (
        <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 16, marginTop: 12 }}>
          <button onClick={() => onChunkChange?.(Math.max(0, currentChunk - 1))} disabled={currentChunk === 0} style={{ width: "auto" }} className="secondary">
            Previous
          </button>
          <span className="muted">Part {currentChunk + 1} of {totalChunks}</span>
          <button
            onClick={() => onChunkChange?.(currentChunk + 1)}
            disabled={(currentChunk + 1) * REPORT_CHUNK_SIZE >= text.length}
            style={{ width: "auto" }}
          >
            Next
          </button>
        </div>
      ) : null}
    </div>
  );
}
