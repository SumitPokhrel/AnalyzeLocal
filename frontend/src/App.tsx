import { useEffect, useState } from "react";
import { getHealth, streamAnalyze, streamCompare } from "./api.ts";
import type { HealthResponse, IncompleteEvent, StreamEvent } from "./api.ts";
import UploadArea from "./components/UploadArea.tsx";
import ResultsView from "./components/ResultsView.tsx";
import QuestionBox from "./components/QuestionBox.tsx";

// Everything the results pane needs, filled in as events arrive.
export interface RunState {
  documentIds: string[];
  documentType: string;
  truncated: boolean;
  stage: string;
  message: string;
  progress: string;
  answer: string;
  unverified: string[];
  incomplete: IncompleteEvent | null;
  error: string;
  running: boolean;
}

const EMPTY_RUN: RunState = {
  documentIds: [],
  documentType: "",
  truncated: false,
  stage: "",
  message: "",
  progress: "",
  answer: "",
  unverified: [],
  incomplete: null,
  error: "",
  running: false,
};

// Digest text belongs in the progress area, not the answer pane.
const PROGRESS_STAGES = new Set(["reading_first", "reading_second"]);

export default function App() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [run, setRun] = useState<RunState>(EMPTY_RUN);

  useEffect(() => {
    getHealth()
      .then(setHealth)
      .catch(() => setHealth(null));
  }, []);

  function apply(event: StreamEvent): void {
    setRun((current) => {
      switch (event.event) {
        case "meta":
          return {
            ...current,
            documentIds: event.document_ids,
            documentType: event.document_type,
            truncated: event.truncated,
          };
        case "status":
          return { ...current, stage: event.stage, message: event.message };
        case "token":
          return PROGRESS_STAGES.has(event.stage)
            ? { ...current, progress: current.progress + event.text }
            : { ...current, answer: current.answer + event.text };
        case "warning":
          return { ...current, unverified: event.unverified };
        case "incomplete":
          return { ...current, incomplete: event, running: false };
        case "error":
          return { ...current, error: event.detail, running: false };
        case "done":
          return { ...current, running: false, stage: "", message: "" };
      }
    });
  }

  async function start(first: File, second: File | null): Promise<void> {
    setRun({ ...EMPTY_RUN, running: true });
    try {
      if (second) {
        await streamCompare(first, second, apply);
      } else {
        await streamAnalyze(first, apply);
      }
    } catch (problem) {
      const detail = problem instanceof Error ? problem.message : "The run failed.";
      setRun((current) => ({ ...current, error: detail, running: false }));
    }
  }

  const canAskQuestions =
    !run.running && run.documentIds.length === 1 && run.answer.length > 0;

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

      <UploadArea onStart={start} busy={run.running} />

      {run.error && <p className="error">{run.error}</p>}

      <ResultsView run={run} />

      {canAskQuestions && <QuestionBox documentId={run.documentIds[0]} />}
    </main>
  );
}
