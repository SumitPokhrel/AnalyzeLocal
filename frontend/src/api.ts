// Thin wrappers over the local backend. All URLs are relative, so requests
// always go to the origin serving this page, which is localhost.
//
// The types below mirror the Pydantic models in backend/schemas.py. Keep the
// two in step: a field renamed there has to be renamed here.
//
// The analyze, compare, and question routes stream newline delimited JSON.
// Each line is one StreamEvent, discriminated by the event field.

export interface HealthResponse {
  status: string;
  configured_model: string;
  ollama_available: boolean;
}

export interface StatusEvent {
  event: "status";
  stage: string;
  message: string;
}

export interface MetaEvent {
  event: "meta";
  document_ids: string[];
  document_type: string;
  truncated: boolean;
  // The document was recognized as a kind this tool does not handle well.
  // Separate from truncated: one is this document being too long, the other
  // is the whole class of document being out of scope.
  unsupported_type: boolean;
}

export interface TokenEvent {
  event: "token";
  stage: string;
  text: string;
}

export interface WarningEvent {
  event: "warning";
  unverified: string[];
}

// Sent on every finished answer, not only when something fails. Without it,
// an answer where nothing could be checked looks exactly like one where
// everything checked out. The counts are approximate: they come from a
// regular expression over the answer text.
export interface CoverageEvent {
  event: "coverage";
  figures: number;
  quoted: number;
}

// The first attempt overflowed the context window, so whatever has been
// streamed so far must be discarded and the answer generated again from a
// shorter excerpt.
export interface RestartEvent {
  event: "restart";
  reason: "context_overflow";
  message: string;
}

export interface DoneEvent {
  event: "done";
}

export interface IncompleteEvent {
  event: "incomplete";
  reason: "length" | "interrupted" | "context_overflow";
  detail: string;
}

export interface ErrorEvent {
  event: "error";
  detail: string;
}

export type StreamEvent =
  | StatusEvent
  | MetaEvent
  | TokenEvent
  | WarningEvent
  | CoverageEvent
  | RestartEvent
  | DoneEvent
  | IncompleteEvent
  | ErrorEvent;

export type StreamEventHandler = (event: StreamEvent) => void;

// Shape of the error body FastAPI returns on a request that fails before
// streaming starts.
interface ErrorBody {
  detail?: string;
}

const TERMINAL_EVENTS = new Set(["done", "incomplete", "error"]);

// Used when the stream stops without a terminal event, which means the
// connection dropped partway through. The text on screen is unfinished and
// the quote check never ran, so it cannot be presented as an answer.
export const DROPPED_STREAM: IncompleteEvent = {
  event: "incomplete",
  reason: "interrupted",
  detail:
    "The connection to the local backend stopped before the answer finished, " +
    "so the quote check did not run. Nothing above has been checked against " +
    "the document.",
};

/**
 * Split buffered stream text into whole events, keeping any partial line.
 *
 * A read from the network does not land on line boundaries, so a JSON object
 * can arrive split across two chunks. Whatever follows the last newline is
 * returned as the new buffer rather than parsed.
 */
export function parseNdjsonChunk(
  buffer: string,
  chunk: string
): [StreamEvent[], string] {
  const lines = (buffer + chunk).split("\n");
  const remainder = lines.pop() ?? "";
  const events: StreamEvent[] = [];
  for (const line of lines) {
    const trimmed = line.trim();
    if (trimmed) {
      events.push(JSON.parse(trimmed) as StreamEvent);
    }
  }
  return [events, remainder];
}

async function readStream(
  response: Response,
  onEvent: StreamEventHandler
): Promise<void> {
  if (!response.ok) {
    const body = (await response.json().catch(() => ({}))) as ErrorBody;
    throw new Error(body.detail || `Request failed with status ${response.status}`);
  }
  if (!response.body) {
    throw new Error("This browser cannot read a streamed response.");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let sawTerminal = false;

  const emit = (events: StreamEvent[]): void => {
    for (const event of events) {
      if (TERMINAL_EVENTS.has(event.event)) {
        sawTerminal = true;
      }
      onEvent(event);
    }
  };

  for (;;) {
    const { done, value } = await reader.read();
    if (done) {
      break;
    }
    const [events, rest] = parseNdjsonChunk(buffer, decoder.decode(value, { stream: true }));
    buffer = rest;
    emit(events);
  }

  // Flush anything left after the final read, then report a dropped stream.
  const [tail] = parseNdjsonChunk(buffer, "\n");
  emit(tail);
  if (!sawTerminal) {
    onEvent(DROPPED_STREAM);
  }
}

export async function getHealth(): Promise<HealthResponse> {
  const response = await fetch("/api/health");
  if (!response.ok) {
    throw new Error(`Request failed with status ${response.status}`);
  }
  return (await response.json()) as HealthResponse;
}

export async function streamAnalyze(
  file: File,
  onEvent: StreamEventHandler
): Promise<void> {
  const form = new FormData();
  form.append("file", file);
  await readStream(
    await fetch("/api/analyze", { method: "POST", body: form }),
    onEvent
  );
}

export async function streamCompare(
  first: File,
  second: File,
  onEvent: StreamEventHandler
): Promise<void> {
  const form = new FormData();
  form.append("first", first);
  form.append("second", second);
  await readStream(
    await fetch("/api/compare", { method: "POST", body: form }),
    onEvent
  );
}

export async function streamQuestion(
  documentId: string,
  question: string,
  onEvent: StreamEventHandler
): Promise<void> {
  const response = await fetch("/api/question", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ document_id: documentId, question }),
  });
  await readStream(response, onEvent);
}
