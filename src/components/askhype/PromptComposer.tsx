import { useEffect, useRef, useState } from 'react';
import { ArrowUp } from 'lucide-react';

interface PromptComposerProps {
  onSubmit: (value: string) => void;
  disabled?: boolean;
  autoFocus?: boolean;
}

export const PromptComposer = ({ onSubmit, disabled = false, autoFocus = false }: PromptComposerProps) => {
  const [value, setValue] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const textarea = textareaRef.current;
    if (!textarea) return;
    textarea.style.height = '0px';
    textarea.style.height = `${Math.min(textarea.scrollHeight, 160)}px`;
  }, [value]);

  const submit = () => {
    const prompt = value.trim();
    if (!prompt || disabled) return;
    onSubmit(prompt);
    setValue('');
  };

  return (
    <div className="rounded-2xl border border-slate-300 bg-white p-2 shadow-[0_8px_30px_rgba(15,23,42,0.08)] focus-within:border-slate-500 focus-within:ring-2 focus-within:ring-yellow-300">
      <div className="flex items-end gap-2">
        <textarea
          ref={textareaRef}
          value={value}
          onChange={(event) => setValue(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter' && !event.shiftKey) {
              event.preventDefault();
              submit();
            }
          }}
          rows={1}
          autoFocus={autoFocus}
          disabled={disabled}
          aria-label="Poruka za AskHype"
          placeholder="Pitaj AskHype..."
          className="max-h-40 min-h-12 flex-1 resize-none bg-transparent px-3 py-3 text-[15px] leading-6 text-slate-950 outline-none placeholder:text-slate-400 disabled:cursor-not-allowed disabled:opacity-60"
        />
        <button
          type="button"
          onClick={submit}
          disabled={disabled || !value.trim()}
          aria-label="Pošalji poruku"
          title="Pošalji"
          className="mb-1 inline-flex h-10 w-10 flex-none items-center justify-center rounded-full bg-slate-950 text-white transition hover:bg-slate-800 focus:outline-none focus:ring-2 focus:ring-slate-950 focus:ring-offset-2 disabled:cursor-not-allowed disabled:bg-slate-200 disabled:text-slate-500"
        >
          <ArrowUp size={19} strokeWidth={2.5} />
        </button>
      </div>
    </div>
  );
};
