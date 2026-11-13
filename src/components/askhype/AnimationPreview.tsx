import { useEffect, useMemo, useRef, useState } from 'react';
import { Play, RotateCcw } from 'lucide-react';
import type { AnimationPlan } from '../../types/chat';
import { actorStateAt, type ActorState } from './animation-state';

const COLORS: Record<string, string> = { blue: '#246BFD', yellow: '#FFD43B', red: '#EF4444', green: '#22C55E', purple: '#8B5CF6', orange: '#F97316', pink: '#EC4899', brown: '#92400E', gray: '#64748B', white: '#F8FAFC', black: '#172033' };
const BACKGROUNDS: Record<string, [string, string]> = { park: ['#BAE6FD', '#86EFAC'], room: ['#FEF3C7', '#D6D3D1'], street: ['#BFDBFE', '#94A3B8'], office: ['#E2E8F0', '#CBD5E1'], school: ['#DBEAFE', '#FDE68A'], space: ['#111827', '#312E81'], abstract: ['#DBEAFE', '#DDD6FE'] };

const Character = ({ character, state }: { character: AnimationPlan['characters'][number]; state: ActorState }) => {
  const body = COLORS[character.appearance.body_color] ?? COLORS.blue;
  const accent = COLORS[character.appearance.accent_color] ?? COLORS.yellow;
  const robot = character.type === 'robot';
  const animal = character.type === 'animal' || character.type === 'creature';
  return <g aria-label={character.name}>
    {animal ? <><ellipse cy="-28" rx="29" ry="25" fill={body}/><circle cx="-20" cy="-48" r="10" fill={accent}/><circle cx="20" cy="-48" r="10" fill={accent}/></> : <rect x="-25" y="-52" width="50" height="48" rx={robot ? 9 : 24} fill={body}/>} 
    <circle cx="-9" cy="-32" r="3" fill="#172033"/><circle cx="9" cy="-32" r="3" fill="#172033"/>
    {state.expression === 'surprised' ? <circle cy="-19" r="5" fill="#172033"/> : <path d="M -9 -20 Q 0 -12 9 -20" fill="none" stroke="#172033" strokeWidth="3" strokeLinecap="round"/>}
    <rect x="-22" y="-5" width="44" height="48" rx="14" fill={accent}/><line x1="-8" y1="43" x2="-12" y2="66" stroke={body} strokeWidth="10" strokeLinecap="round"/><line x1="8" y1="43" x2="12" y2="66" stroke={body} strokeWidth="10" strokeLinecap="round"/>
  </g>;
};

const SceneObject = ({ object }: { object: AnimationPlan['objects'][number] }) => {
  const color = COLORS[object.color] ?? COLORS.blue;
  if (object.type === 'tree') return <g><rect x="-8" y="-45" width="16" height="55" rx="5" fill="#92400E"/><circle cy="-55" r="30" fill={color}/></g>;
  if (object.type === 'star') return <text x="-22" y="8" fontSize="52" fill={color}>★</text>;
  if (object.type === 'rocket') return <g><path d="M0-55 C28-25 26 17 0 35 C-26 17-28-25 0-55Z" fill={color}/><circle cy="-17" r="10" fill="#BAE6FD"/><path d="M-10 34 L0 60 L10 34" fill="#FFD43B"/></g>;
  return <g><rect x="-28" y="-28" width="56" height="56" rx="14" fill={color}/>{object.label && <text textAnchor="middle" y="5" fontSize="12" fill="white">{object.label}</text>}</g>;
};

export const AnimationPreview = ({ plan, remaining }: { plan: AnimationPlan; remaining?: number }) => {
  const reduced = typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
  const [time, setTime] = useState(reduced ? plan.duration_seconds : 0);
  const [playing, setPlaying] = useState(false);
  const frame = useRef<number | null>(null);
  const started = useRef(0);
  useEffect(() => () => { if (frame.current) cancelAnimationFrame(frame.current); }, []);
  const play = () => {
    if (reduced) return setTime(plan.duration_seconds);
    setPlaying(true); started.current = performance.now(); setTime(0);
    const tick = (now: number) => { const next = Math.min((now - started.current) / 1000, plan.duration_seconds); setTime(next); if (next < plan.duration_seconds) frame.current = requestAnimationFrame(tick); else setPlaying(false); };
    frame.current = requestAnimationFrame(tick);
  };
  const background = BACKGROUNDS[plan.background.type] ?? BACKGROUNDS.abstract;
  const actors = useMemo(() => [...plan.objects, ...plan.characters], [plan]);
  return <section className="space-y-3 rounded-xl border border-chat-border bg-chat-elevated p-3">
    <div className="flex items-center justify-between gap-3"><div><h3 className="font-semibold text-chat-text">{plan.title}</h3><p className="text-xs text-chat-muted">{plan.duration_seconds} sekundi · beta</p></div><button type="button" onClick={play} disabled={playing} className="inline-flex items-center gap-2 rounded-full bg-hype-blue px-3 py-2 text-xs font-semibold text-white disabled:opacity-60">{time > 0 ? <RotateCcw size={14}/> : <Play size={14}/>} {time > 0 ? 'Ponovi' : 'Pusti'}</button></div>
    <div className="overflow-hidden rounded-lg bg-slate-900"><svg viewBox="0 0 800 450" role="img" aria-label={`Animacija: ${plan.title}`} className="block h-auto w-full"><rect width="800" height="450" fill={background[0]}/><rect y="315" width="800" height="135" fill={background[1]}/>{actors.map((actor) => { const state = actorStateAt(plan, actor.id, time); if (!state.visible) return null; return <g key={actor.id} transform={`translate(${state.x * 8} ${state.y * 4.5}) scale(${actor.scale}) ${state.transform}`}><g transform="translate(0 -35)">{'appearance' in actor ? <Character character={actor} state={state}/> : <SceneObject object={actor}/>}</g>{state.bubble && <g transform="translate(-90 -150)"><rect width="180" height="58" rx={state.bubble.thought ? 28 : 12} fill="white" stroke="#CBD5E1"/><foreignObject x="10" y="8" width="160" height="44"><p className="m-0 overflow-hidden text-center text-[12px] leading-4 text-slate-900">{state.bubble.text}</p></foreignObject></g>}</g>; })}</svg></div>
    {typeof remaining === 'number' && <p className="text-[11px] text-chat-muted">Preostalo animacija danas: {remaining}</p>}
    {reduced && <p className="text-[11px] text-chat-muted">Prikazan je statičan kadar zbog podešavanja smanjenog kretanja.</p>}
  </section>;
};
