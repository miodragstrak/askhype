import { useEffect, useRef, useState } from 'react';
import { ArrowUp, ImagePlus, X } from 'lucide-react';
import type { PendingImage } from '../../types/chat';

interface PromptComposerProps {
  onSubmit: (value: string, images: PendingImage[]) => Promise<boolean>;
  disabled?: boolean;
  autoFocus?: boolean;
}

export const PromptComposer = ({ onSubmit, disabled = false, autoFocus = false }: PromptComposerProps) => {
  const [value, setValue] = useState('');
  const [images, setImages] = useState<PendingImage[]>([]);
  const [validationError, setValidationError] = useState<string | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const textarea = textareaRef.current;
    if (!textarea) return;
    textarea.style.height = '0px';
    textarea.style.height = `${Math.min(textarea.scrollHeight, 160)}px`;
  }, [value]);

  const submit = async () => {
    const prompt = value.trim();
    if ((!prompt && !images.length) || disabled) return;
    if (await onSubmit(prompt, images)) {
      setValue('');
      setImages([]);
      setValidationError(null);
    }
  };

  const selectImages = (files: FileList | null) => {
    if (!files) return;
    const selected = [...files];
    if (images.length + selected.length > 3) return setValidationError('Možeš poslati najviše 3 slike u jednoj poruci.');
    const invalid = selected.find((file) => !['image/jpeg', 'image/png', 'image/webp'].includes(file.type));
    if (invalid) return setValidationError('Podržane su JPG, PNG i WebP slike.');
    if (selected.some((file) => !file.size || file.size > 10 * 1024 * 1024)) return setValidationError('Slika je prevelika ili prazna. Maksimalna veličina je 10 MB.');
    setImages((current) => [...current, ...selected.map((file) => ({ file, previewUrl: URL.createObjectURL(file) }))]);
    setValidationError(null);
  };

  return (
    <div className="rounded-2xl border border-chat-outline bg-[var(--app-composer)] p-2 shadow-[0_8px_30px_rgba(21,35,84,0.08)] focus-within:border-hype-yellow focus-within:ring-2 focus-within:ring-hype-yellow">
      {images.length > 0 && <div className="flex gap-2 p-2">{images.map((image) => <div key={image.previewUrl} className="relative"><img src={image.previewUrl} alt="Priložena slika" className="h-16 w-16 rounded-lg object-cover"/><button type="button" aria-label="Ukloni sliku" onClick={() => { URL.revokeObjectURL(image.previewUrl); setImages((current) => current.filter((item) => item !== image)); }} className="absolute -right-1 -top-1 rounded-full bg-chat-surface p-1 text-chat-text"><X size={12}/></button></div>)}</div>}
      {validationError && <p className="px-2 pb-1 text-xs text-red-600">{validationError}</p>}
      <div className="flex items-end gap-2">
        <input ref={inputRef} type="file" accept="image/jpeg,image/png,image/webp" multiple className="hidden" onChange={(event) => { selectImages(event.target.files); event.target.value = ''; }}/>
        <button type="button" disabled={disabled} onClick={() => inputRef.current?.click()} aria-label="Dodaj slike" title="Dodaj slike" className="mb-1 inline-flex h-10 w-10 flex-none items-center justify-center rounded-full text-chat-muted hover:bg-chat-hover"><ImagePlus size={19}/></button>
        <textarea
          ref={textareaRef}
          value={value}
          onChange={(event) => setValue(event.target.value)}
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
          placeholder="Pitaj AskHype..."
          className="max-h-40 min-h-12 flex-1 resize-none bg-transparent px-3 py-3 text-[15px] leading-6 text-chat-text outline-none placeholder:text-chat-muted disabled:cursor-not-allowed disabled:text-chat-muted"
        />
        <button
          type="button"
          onClick={() => void submit()}
          disabled={disabled || (!value.trim() && !images.length)}
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
