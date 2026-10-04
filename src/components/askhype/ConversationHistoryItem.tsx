import { MessageSquare, Trash2 } from 'lucide-react';
import type { LocalConversation } from '../../types/conversation';

interface ConversationHistoryItemProps {
  conversation: LocalConversation;
  active: boolean;
  onSelect: () => void;
  onDelete: () => void;
}

export const ConversationHistoryItem = ({
  conversation,
  active,
  onSelect,
  onDelete,
}: ConversationHistoryItemProps) => (
  <div className={`group flex items-center gap-1 rounded-lg ${active ? 'bg-slate-200' : 'hover:bg-slate-100'}`}>
    <button
      type="button"
      onClick={onSelect}
      aria-current={active ? 'page' : undefined}
      className="flex min-w-0 flex-1 items-center gap-3 px-3 py-2.5 text-left focus:outline-none focus:ring-2 focus:ring-inset focus:ring-slate-950"
    >
      <MessageSquare size={15} className="flex-none text-slate-500" />
      <span className="truncate text-sm font-medium text-slate-700">{conversation.title}</span>
    </button>
    <button
      type="button"
      onClick={onDelete}
      aria-label={`Obriši razgovor: ${conversation.title}`}
      title="Obriši razgovor"
      className="mr-1 inline-flex h-9 w-9 flex-none items-center justify-center rounded-md text-slate-400 opacity-70 transition hover:bg-white hover:text-red-700 focus:opacity-100 focus:outline-none focus:ring-2 focus:ring-slate-950 sm:opacity-0 sm:group-hover:opacity-100"
    >
      <Trash2 size={15} />
    </button>
  </div>
);
