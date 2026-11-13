import { useEffect, useMemo, useRef, useState } from 'react';
import { Play, RotateCcw } from 'lucide-react';
import type { AnimationPlan } from '../../types/chat';
import { actorStateAt, type ActorState } from './animation-state';

const COLORS: Record<string, string> = { blue: '#246BFD', yellow: '#FFD43B', red: '#EF4444', green: '#22C55E', purple: '#8B5CF6', orange: '#F97316', pink: '#EC4899', brown: '#92400E', gray: '#64748B', white: '#F8FAFC', black: '#172033' };
const BACKGROUNDS: Record<string, [string, string]> = { park: ['#BAE6FD', '#86EFAC'], room: ['#FEF3C7', '#D6D3D1'], street: ['#BFDBFE', '#94A3B8'], office: ['#E2E8F0', '#CBD5E1'], school: ['#DBEAFE', '#FDE68A'], space: ['#111827', '#312E81'], abstract: ['#DBEAFE', '#DDD6FE'] };

const Face = ({ state, robot = false }: { state: ActorState; robot?: boolean }) => <g data-part="face">
  <g transform={`translate(${state.eyeOffsetX} ${state.eyeOffsetY})`} data-part="eyes">
    <circle cx="-9" cy="-5" r={state.expression === 'surprised' ? 4 : 3} fill="#172033"/><circle cx="9" cy="-5" r={state.expression === 'surprised' ? 4 : 3} fill="#172033"/>
  </g>
  {state.expression === 'surprised' ? <circle cy="9" r="5" fill="#172033" data-expression="surprised"/>
    : state.expression === 'smile' ? <path d="M -10 7 Q 0 18 10 7" fill="none" stroke="#172033" strokeWidth="3" strokeLinecap="round" data-expression="smile"/>
      : <path d={robot ? 'M -8 9 L 8 9' : 'M -7 10 Q 0 12 7 10'} fill="none" stroke="#172033" strokeWidth="2.5" strokeLinecap="round" data-expression="neutral"/>}
</g>;

const Limb = ({ side, color, upperRotation = 0, forearmRotation = 0, short = false }: { side: 'left' | 'right'; color: string; upperRotation?: number; forearmRotation?: number; short?: boolean }) => {
  const direction = side === 'left' ? -1 : 1;
  const upperLength = short ? 23 : 29;
  const lowerLength = short ? 19 : 24;
  return <g data-part={`${side}-arm`} transform={`translate(${direction * 20} -2) rotate(${upperRotation * direction})`}>
    <line x2={direction * upperLength} y2="17" stroke={color} strokeWidth="10" strokeLinecap="round" data-part={`${side}-upper-arm`}/>
    <g transform={`translate(${direction * upperLength} 17) rotate(${forearmRotation * direction})`} data-part={`${side}-forearm`}>
      <line x2={direction * lowerLength} y2="15" stroke={color} strokeWidth="9" strokeLinecap="round"/><circle cx={direction * lowerLength} cy="15" r="6" fill={color} data-part={`${side}-hand`}/>
    </g>
  </g>;
};

const HumanOrRobot = ({ character, state }: { character: AnimationPlan['characters'][number]; state: ActorState }) => {
  const body = COLORS[character.appearance.body_color] ?? COLORS.blue;
  const accent = COLORS[character.appearance.accent_color] ?? COLORS.yellow;
  const robot = character.type === 'robot'; const child = character.type === 'child';
  const headWidth = robot ? 54 : child ? 58 : 52; const headHeight = robot ? 46 : child ? 56 : 50;
  const torsoHeight = child ? 42 : 53; const legLength = child ? 27 : 38;
  return <g aria-label={character.name} data-character-type={character.type}><g transform={`translate(0 ${state.bodyOffsetY})`} data-part="body">
    <Limb side="left" color={body}/><Limb side="right" color={body} upperRotation={state.rightUpperArmRotation} forearmRotation={state.rightForearmRotation}/>
    <rect x="-22" y="-7" width="44" height={torsoHeight} rx={robot ? 9 : 16} fill={accent} data-part="torso"/>
    {robot && <rect x="-10" y="4" width="20" height="12" rx="3" fill={body} opacity=".85"/>}
    <line x1="-10" y1={torsoHeight - 8} x2="-13" y2={torsoHeight + legLength} stroke={body} strokeWidth="11" strokeLinecap="round" data-part="left-leg"/>
    <line x1="10" y1={torsoHeight - 8} x2="13" y2={torsoHeight + legLength} stroke={body} strokeWidth="11" strokeLinecap="round" data-part="right-leg"/>
    <g transform={`translate(0 ${-headHeight / 2 - 12 + state.headOffsetY}) rotate(${state.headRotation})`} data-part="head">
      <rect x={-headWidth / 2} y={-headHeight / 2} width={headWidth} height={headHeight} rx={robot ? 10 : headHeight / 2} fill={body}/>
      {robot && <><line y1={-headHeight / 2} y2={-headHeight / 2 - 13} stroke={accent} strokeWidth="4"/><circle cy={-headHeight / 2 - 16} r="5" fill={accent}/></>}
      {!robot && character.appearance.hair_style !== 'none' && <path d={`M ${-headWidth / 2 + 5} ${-headHeight / 2 + 10} Q 0 ${-headHeight / 2 - 9} ${headWidth / 2 - 5} ${-headHeight / 2 + 10}`} fill={accent}/>}<Face state={state} robot={robot}/>
    </g>
  </g></g>;
};

const AnimalOrCreature = ({ character, state }: { character: AnimationPlan['characters'][number]; state: ActorState }) => {
  const body = COLORS[character.appearance.body_color] ?? COLORS.blue; const accent = COLORS[character.appearance.accent_color] ?? COLORS.yellow;
  const creature = character.type === 'creature';
  return <g aria-label={character.name} data-character-type={character.type} transform={`translate(0 ${state.bodyOffsetY})`}>
    <ellipse cy="14" rx={creature ? 34 : 42} ry={creature ? 38 : 27} fill={body} data-part="body"/>
    {!creature && <>
      <line x1="-26" y1="26" x2="-29" y2="53" stroke={body} strokeWidth="10" strokeLinecap="round"/>
      <line x1="-10" y1="29" x2="-11" y2="55" stroke={body} strokeWidth="9" strokeLinecap="round"/>
      <line x1="15" y1="28" x2="16" y2="54" stroke={body} strokeWidth="9" strokeLinecap="round"/>
      <g transform={`translate(30 25) rotate(${state.rightUpperArmRotation ? -55 : 0})`} data-part="right-front-paw"><line y2="28" stroke={body} strokeWidth="10" strokeLinecap="round"/><circle cy="29" r="6" fill={body}/></g>
    </>}
    <g transform={`translate(${creature ? 0 : -34} ${creature ? -18 : -17 + state.headOffsetY}) rotate(${state.headRotation})`} data-part="head"><circle r={creature ? 27 : 25} fill={accent}/><circle cx="-17" cy="-19" r="9" fill={body}/><circle cx="17" cy="-19" r="9" fill={body}/><Face state={state}/></g>
    {creature && <><Limb side="left" color={accent} short/><Limb side="right" color={accent} short upperRotation={state.rightUpperArmRotation} forearmRotation={state.rightForearmRotation}/></>}
  </g>;
};

export const ControlledCharacter = ({ character, state }: { character: AnimationPlan['characters'][number]; state: ActorState }) => character.type === 'animal' || character.type === 'creature' ? <AnimalOrCreature character={character} state={state}/> : <HumanOrRobot character={character} state={state}/>;

const SceneObject = ({ object }: { object: AnimationPlan['objects'][number] }) => {
  const color = COLORS[object.color] ?? COLORS.blue;
  if (object.type === 'tree') return <g><rect x="-8" y="-45" width="16" height="55" rx="5" fill="#92400E"/><circle cy="-55" r="30" fill={color}/></g>;
  if (object.type === 'star') return <text x="-22" y="8" fontSize="52" fill={color}>★</text>;
  if (object.type === 'rocket') return <g><path d="M0-55 C28-25 26 17 0 35 C-26 17-28-25 0-55Z" fill={color}/><circle cy="-17" r="10" fill="#BAE6FD"/><path d="M-10 34 L0 60 L10 34" fill="#FFD43B"/></g>;
  return <g><rect x="-28" y="-28" width="56" height="56" rx="14" fill={color}/>{object.label && <text textAnchor="middle" y="5" fontSize="12" fill="white">{object.label}</text>}</g>;
};

export const AnimationPreview = ({ plan, remaining }: { plan: AnimationPlan; remaining?: number }) => {
  const reduced = typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
  const [time, setTime] = useState(reduced ? plan.duration_seconds : 0); const [playing, setPlaying] = useState(false);
  const frame = useRef<number | null>(null); const started = useRef(0);
  useEffect(() => () => { if (frame.current) cancelAnimationFrame(frame.current); }, []);
  const play = () => {
    if (frame.current) cancelAnimationFrame(frame.current); setTime(0);
    if (reduced) return setTime(plan.duration_seconds);
    setPlaying(true); started.current = performance.now();
    const tick = (now: number) => { const next = Math.min((now - started.current) / 1000, plan.duration_seconds); setTime(next); if (next < plan.duration_seconds) frame.current = requestAnimationFrame(tick); else { frame.current = null; setPlaying(false); } };
    frame.current = requestAnimationFrame(tick);
  };
  const background = BACKGROUNDS[plan.background.type] ?? BACKGROUNDS.abstract; const actors = useMemo(() => [...plan.objects, ...plan.characters], [plan]);
  return <section className="space-y-3 rounded-xl border border-chat-border bg-chat-elevated p-3"><div className="flex items-center justify-between gap-3"><div><h3 className="font-semibold text-chat-text">{plan.title}</h3><p className="text-xs text-chat-muted">{plan.duration_seconds} sekundi · beta</p></div><button type="button" onClick={play} disabled={playing} className="inline-flex items-center gap-2 rounded-full bg-hype-blue px-3 py-2 text-xs font-semibold text-white disabled:opacity-60">{time > 0 ? <RotateCcw size={14}/> : <Play size={14}/>} {time > 0 ? 'Ponovi' : 'Pusti'}</button></div>
    <div className="overflow-hidden rounded-lg bg-slate-900"><svg viewBox="0 0 800 450" role="img" aria-label={`Animacija: ${plan.title}`} className="block h-auto w-full"><rect width="800" height="450" fill={background[0]}/><rect y="315" width="800" height="135" fill={background[1]}/>{actors.map((actor) => { const state = actorStateAt(plan, actor.id, time); if (state.opacity <= 0) return null; return <g key={actor.id} opacity={state.opacity} transform={`translate(${state.x * 8} ${state.y * 4.5 - 35}) scale(${actor.scale})`} data-actor={actor.id}>{'appearance' in actor ? <ControlledCharacter character={actor} state={state}/> : <SceneObject object={actor}/>} {state.bubble && <g transform="translate(-90 -150)"><rect width="180" height="58" rx={state.bubble.thought ? 28 : 12} fill="white" stroke="#CBD5E1"/><foreignObject x="10" y="8" width="160" height="44"><p className="m-0 overflow-hidden text-center text-[12px] leading-4 text-slate-900">{state.bubble.text}</p></foreignObject></g>}</g>; })}</svg></div>
    {typeof remaining === 'number' && <p className="text-[11px] text-chat-muted">Preostalo animacija danas: {remaining}</p>}{reduced && <p className="text-[11px] text-chat-muted">Prikazan je statičan kadar zbog podešavanja smanjenog kretanja.</p>}</section>;
};
