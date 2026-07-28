import type { AnalyzeResponse } from "../api.ts";

interface ResultsViewProps {
  result: AnalyzeResponse;
}

export default function ResultsView({ result }: ResultsViewProps) {
  return (
    <section>
      <h2>Analysis</h2>
      <p className="output">{result.analysis}</p>

      <h2>Redacted text</h2>
      <p className="status">{result.spans.length} items were redacted.</p>
      <pre className="output">{result.redacted_text}</pre>
    </section>
  );
}
