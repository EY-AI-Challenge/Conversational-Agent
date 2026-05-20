import { UploadCloud } from 'lucide-react';
import { useRef, useState } from 'react';

import { uploadDocument } from '../api/client';

type DocumentUploaderProps = {
  onUploaded: () => void;
};

export function DocumentUploader({ onUploaded }: DocumentUploaderProps) {
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [status, setStatus] = useState<string>('PDF, TXT, Markdown, Excel ou CSV');
  const [isUploading, setIsUploading] = useState(false);

  async function handleFile(file?: File) {
    if (!file) return;

    setIsUploading(true);
    setStatus(`A indexar ${file.name}...`);
    try {
      const result = await uploadDocument(file);
      setStatus(`${result.filename}: ${result.chunks_indexed} chunks adicionados`);
      onUploaded();
    } catch (error) {
      setStatus(error instanceof Error ? error.message : 'Falha no upload.');
    } finally {
      setIsUploading(false);
      if (inputRef.current) inputRef.current.value = '';
    }
  }

  return (
    <section className="panel upload-panel" aria-label="Carregar documento">
      <div>
        <h2>CV ou documento</h2>
        <p>{status}</p>
      </div>
      <input
        ref={inputRef}
        className="sr-only"
        type="file"
        accept=".pdf,.txt,.md,.xlsx,.xls,.csv"
        onChange={(event) => void handleFile(event.target.files?.[0])}
      />
      <button className="icon-button upload-button" type="button" onClick={() => inputRef.current?.click()} disabled={isUploading}>
        <UploadCloud size={18} />
        <span>{isUploading ? 'A carregar' : 'Carregar'}</span>
      </button>
    </section>
  );
}
