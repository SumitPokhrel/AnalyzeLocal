import { useEffect, useState } from "react";
import { analyzeDocument, getHealth } from "./api.ts";
import type { AnalyzeResponse, HealthResponse } from "./api.ts";
import UploadArea from "./components/UploadArea.tsx";
import ResultsView from "./components/ResultsView.tsx";
import QuestionBox from "./components/QuestionBox.tsx";

export default function App() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [result, setResult] = useState<AnalyzeResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    getHealth()
      .then(setHealth)
      .catch(() => setHealth(null));
  }, []);

  async function handleFile(file: File): Promise<void> {
    setBusy(true);
    setError("");
    try {
      setResult(await analyzeDocument(file));
    } catch (problem) {
      setError(problem instanceof Error ? problem.message : "Analysis failed.");
      setResult(null);
    } finally {
      setBusy(false);
    }
  }

  return (
    <main>
      <header>
        <h1>AnalyzeLocal</h1>
        <p className="subtitle">
          Everything runs on this machine. Nothing is uploaded anywhere.
        </p>
        {health && (
          <p className="status">
            Model: {health.configured_model}.{" "}
            {health.ollama_available
              ? "Local model runtime is reachable."
              : "Ollama is not running. Start it, then reload this page."}
          </p>
        )}
      </header>

      <UploadArea onFile={handleFile} busy={busy} />

      {error && <p className="error">{error}</p>}

      {result && (
        <>
          <ResultsView result={result} />
          <QuestionBox documentId={result.document_id} />
        </>
      )}
    </main>
  );
}
