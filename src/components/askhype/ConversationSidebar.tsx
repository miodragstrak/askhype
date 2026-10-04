import { Plus, X } from 'lucide-react';
import type { LocalConversation } from '../../types/conversation';
import { ConversationHistoryItem } from './ConversationHistoryItem';

interface ConversationSidebarProps {
  conversations: LocalConversation[];
  activeId: string | null;
  mobileOpen: boolean;
  onClose: () => void;
  onNew: () => void;
  onSelect: (id: string) => void;
  onDelete: (id: string) => void;
}

export const ConversationSidebar = ({
  conversations,
  activeId,
  mobileOpen,
  onClose,
  onNew,
  onSelect,
  onDelete,
}: ConversationSidebarProps) => (
  <>
    {mobileOpen && (
      <button
        type="button"
        aria-label="Zatvori istoriju"
        onClick={onClose}
        className="fixed inset-0 z-30 bg-slate-950/30 md:hidden"
      />
    )}
    <aside
      aria-label="Istorija razgovora"
      className={`fixed bottom-0 left-0 top-0 z-40 flex w-[min(86vw,300px)] flex-col border-r border-slate-200 bg-slate-50 transition-transform md:static md:z-auto md:w-72 md:translate-x-0 ${mobileOpen ? 'translate-x-0' : '-translate-x-full'}`}
    >
      <div className="flex h-16 items-center justify-between border-b border-slate-200 px-4 md:hidden">
        <span className="text-sm font-semibold text-slate-900">Razgovori</span>
        <button
          type="button"
          onClick={onClose}
          aria-label="Zatvori"
          title="Zatvori"
          className="inline-flex h-10 w-10 items-center justify-center rounded-md text-slate-600 hover:bg-slate-200 focus:outline-none focus:ring-2 focus:ring-slate-950"
        >
          <X size={19} />
        </button>
      </div>
      <div className="p-3">
        <button
          type="button"
          onClick={onNew}
          className="flex w-full items-center gap-3 rounded-lg border border-slate-300 bg-white px-3 py-2.5 text-sm font-semibold text-slate-900 transition hover:border-slate-500 focus:outline-none focus:ring-2 focus:ring-slate-950 focus:ring-offset-2"
        >
          <Plus size={17} />
          Novi razgovor
        </button>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto px-3 pb-4">
        {conversations.length ? (
          <div className="space-y-1">
            {conversations.map((conversation) => (
              <ConversationHistoryItem
                key={conversation.id}
                conversation={conversation}
                active={conversation.id === activeId}
                onSelect={() => onSelect(conversation.id)}
                onDelete={() => onDelete(conversation.id)}
              />
            ))}
          </div>
        ) : (
          <p className="px-3 py-5 text-sm leading-6 text-slate-500">Tvoji razgovori će se pojaviti ovde.</p>
        )}
      </div>
    </aside>
  </>
);
