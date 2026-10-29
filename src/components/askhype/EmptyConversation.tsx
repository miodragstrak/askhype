const EXAMPLES = [
  'Gde da izađem večeras u Beogradu?',
  'Isplaniraj mi vikend na Tari.',
];

const HYPE_EXAMPLES = [
  'Šta ima novo na Hype TV?',
  'Koje Hype emisije vredi pogledati?',
  'Koji Hype koncerti uskoro dolaze?',
  'Ko su izvođači Hype Production-a?',
];

interface EmptyConversationProps {
  onSelect: (prompt: string) => void;
}

export const EmptyConversation = ({ onSelect }: EmptyConversationProps) => (
  <div className="mx-auto flex w-full max-w-2xl flex-1 flex-col items-center justify-center px-4 pb-8 pt-12 text-center sm:px-8">
    <h1 className="text-3xl font-semibold text-chat-text sm:text-4xl">Šta želiš da otkriješ?</h1>
    <p className="mt-3 max-w-md text-sm leading-6 text-chat-muted sm:text-base">
      Pitaj za mesta, događaje, hranu ili sledeće putovanje.
    </p>
    <div className="mt-8 flex max-w-xl flex-wrap justify-center gap-2">
      {HYPE_EXAMPLES.map((prompt) => (
        <button
          key={prompt}
          type="button"
          onClick={() => onSelect(prompt)}
          className="min-h-10 rounded-full border border-chat-source-border bg-hype-blue px-4 py-2 text-sm text-chat-source transition hover:bg-chat-hover focus:outline-none focus:ring-2 focus:ring-hype-yellow focus:ring-offset-2 focus:ring-offset-chat-bg"
        >
          {prompt}
        </button>
      ))}
    </div>
    <div className="mt-3 flex max-w-xl flex-wrap justify-center gap-2">
      {EXAMPLES.map((prompt) => (
        <button
          key={prompt}
          type="button"
          onClick={() => onSelect(prompt)}
          className="min-h-10 rounded-full border border-chat-outline bg-chat-elevated px-4 py-2 text-sm text-chat-text transition hover:bg-chat-hover focus:outline-none focus:ring-2 focus:ring-hype-yellow focus:ring-offset-2 focus:ring-offset-chat-bg"
        >
          {prompt}
        </button>
      ))}
    </div>
  </div>
);
