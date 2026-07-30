// Thin wrappers over the local backend. All URLs are relative, so requests
// always go to the origin serving this page, which is localhost.
//
// The types below mirror the Pydantic models in backend/schemas.py. Keep the
// two in step: a field renamed there has to be renamed here.

export interface HealthResponse {
  status: string;
  configured_model: string;
  ollama_available: boolean;
}

export interface AnalyzeResponse {
  document_id: string;
  analysis: string;
}

// The compare route exists on the backend but has no caller in the UI yet.
export interface CompareResponse {
  document_ids: string[];
  comparison: string;
}

export interface QuestionResponse {
  answer: string;
}

// Shape of the error body FastAPI returns on a failed request.
interface ErrorBody {
  detail?: string;
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(path, options);
  if (!response.ok) {
    const body = (await response.json().catch(() => ({}))) as ErrorBody;
    throw new Error(body.detail || `Request failed with status ${response.status}`);
  }
  return (await response.json()) as T;
}

export function getHealth(): Promise<HealthResponse> {
  return request<HealthResponse>("/api/health");
}

export function analyzeDocument(file: File): Promise<AnalyzeResponse> {
  const form = new FormData();
  form.append("file", file);
  return request<AnalyzeResponse>("/api/analyze", { method: "POST", body: form });
}

export function askQuestion(documentId: string, question: string): Promise<QuestionResponse> {
  return request<QuestionResponse>("/api/question", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ document_id: documentId, question }),
  });
}
