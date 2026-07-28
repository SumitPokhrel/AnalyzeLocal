import { useState } from "react";
import type { FormEvent } from "react";
import { askQuestion } from "../api.ts";

interface QuestionBoxProps {
  documentId: string;
}

interface Exchange {
  question: string;
  answer: string;
}

export default function QuestionBox({ documentId }: QuestionBoxProps) {
  const [question, setQuestion] = useState("");
  const [messages, setMessages] = useState<Exchange[]>([]);
  const [busy, setBusy] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    const asked = question.trim();
    if (!asked) {
      return;
    }
    setBusy(true);
    setQuestion("");
    try {
      const response = await askQuestion(documentId, asked);
      setMessages((current) => [...current, { question: asked, answer: response.answer }]);
    } catch (problem) {
      const answer = problem instanceof Error ? problem.message : "The question failed.";
      setMessages((current) => [...current, { question: asked, answer }]);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section>
      <h2>Questions</h2>
      {messages.map((message, index) => (
        <div key={index}>
          <p className="asked">{message.question}</p>
          <p className="output">{message.answer}</p>
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
