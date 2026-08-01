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
  const started =
    run.running || run.answer.length > 0 || run.incomplete !== null;
  if (!started) {
    return null;
  }

  const coverage = run.coverage;
  const nothingChecked = coverage !== null && coverage.quoted === 0;

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

      {run.unsupportedType && (
        <p className="banner severe">
          This looks like a tax return, which AnalyzeLocal does not support.
          Documents of this kind are far larger than the model can read at
          once, so most of it will not be seen. The analysis below will be
          incomplete and should not be relied on.
        </p>
      )}

      {run.truncated && (
        <p className="banner">
          This document was too long for the model's context window, so only
          the first part was read. Figures later in the document were not
          seen.
        </p>
      )}

      {run.restarted && !run.running && (
        <p className="banner">
          The first attempt overflowed the model's context window and was
          discarded. What follows is a second attempt made from a shorter
          excerpt, which is why this took twice as long.
        </p>
      )}

      {run.running && run.message && <p className="status">{run.message}...</p>}

      {run.running && run.restarted && (
        <p className="banner">{run.restarted}</p>
      )}

      {run.progress && run.stage !== "comparing" && (
        <pre className="progress">{run.progress}</pre>
      )}

      <p className="output">{run.answer}</p>

      {run.incomplete && (
        <p
          className={
            run.incomplete.reason === "length" ? "banner" : "banner severe"
          }
        >
          {run.incomplete.detail}
        </p>
      )}

      {coverage !== null && (
        <p className={nothingChecked ? "banner severe" : "status"}>
          {nothingChecked
            ? "No figure in this answer was backed by a quote, so nothing " +
              "here could be checked against your document."
            : `About ${coverage.quoted} of ${coverage.figures} figures in this ` +
              "answer were backed by a quote from your document."}{" "}
          Figure counting is approximate.
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
