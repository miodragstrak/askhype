import { useMemo, useState } from 'react';
import { RefreshCcw } from 'lucide-react';

const isolatedDocument = (svg: string): string => `<!doctype html>
<html><head><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; img-src 'none'; font-src 'none'; connect-src 'none'; media-src 'none'; object-src 'none'; frame-src 'none';"><style>html,body{margin:0;width:100%;height:100%;overflow:hidden;background:#0b1220}svg{display:block;width:100%;height:100%}</style></head><body>${svg}</body></html>`;

export const GenerativeSvgPreview = ({ svg, remaining, onGenerateAgain }: { svg: string; remaining?: number; onGenerateAgain?: () => void }) => {
  const [version, setVersion] = useState(0);
  const srcDoc = useMemo(() => isolatedDocument(svg), [svg]);
  return (
    <section className="space-y-3">
      <div className="aspect-video overflow-hidden rounded-xl border border-chat-border bg-[#0b1220]">
        <iframe
          key={version}
          title="AI animacija"
          sandbox=""
          referrerPolicy="no-referrer"
          srcDoc={srcDoc}
          className="h-full w-full border-0"
        />
      </div>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap gap-2">
          <button type="button" onClick={() => setVersion((value) => value + 1)} className="inline-flex items-center gap-2 rounded-full border border-chat-outline px-3 py-1.5 text-xs font-medium text-chat-text hover:bg-chat-hover">
            <RefreshCcw size={14}/> Ponovo pokreni
          </button>
          {onGenerateAgain && <button type="button" onClick={onGenerateAgain} className="rounded-full bg-hype-blue px-3 py-1.5 text-xs font-semibold text-white">Generiši ponovo</button>}
        </div>
        {typeof remaining === 'number' && <p className="text-[11px] text-chat-muted">Preostalo animacija danas: {remaining}</p>}
      </div>
    </section>
  );
};
