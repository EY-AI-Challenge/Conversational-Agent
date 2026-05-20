export type Role = 'user' | 'assistant';

export type Message = {
  role: Role;
  content: string;
};

export type Source = {
  source: string;
  document_type: string;
  page?: number | null;
  title?: string | null;
  service_line?: string | null;
  url?: string | null;
  score?: number | null;
  excerpt?: string | null;
};

export type ChatResponse = {
  answer: string;
  sources: Source[];
};

type StreamEvent =
  | { type: 'sources'; sources: Source[] }
  | { type: 'token'; content: string }
  | { type: 'error'; message: string }
  | { type: 'done' };

export type SourceSummary = {
  source: string;
  document_type: string;
  chunks: number;
};

export type HealthResponse = {
  status: string;
  collection_name: string;
  documents_indexed: number;
  data_dir: string;
};

export async function streamQuestion(
  question: string,
  history: Message[],
  filters: string[],
  handlers: {
    onSources: (sources: Source[]) => void;
    onToken: (token: string) => void;
  },
): Promise<void> {
  const response = await fetch('/api/chat/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question, history, filters }),
  });

  if (!response.ok || !response.body) {
    const payload = await response.json().catch(() => null);
    throw new Error(payload?.detail ?? 'Erro ao contactar a API.');
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() ?? '';

    for (const line of lines) {
      if (!line.trim()) continue;
      const event = JSON.parse(line) as StreamEvent;
      if (event.type === 'sources') handlers.onSources(event.sources);
      if (event.type === 'token') handlers.onToken(event.content);
      if (event.type === 'error') throw new Error(event.message);
    }
  }
}

export async function fetchHealth(): Promise<HealthResponse> {
  const response = await fetch('/health');
  if (!response.ok) {
    throw new Error('Não foi possível obter o estado da API.');
  }
  return response.json();
}

export async function fetchSources(): Promise<SourceSummary[]> {
  const response = await fetch('/api/sources');
  if (!response.ok) {
    throw new Error('Não foi possível obter as fontes.');
  }
  return response.json();
}

export async function uploadDocument(file: File): Promise<{ filename: string; chunks_indexed: number; message: string }> {
  const formData = new FormData();
  formData.append('file', file);

  const response = await fetch('/api/upload', {
    method: 'POST',
    body: formData,
  });

  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    throw new Error(payload?.detail ?? 'Falha ao carregar o documento.');
  }

  return response.json();
}
