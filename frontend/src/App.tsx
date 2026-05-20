import { RefreshCcw, Search, SendHorizontal, SlidersHorizontal } from 'lucide-react';
import { FormEvent, useMemo, useState } from 'react';

import { ChatMessage } from './components/ChatMessage';
import { DocumentUploader } from './components/DocumentUploader';
import { streamQuestion } from './api/client';
import type { Message, Source } from './api/client';

type ChatEntry = {
  id: string;
  message: Message;
  sources?: Source[];
};

const suggestedQuestions = [
  'Quem é responsável por Assurance-Audit?',
  'Resume a experiência relevante de um partner para preparar uma reunião com cliente.',
  'Que conhecimento interno temos sobre AI e transformação?',
];

const filters = [
  { id: 'partner_cv', label: 'Partner CVs' },
  { id: 'service_line', label: 'Service lines' },
  { id: 'news', label: 'News' },
  { id: 'transcript', label: 'Transcrições' },
  { id: 'uploaded_document', label: 'Uploads' },
  { id: 'external', label: 'Web sources' },
];

const initialEntry: ChatEntry = {
  id: 'welcome',
  message: {
    role: 'assistant',
    content:
      'Olá. Sou o Knowledge Navigator EY Assistant. Pesquisa em documentos internos, fontes indexadas e documentos carregados, sempre com citações.',
  },
};

function App() {
  const [entries, setEntries] = useState<ChatEntry[]>([initialEntry]);
  const [question, setQuestion] = useState('');
  const [activeFilters, setActiveFilters] = useState<string[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const history = useMemo<Message[]>(
    () => entries.filter((entry) => entry.id !== 'welcome').map((entry) => entry.message),
    [entries],
  );
  async function submitQuestion(nextQuestion?: string) {
    const text = (nextQuestion ?? question).trim();
    if (!text || isLoading) return;

    const userEntry: ChatEntry = {
      id: crypto.randomUUID(),
      message: { role: 'user', content: text },
    };
    const assistantId = crypto.randomUUID();
    const assistantEntry: ChatEntry = {
      id: assistantId,
      message: { role: 'assistant', content: '' },
      sources: [],
    };

    setEntries((current) => [...current, userEntry, assistantEntry]);
    setQuestion('');
    setError(null);
    setIsLoading(true);

    try {
      await streamQuestion(text, [...history, userEntry.message], activeFilters, {
        onSources: (streamedSources) => {
          setEntries((current) =>
            current.map((entry) => (entry.id === assistantId ? { ...entry, sources: streamedSources } : entry)),
          );
        },
        onToken: (token) => {
          setEntries((current) =>
            current.map((entry) =>
              entry.id === assistantId
                ? { ...entry, message: { ...entry.message, content: entry.message.content + token } }
                : entry,
            ),
          );
        },
      });
    } catch (requestError) {
      setEntries((current) => current.filter((entry) => entry.id !== assistantId));
      setError(requestError instanceof Error ? requestError.message : 'Erro inesperado.');
    } finally {
      setIsLoading(false);
    }
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void submitQuestion();
  }

  function toggleFilter(filterId: string) {
    setActiveFilters((current) =>
      current.includes(filterId) ? current.filter((item) => item !== filterId) : [...current, filterId],
    );
  }

  return (
    <main className="app-shell">
      <aside className="sidebar" aria-label="Painel de conhecimento">
        <div className="brand-lockup">
          <div className="ey-mark">EY</div>
          <div>
            <h1>Knowledge Navigator EY Assistant</h1>
            <p>Conversational Agent Challenge</p>
          </div>
        </div>

        <section className="panel">
          <div className="panel-title">
            <SlidersHorizontal size={18} />
            <h2>Filtros</h2>
          </div>
          <div className="filter-list">
            {filters.map((filter) => (
              <button
                className={activeFilters.includes(filter.id) ? 'filter active' : 'filter'}
                type="button"
                key={filter.id}
                onClick={() => toggleFilter(filter.id)}
              >
                {filter.label}
              </button>
            ))}
          </div>
        </section>

        <DocumentUploader onUploaded={() => undefined} />
      </aside>

      <section className="workspace" aria-label="Chat com conhecimento EY">
        <header className="workspace-header">
          <div>
            <h2>Knowledge Navigator EY Assistant</h2>
          </div>
          <button className="ghost-button" type="button" onClick={() => setEntries([initialEntry])}>
            <RefreshCcw size={17} />
            <span>Nova conversa</span>
          </button>
        </header>

        <div className="suggested-strip" aria-label="Perguntas sugeridas">
          {suggestedQuestions.map((item) => (
            <button type="button" key={item} onClick={() => void submitQuestion(item)}>
              {item}
            </button>
          ))}
        </div>

        <div className="chat-thread">
          {entries.map((entry) => (
            <ChatMessage message={entry.message} sources={entry.sources} key={entry.id} />
          ))}
          {isLoading ? (
            <div className="thinking">
              <Search size={16} />
              <span>A gerar resposta...</span>
            </div>
          ) : null}
        </div>

        {error ? <div className="error-banner">{error}</div> : null}

        <form className="composer" onSubmit={handleSubmit}>
          <textarea
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            placeholder="Escreve uma pergunta sobre partners, service lines, AI, notícias EY ou documentos carregados..."
            rows={2}
          />
          <button className="send-button" type="submit" disabled={isLoading || !question.trim()}>
            <SendHorizontal size={19} />
            <span>Enviar</span>
          </button>
        </form>
      </section>
    </main>
  );
}

export default App;
