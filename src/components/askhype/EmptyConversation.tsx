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
    <h1 className="text-3xl font-semibold text-slate-950 sm:text-4xl">Šta želiš da otkriješ?</h1>
    <p className="mt-3 max-w-md text-sm leading-6 text-slate-500 sm:text-base">
      Pitaj za mesta, događaje, hranu ili sledeće putovanje.
    </p>
    <div className="mt-8 flex max-w-xl flex-wrap justify-center gap-2">
      {HYPE_EXAMPLES.map((prompt) => (
        <button
          key={prompt}
          type="button"
          onClick={() => onSelect(prompt)}
          className="min-h-10 rounded-full border border-blue-200 bg-blue-50/50 px-4 py-2 text-sm text-blue-800 transition hover:border-blue-400 hover:bg-blue-50 focus:outline-none focus:ring-2 focus:ring-blue-700 focus:ring-offset-2"
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
          className="min-h-10 rounded-full border border-slate-200 bg-white px-4 py-2 text-sm text-slate-700 transition hover:border-slate-400 hover:text-slate-950 focus:outline-none focus:ring-2 focus:ring-slate-950 focus:ring-offset-2"
        >
          {prompt}
        </button>
      ))}
    </div>
  </div>
);
