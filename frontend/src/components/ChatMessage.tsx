import { Bot, UserRound } from 'lucide-react';

import type { Message, Source } from '../api/client';

type ChatMessageProps = {
  message: Message;
  sources?: Source[];
};

function sourceLabel(source: Source) {
  const page = source.page ? `, p. ${source.page}` : '';
  const type = source.document_type === 'external' ? 'web' : source.document_type;
  return `${source.source}${page} · ${type}`;
}

export function ChatMessage({ message, sources = [] }: ChatMessageProps) {
  const isUser = message.role === 'user';

  return (
    <article className={`chat-message ${isUser ? 'chat-message-user' : 'chat-message-assistant'}`}>
      <div className="message-avatar" aria-hidden="true">
        {isUser ? <UserRound size={18} /> : <Bot size={18} />}
      </div>
      <div className="message-content">
        <p>{message.content}</p>
        {!isUser && sources.length > 0 ? (
          <div className="source-list" aria-label="Fontes usadas">
            {sources.slice(0, 4).map((source) => (
              <span className="source-chip" key={`${source.source}-${source.page ?? 'no-page'}-${source.document_type}`}>
                {sourceLabel(source)}
              </span>
            ))}
          </div>
        ) : null}
      </div>
    </article>
  );
}
