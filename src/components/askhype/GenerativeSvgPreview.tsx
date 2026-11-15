import { useEffect, useMemo, useState } from 'react';
import { RefreshCcw } from 'lucide-react';
import type { GenerativeSvgResponse } from '../../types/chat';

const isolatedDocument = (svg: string): string => `<!doctype html>
<html><head><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; img-src 'none'; font-src 'none'; connect-src 'none'; media-src 'none'; object-src 'none'; frame-src 'none';"><style>html,body{margin:0;width:100%;height:100%;overflow:hidden;background:#0b1220}svg{display:block;width:100%;height:100%}</style></head><body>${svg}</body></html>`;

export const GenerativeSvgPreview = ({ svg, storyboard, remaining, onGenerateAgain }: { svg?: string; storyboard?: GenerativeSvgResponse; remaining?: number; onGenerateAgain?: () => void }) => {
  const [version, setVersion] = useState(0);
  const [sceneIndex, setSceneIndex] = useState(0);
  const scenes = useMemo(() => storyboard?.scenes ?? (svg ? [{ id: 'scene_1', duration_seconds: 10, transition_in: 'fade' as const, transition_out: 'fade' as const, svg }] : []), [storyboard, svg]);
  useEffect(() => {
    if (scenes.length < 2) return;
    const timer = window.setTimeout(() => setSceneIndex((value) => (value + 1) % scenes.length), scenes[sceneIndex].duration_seconds * 1000);
    return () => window.clearTimeout(timer);
  }, [sceneIndex, scenes, version]);
  const scene = scenes[sceneIndex];
  const srcDoc = useMemo(() => isolatedDocument(scene?.svg ?? '<svg xmlns="http://www.w3.org/2000/svg"/>'), [scene]);
  const restart = () => { setSceneIndex(0); setVersion((value) => value + 1); };
  const transitionName = scene?.transition_in === 'slide' ? 'storyboard-slide' : 'storyboard-fade';
  return (
    <section className="space-y-3">
      <style>{`@keyframes storyboard-fade{from{opacity:0}to{opacity:1}}@keyframes storyboard-slide{from{opacity:0;transform:translateX(3%)}to{opacity:1;transform:translateX(0)}}`}</style>
      <div className="aspect-video overflow-hidden rounded-xl border border-chat-border bg-[#0b1220]" style={{ animation: `${transitionName} 450ms ease-out` }} data-transition={scene?.transition_in}>
        <iframe
          key={`${version}-${sceneIndex}`}
          title="AI animacija"
          sandbox=""
          referrerPolicy="no-referrer"
          srcDoc={srcDoc}
          className="h-full w-full border-0"
        />
      </div>
      {storyboard && <div className="flex items-center justify-between gap-3 text-[11px] text-chat-muted"><span>Scena {sceneIndex + 1}/{scenes.length}</span><span>{storyboard.total_duration_seconds} s</span><div className="flex gap-1">{scenes.map((item, index) => <span key={item.id} className={`h-1.5 w-5 rounded-full ${index === sceneIndex ? 'bg-hype-yellow' : 'bg-chat-hover'}`}/>)}</div></div>}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap gap-2">
          <button type="button" onClick={restart} className="inline-flex items-center gap-2 rounded-full border border-chat-outline px-3 py-1.5 text-xs font-medium text-chat-text hover:bg-chat-hover">
            <RefreshCcw size={14}/> Ponovo pokreni
          </button>
          {onGenerateAgain && <button type="button" onClick={onGenerateAgain} className="rounded-full bg-hype-blue px-3 py-1.5 text-xs font-semibold text-white">Generiši ponovo</button>}
        </div>
        {typeof remaining === 'number' && <p className="text-[11px] text-chat-muted">Preostalo animacija danas: {remaining}</p>}
      </div>
    </section>
  );
};
