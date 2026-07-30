import type { AnalyzeResponse } from "../api.ts";

interface ResultsViewProps {
  result: AnalyzeResponse;
}

export default function ResultsView({ result }: ResultsViewProps) {
  return (
    <section>
      <h2>Analysis</h2>
      <p className="output">{result.analysis}</p>
    </section>
  );
}
