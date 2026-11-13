import { useEffect, useRef, useState } from 'react';
import { ArrowUp, FileSearch, FileText, ImagePlus, Presentation, X } from 'lucide-react';
import type { DocumentAction, PendingDocument, PendingImage } from '../../types/chat';

const hasPresentationIntent = (value: string): boolean => {
  const prompt = value.toLocaleLowerCase('sr').replace(/\s+/g, ' ').trim();
  return [
    'napravi prezentaciju',
    'kreiraj prezentaciju',
    'napravi powerpoint',
    'kreiraj powerpoint',
    'pptx',
    'presentation',
    'powerpoint presentation',
  ].some((phrase) => prompt.includes(phrase));
};

interface PromptComposerProps {
  onSubmit: (value: string, images: PendingImage[], document: PendingDocument | null, action: DocumentAction) => Promise<boolean>;
  disabled?: boolean;
  autoFocus?: boolean;
}

export const PromptComposer = ({ onSubmit, disabled = false, autoFocus = false }: PromptComposerProps) => {
  const [value, setValue] = useState('');
  const [images, setImages] = useState<PendingImage[]>([]);
  const [document, setDocument] = useState<PendingDocument | null>(null);
  const [documentAction, setDocumentAction] = useState<DocumentAction>('analyze');
  const documentActionRef = useRef<DocumentAction>('analyze');
  const actionExplicitRef = useRef(false);
  const [validationError, setValidationError] = useState<string | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const documentInputRef = useRef<HTMLInputElement>(null);

  const selectDocumentAction = (action: DocumentAction, explicit = true) => {
    documentActionRef.current = action;
    actionExplicitRef.current = explicit;
    setDocumentAction(action);
  };

  useEffect(() => {
    const textarea = textareaRef.current;
    if (!textarea) return;
    textarea.style.height = '0px';
    textarea.style.height = `${Math.min(textarea.scrollHeight, 160)}px`;
  }, [value]);

  const submit = async () => {
    const prompt = value.trim();
    const selectedAction = actionExplicitRef.current
      ? documentActionRef.current
      : hasPresentationIntent(prompt) ? 'presentation' : 'analyze';
    if (!actionExplicitRef.current && selectedAction !== documentActionRef.current) {
      selectDocumentAction(selectedAction, false);
    }
    if (selectedAction === 'transform') {
      if (!document) {
        setValidationError('Dokument je obavezan za Excel izmenu.');
        return;
      }
      if (!document.file.name.toLocaleLowerCase().endsWith('.xlsx')) {
        setValidationError('Za ovu opciju potreban je XLSX fajl.');
        return;
      }
    }
    if (selectedAction === 'research' && images.length) {
      setValidationError('Deep Research podržava pitanje i najviše jedan dokument, ne slike.');
      return;
    }
    if ((!prompt && !images.length) || (document && !prompt) || disabled) return;
    if (await onSubmit(prompt, images, document, selectedAction)) {
      setValue('');
      images.forEach((image) => URL.revokeObjectURL(image.previewUrl));
      setImages([]);
      setDocument(null);
      selectDocumentAction('analyze', false);
      setValidationError(null);
    }
  };

  const selectImages = (files: FileList | null) => {
    if (!files) return;
    if (documentAction === 'presentation') return setValidationError('Slike nisu podržane kao izvor za prezentaciju.');
    if (documentAction === 'research') return setValidationError('Slike nisu podržane za Deep Research.');
    if (document) return setValidationError('Ukloni dokument pre dodavanja slika.');
    const selected = [...files];
    if (images.length + selected.length > 3) return setValidationError('Možeš poslati najviše 3 slike u jednoj poruci.');
    const invalid = selected.find((file) => !['image/jpeg', 'image/png', 'image/webp'].includes(file.type));
    if (invalid) return setValidationError('Podržane su JPG, PNG i WebP slike.');
    if (selected.some((file) => !file.size || file.size > 10 * 1024 * 1024)) return setValidationError('Slika je prevelika ili prazna. Maksimalna veličina je 10 MB.');
    setImages((current) => [...current, ...selected.map((file) => ({ file, previewUrl: URL.createObjectURL(file) }))]);
    setValidationError(null);
  };

  const selectDocument = (files: FileList | null) => {
    const file = files?.[0];
    if (!file) return;
    const extension = file.name.split('.').pop()?.toLocaleLowerCase();
    const supported = ['pdf', 'docx', 'xlsx', 'csv'];
    if (!extension || !supported.includes(extension)) {
      if (documentActionRef.current === 'presentation') {
        return setValidationError('Za prezentaciju su podržani samo PDF, DOCX, XLSX i CSV dokumenti.');
      }
      return setValidationError('Podržani su samo PDF, Word, Excel i CSV dokumenti.');
    }
    if (!file.size || file.size > 15 * 1024 * 1024) {
      return setValidationError('Dokument je prazan ili veći od dozvoljenih 15 MB.');
    }
    images.forEach((image) => URL.revokeObjectURL(image.previewUrl));
    setImages([]);
    setDocument({ file });
    setValidationError(null);
  };

  return (
    <div className="rounded-2xl border border-chat-outline bg-[var(--app-composer)] p-2 shadow-[0_8px_30px_rgba(21,35,84,0.08)] focus-within:border-hype-yellow focus-within:ring-2 focus-within:ring-hype-yellow">
      {!document && <div className="flex items-center justify-end gap-1 px-1 pb-1">
        <button
          type="button"
          onClick={() => { selectDocumentAction(documentActionRef.current === 'research' ? 'analyze' : 'research'); setValidationError(null); }}
          className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-medium ${documentAction === 'research' ? 'bg-hype-blue text-white' : 'text-chat-muted hover:bg-chat-hover hover:text-chat-text'}`}
        >
          <FileSearch size={14} /> Deep Research
        </button>
        <button
          type="button"
          onClick={() => {
            selectDocumentAction(documentActionRef.current === 'presentation' ? 'analyze' : 'presentation');
            images.forEach((image) => URL.revokeObjectURL(image.previewUrl));
            setImages([]);
            setValidationError(null);
          }}
          className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-medium ${documentAction === 'presentation' ? 'bg-hype-blue text-white' : 'text-chat-muted hover:bg-chat-hover hover:text-chat-text'}`}
        >
          <Presentation size={14} /> {documentAction === 'presentation' ? 'Prezentacija' : 'Napravi prezentaciju'}
        </button>
      </div>}
      {images.length > 0 && <div className="flex gap-2 p-2">{images.map((image) => <div key={image.previewUrl} className="relative"><img src={image.previewUrl} alt="Priložena slika" className="h-16 w-16 rounded-lg object-cover"/><button type="button" aria-label="Ukloni sliku" onClick={() => { URL.revokeObjectURL(image.previewUrl); setImages((current) => current.filter((item) => item !== image)); }} className="absolute -right-1 -top-1 rounded-full bg-chat-surface p-1 text-chat-text"><X size={12}/></button></div>)}</div>}
      {document && (
        <div className="m-1 flex items-center gap-3 rounded-xl border border-chat-border bg-chat-surface px-3 py-2">
          <FileText size={18} className="flex-none text-hype-yellow" />
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-medium text-chat-text">{document.file.name}</p>
            <p className="text-[11px] uppercase text-chat-muted">{document.file.name.split('.').pop()} · dokument</p>
          </div>
          <div className="flex flex-wrap justify-end rounded-lg border border-chat-border p-0.5 text-[11px]">
            <button type="button" onClick={() => selectDocumentAction('analyze')} className={`rounded-md px-2 py-1 ${documentAction === 'analyze' ? 'bg-chat-hover text-chat-text' : 'text-chat-muted'}`}>Analiziraj</button>
            {document.file.name.toLocaleLowerCase().endsWith('.xlsx') && (
              <button type="button" onClick={() => selectDocumentAction('transform')} className={`rounded-md px-2 py-1 ${documentAction === 'transform' ? 'bg-hype-blue text-white' : 'text-chat-muted'}`}>Uredi Excel</button>
            )}
            <button type="button" onClick={() => selectDocumentAction('presentation')} className={`rounded-md px-2 py-1 ${documentAction === 'presentation' ? 'bg-hype-blue text-white' : 'text-chat-muted'}`}>Prezentacija</button>
            <button type="button" onClick={() => selectDocumentAction('research')} className={`rounded-md px-2 py-1 ${documentAction === 'research' ? 'bg-hype-blue text-white' : 'text-chat-muted'}`}>Deep Research</button>
          </div>
          <button type="button" onClick={() => setDocument(null)} aria-label="Ukloni dokument" className="inline-flex h-9 w-9 items-center justify-center rounded-full text-chat-muted hover:bg-chat-hover hover:text-chat-text"><X size={16} /></button>
        </div>
      )}
      {validationError && <p className="px-2 pb-1 text-xs text-red-600">{validationError}</p>}
      {documentAction === 'research' && (
        <p className="px-2 pb-1 text-[11px] text-chat-muted">Deep Research koristi zaseban dnevni limit tokom beta testiranja.</p>
      )}
      <div className="flex items-end gap-2">
        <input ref={inputRef} type="file" accept="image/jpeg,image/png,image/webp" multiple className="hidden" onChange={(event) => { selectImages(event.target.files); event.target.value = ''; }}/>
        <input ref={documentInputRef} type="file" accept=".pdf,.docx,.xlsx,.csv,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,text/csv" className="hidden" onChange={(event) => { selectDocument(event.target.files); event.target.value = ''; }}/>
        <button type="button" disabled={disabled} onClick={() => inputRef.current?.click()} aria-label="Dodaj slike" title="Dodaj slike" className="mb-1 inline-flex h-10 w-10 flex-none items-center justify-center rounded-full text-chat-muted hover:bg-chat-hover"><ImagePlus size={19}/></button>
        <button type="button" disabled={disabled} onClick={() => documentInputRef.current?.click()} aria-label="Dodaj dokument" title="Documents — dodaj PDF, Word, Excel ili CSV" className="mb-1 inline-flex h-10 w-10 flex-none items-center justify-center rounded-full text-chat-muted hover:bg-chat-hover"><FileText size={19}/></button>
        <textarea
          ref={textareaRef}
          value={value}
          onChange={(event) => {
            const nextValue = event.target.value;
            setValue(nextValue);
            if (!actionExplicitRef.current) {
              selectDocumentAction(hasPresentationIntent(nextValue) ? 'presentation' : 'analyze', false);
            }
          }}
          onKeyDown={(event) => {
            if (event.key === 'Enter' && !event.shiftKey) {
              event.preventDefault();
              void submit();
            }
          }}
          rows={1}
          autoFocus={autoFocus}
          disabled={disabled}
          aria-label="Poruka za AskHype"
          placeholder={documentAction === 'research' ? 'Postavi pitanje za dubinsko istraživanje...' : documentAction === 'presentation' ? 'Opiši PowerPoint prezentaciju...' : documentAction === 'transform' ? 'Opiši željenu Excel izmenu...' : document ? 'Pitanje o dokumentu...' : 'Pitaj...'}
          className="max-h-40 min-h-12 flex-1 resize-none bg-transparent px-3 py-3 text-[15px] leading-6 text-chat-text outline-none placeholder:text-chat-muted disabled:cursor-not-allowed disabled:text-chat-muted"
        />
        <button
          type="button"
          onClick={() => void submit()}
          disabled={disabled || (document ? !value.trim() : (!value.trim() && !images.length))}
          aria-label="Pošalji poruku"
          title="Pošalji"
          className="mb-1 inline-flex h-10 w-10 flex-none items-center justify-center rounded-full bg-hype-yellow text-chat-surface transition enabled:hover:bg-yellow-300 focus:outline-none focus:ring-2 focus:ring-hype-yellow focus:ring-offset-2 focus:ring-offset-chat-elevated disabled:cursor-not-allowed disabled:bg-chat-hover disabled:text-chat-muted"
        >
          <ArrowUp size={19} strokeWidth={2.5} />
        </button>
      </div>
    </div>
  );
};
