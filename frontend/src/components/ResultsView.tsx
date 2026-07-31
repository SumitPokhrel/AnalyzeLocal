import type { RunState } from "../App.tsx";

interface ResultsViewProps {
  run: RunState;
}

const TYPE_LABELS: Record<string, string> = {
  job_offer: "Job offer",
  lease: "Lease",
  tax_return: "Tax return",
  generic: "Document",
};

export default function ResultsView({ run }: ResultsViewProps) {
  const started = run.running || run.answer.length > 0 || run.incomplete !== null;
  if (!started) {
    return null;
  }

  return (
    <section>
      <h2>
        Analysis
        {run.documentType && (
          <span className="badge">
            {TYPE_LABELS[run.documentType] ?? run.documentType}
          </span>
        )}
      </h2>

      {run.truncated && (
        <p className="banner">
          This document was too long for the model's context window, so only
          the first part was read. Figures later in the document were not
          seen.
        </p>
      )}

      {run.running && run.message && (
        <p className="status">{run.message}...</p>
      )}

      {run.progress && run.stage !== "comparing" && (
        <pre className="progress">{run.progress}</pre>
      )}

      <p className="output">{run.answer}</p>

      {run.incomplete && (
        <p className={run.incomplete.reason === "interrupted" ? "banner severe" : "banner"}>
          {run.incomplete.detail}
        </p>
      )}

      {run.unverified.length > 0 && (
        <div className="banner severe">
          <p>
            These quotes could not be found in your document. Treat the
            figures they support as unconfirmed.
          </p>
          <ul>
            {run.unverified.map((quote) => (
              <li key={quote}>{quote}</li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
