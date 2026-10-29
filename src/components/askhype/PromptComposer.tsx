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
    <div className="rounded-2xl border border-chat-outline bg-chat-elevated p-2 shadow-[0_8px_30px_rgba(21,35,84,0.08)] focus-within:border-hype-yellow focus-within:ring-2 focus-within:ring-hype-yellow">
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
          className="max-h-40 min-h-12 flex-1 resize-none bg-transparent px-3 py-3 text-[15px] leading-6 text-chat-text outline-none placeholder:text-chat-muted disabled:cursor-not-allowed disabled:text-chat-muted"
        />
        <button
          type="button"
          onClick={submit}
          disabled={disabled || !value.trim()}
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
