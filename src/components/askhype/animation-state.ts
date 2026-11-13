import type { AnimationPlan } from '../../types/chat';

export type FaceExpression = 'neutral' | 'smile' | 'surprised';

export interface ActorState {
  x: number; y: number; opacity: number; bodyOffsetY: number;
  headRotation: number; headOffsetY: number; eyeOffsetX: number; eyeOffsetY: number;
  rightUpperArmRotation: number; rightForearmRotation: number;
  expression: FaceExpression;
  bubble?: { text: string; thought: boolean };
}

const progressAt = (time: number, start: number, duration: number) =>
  Math.min(Math.max((time - start) / duration, 0), 1);

export const actorStateAt = (plan: AnimationPlan, id: string, time: number): ActorState => {
  const actor = [...plan.characters, ...plan.objects].find((item) => item.id === id)!;
  const events = plan.timeline.filter((item) => item.target_id === id).sort((a, b) => a.start - b.start);
  const baseExpression = 'expression' in actor && actor.expression === 'surprised'
    ? 'surprised' : 'expression' in actor && actor.expression === 'happy' ? 'smile' : 'neutral';
  const state: ActorState = {
    x: actor.x, y: actor.y,
    opacity: events.some((event) => event.action === 'appear' && time < event.start) ? 0 : 1,
    bodyOffsetY: 0, headRotation: 0, headOffsetY: 0, eyeOffsetX: 0, eyeOffsetY: 0,
    rightUpperArmRotation: 0, rightForearmRotation: 0, expression: baseExpression,
  };

  for (const event of events) {
    if (time < event.start) continue;
    const progress = progressAt(time, event.start, event.duration);
    const active = progress < 1;
    if (event.action === 'move') {
      const destinationX = event.parameters.x ?? state.x;
      const destinationY = event.parameters.y ?? state.y;
      state.x += (destinationX - state.x) * progress;
      state.y += (destinationY - state.y) * progress;
    }
    if (event.action === 'enter_left') state.x = actor.x - (1 - progress) * 110;
    if (event.action === 'enter_right') state.x = actor.x + (1 - progress) * 110;
    if (event.action === 'exit_left') state.x = actor.x - progress * 110;
    if (event.action === 'exit_right') state.x = actor.x + progress * 110;
    if (event.action === 'appear') state.opacity = progress;
    if (event.action === 'disappear') state.opacity = 1 - progress;
    if (!active) continue;
    if (event.action === 'bounce') state.bodyOffsetY += -Math.abs(Math.sin(progress * Math.PI * 2)) * 22;
    if (event.action === 'wave') {
      state.rightUpperArmRotation = -125;
      state.rightForearmRotation = -28 + Math.sin(progress * Math.PI * 8) * 24;
    }
    if (event.action === 'nod') {
      state.headRotation += Math.sin(progress * Math.PI * 4) * 8;
      state.headOffsetY += Math.sin(progress * Math.PI * 4) * 3;
    }
    if (event.action === 'shake') state.headRotation += Math.sin(progress * Math.PI * 6) * 12;
    if (event.action === 'look_left') { state.headRotation -= 5; state.eyeOffsetX -= 3; }
    if (event.action === 'look_right') { state.headRotation += 5; state.eyeOffsetX += 3; }
    if (event.action === 'look_up') { state.headRotation -= 5; state.eyeOffsetY -= 3; }
    if ((event.action === 'speech' || event.action === 'thought') && event.parameters.text) {
      state.bubble = { text: event.parameters.text, thought: event.action === 'thought' };
    }
    if (event.action === 'smile') state.expression = 'smile';
    if (event.action === 'surprised') state.expression = 'surprised';
  }
  return state;
};
