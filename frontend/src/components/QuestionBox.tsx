import { useState } from "react";
import type { FormEvent } from "react";
import { streamQuestion } from "../api.ts";
import type { StreamEvent } from "../api.ts";

interface QuestionBoxProps {
  documentId: string;
}

interface Exchange {
  question: string;
  answer: string;
  unverified: string[];
  incomplete: string;
  error: string;
}

function blankExchange(question: string): Exchange {
  return { question, answer: "", unverified: [], incomplete: "", error: "" };
}

export default function QuestionBox({ documentId }: QuestionBoxProps) {
  const [question, setQuestion] = useState("");
  const [exchanges, setExchanges] = useState<Exchange[]>([]);
  const [busy, setBusy] = useState(false);

  // Every event updates the newest exchange, which is the one being answered.
  function updateLatest(change: (current: Exchange) => Exchange): void {
    setExchanges((all) =>
      all.map((item, index) => (index === all.length - 1 ? change(item) : item))
    );
  }

  function apply(event: StreamEvent): void {
    switch (event.event) {
      case "token":
        updateLatest((item) => ({ ...item, answer: item.answer + event.text }));
        break;
      case "warning":
        updateLatest((item) => ({ ...item, unverified: event.unverified }));
        break;
      case "incomplete":
        updateLatest((item) => ({ ...item, incomplete: event.detail }));
        break;
      case "error":
        updateLatest((item) => ({ ...item, error: event.detail }));
        break;
      default:
        break;
    }
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    const asked = question.trim();
    if (!asked) {
      return;
    }
    setBusy(true);
    setQuestion("");
    setExchanges((all) => [...all, blankExchange(asked)]);
    try {
      await streamQuestion(documentId, asked, apply);
    } catch (problem) {
      const detail =
        problem instanceof Error ? problem.message : "The question failed.";
      updateLatest((item) => ({ ...item, error: detail }));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section>
      <h2>Questions</h2>
      {exchanges.map((exchange, index) => (
        <div key={index}>
          <p className="asked">{exchange.question}</p>
          <p className="output">{exchange.answer}</p>
          {exchange.incomplete && <p className="banner severe">{exchange.incomplete}</p>}
          {exchange.error && <p className="error">{exchange.error}</p>}
          {exchange.unverified.length > 0 && (
            <div className="banner severe">
              <p>These quotes could not be found in your document.</p>
              <ul>
                {exchange.unverified.map((quote) => (
                  <li key={quote}>{quote}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      ))}
      <form onSubmit={handleSubmit}>
        <input
          type="text"
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          placeholder="Ask about this document"
          disabled={busy}
        />
        <button type="submit" disabled={busy}>
          Ask
        </button>
      </form>
    </section>
  );
}
