import type { AnimationPlan } from '../../types/chat';

export interface ActorState { x: number; y: number; visible: boolean; transform: string; expression: string; bubble?: { text: string; thought: boolean } }

export const actorStateAt = (plan: AnimationPlan, id: string, time: number): ActorState => {
  const actor = [...plan.characters, ...plan.objects].find((item) => item.id === id)!;
  const events = plan.timeline.filter((item) => item.target_id === id);
  let state: ActorState = { x: actor.x, y: actor.y, visible: !events.some((event) => event.action === 'appear' && time < event.start), transform: '', expression: 'expression' in actor ? actor.expression : 'neutral' };
  for (const event of events.filter((item) => time >= item.start)) {
    const progress = Math.min((time - event.start) / event.duration, 1);
    const active = progress < 1;
    if (event.action === 'move') state = { ...state, x: actor.x + ((event.parameters.x ?? actor.x) - actor.x) * progress, y: actor.y + ((event.parameters.y ?? actor.y) - actor.y) * progress };
    if (event.action === 'enter_left') state.x = actor.x - (1 - progress) * 110;
    if (event.action === 'enter_right') state.x = actor.x + (1 - progress) * 110;
    if (event.action === 'exit_left') state.x = actor.x - progress * 110;
    if (event.action === 'exit_right') state.x = actor.x + progress * 110;
    if (event.action === 'appear') state.visible = progress >= 0;
    if (event.action === 'disappear') state.visible = progress < 1;
    if (active && event.action === 'bounce') state.transform = `translate(0 ${-Math.abs(Math.sin(progress * Math.PI * 2)) * 22})`;
    if (active && event.action === 'wave') state.transform = `rotate(${Math.sin(progress * Math.PI * 4) * 7})`;
    if (active && event.action === 'nod') state.transform = `translate(0 ${Math.sin(progress * Math.PI * 4) * 5})`;
    if (active && event.action === 'shake') state.transform = `translate(${Math.sin(progress * Math.PI * 6) * 6} 0)`;
    if (active && event.action === 'look_left') state.transform = 'rotate(-5)';
    if (active && event.action === 'look_right') state.transform = 'rotate(5)';
    if (active && event.action === 'look_up') state.transform = 'translate(0 -5)';
    if (active && ['speech', 'thought'].includes(event.action) && event.parameters.text) state.bubble = { text: event.parameters.text, thought: event.action === 'thought' };
    if (active && ['smile', 'surprised'].includes(event.action)) state.expression = event.action;
  }
  return state;
};
