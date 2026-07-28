import type { ChangeEvent } from "react";

interface UploadAreaProps {
  onFile: (file: File) => void;
  busy: boolean;
}

export default function UploadArea({ onFile, busy }: UploadAreaProps) {
  function handleChange(event: ChangeEvent<HTMLInputElement>): void {
    const file = event.target.files?.[0];
    if (file) {
      onFile(file);
    }
  }

  return (
    <section>
      <h2>Document</h2>
      <input
        type="file"
        accept=".pdf,.docx,.txt,.md"
        onChange={handleChange}
        disabled={busy}
      />
      {busy && <p className="status">Working. Local analysis can take a minute.</p>}
    </section>
  );
}
