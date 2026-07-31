import { useState } from "react";
import type { ChangeEvent, FormEvent } from "react";

interface UploadAreaProps {
  onStart: (first: File, second: File | null) => void;
  busy: boolean;
}

export default function UploadArea({ onStart, busy }: UploadAreaProps) {
  const [first, setFirst] = useState<File | null>(null);
  const [second, setSecond] = useState<File | null>(null);

  function pick(setter: (file: File | null) => void) {
    return (event: ChangeEvent<HTMLInputElement>): void => {
      setter(event.target.files?.[0] ?? null);
    };
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    if (first) {
      onStart(first, second);
    }
  }

  return (
    <section>
      <h2>Document</h2>
      <form onSubmit={handleSubmit} className="upload">
        <label>
          Document
          <input
            type="file"
            accept=".pdf,.docx,.txt,.md"
            onChange={pick(setFirst)}
            disabled={busy}
          />
        </label>
        <label>
          Second document, to compare (optional)
          <input
            type="file"
            accept=".pdf,.docx,.txt,.md"
            onChange={pick(setSecond)}
            disabled={busy}
          />
        </label>
        <button type="submit" disabled={busy || !first}>
          {second ? "Compare" : "Analyze"}
        </button>
      </form>
      {second && (
        <p className="status">
          Comparing reads each document on its own first, then puts them side
          by side. It takes about three times as long as a single analysis.
        </p>
      )}
    </section>
  );
}
