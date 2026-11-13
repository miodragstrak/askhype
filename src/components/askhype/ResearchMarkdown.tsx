import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type { ResearchSource } from '../../types/chat';
import { replaceResearchCitations, safeResearchHref } from './research-display';

interface ResearchMarkdownProps {
  text: string;
  sources: ResearchSource[];
  compact?: boolean;
}

export const ResearchMarkdown = ({ text, sources, compact = false }: ResearchMarkdownProps) => (
  <div className={compact ? 'research-markdown text-[15px] leading-7 text-chat-text' : 'research-markdown text-sm leading-7 text-chat-text'}>
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={{
        h1: ({ children }) => <h4 className="mb-2 mt-5 text-lg font-semibold text-chat-text">{children}</h4>,
        h2: ({ children }) => <h4 className="mb-2 mt-5 text-base font-semibold text-chat-text">{children}</h4>,
        h3: ({ children }) => <h5 className="mb-2 mt-4 text-sm font-semibold text-chat-text">{children}</h5>,
        p: ({ children }) => <p className="my-2 whitespace-normal">{children}</p>,
        ul: ({ children }) => <ul className="my-3 list-disc space-y-1 pl-6">{children}</ul>,
        ol: ({ children }) => <ol className="my-3 list-decimal space-y-1 pl-6">{children}</ol>,
        blockquote: ({ children }) => <blockquote className="my-3 border-l-2 border-chat-outline pl-4 text-chat-muted">{children}</blockquote>,
        table: ({ children }) => <div className="my-4 max-w-full overflow-x-auto rounded-lg border border-chat-border"><table className="w-full min-w-max border-collapse text-left text-xs">{children}</table></div>,
        th: ({ children }) => <th className="border-b border-r border-chat-border bg-chat-elevated px-3 py-2 font-semibold text-chat-text last:border-r-0">{children}</th>,
        td: ({ children }) => <td className="border-b border-r border-chat-border px-3 py-2 align-top last:border-r-0">{children}</td>,
        code: ({ className, children }) => {
          const block = Boolean(className) || String(children).includes('\n');
          return block
            ? <code className={`${className ?? ''} block overflow-x-auto rounded-lg bg-chat-elevated p-3 font-mono text-xs leading-5`}>{children}</code>
            : <code className="rounded bg-chat-elevated px-1.5 py-0.5 font-mono text-xs">{children}</code>;
        },
        pre: ({ children }) => <pre className="my-4 max-w-full overflow-x-auto">{children}</pre>,
        a: ({ href, children }) => {
          const safeHref = href ? safeResearchHref(href) : null;
          return safeHref ? (
            <a href={safeHref} target="_blank" rel="noopener noreferrer"
              className="font-medium text-hype-blue underline decoration-chat-outline underline-offset-2 focus:outline-none focus:ring-2 focus:ring-hype-yellow">
              {children}
            </a>
          ) : <span>{children}</span>;
        },
      }}
    >
      {replaceResearchCitations(text, sources)}
    </ReactMarkdown>
  </div>
);
