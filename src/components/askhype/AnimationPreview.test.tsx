import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import type { AnimationPlan } from '../../types/chat';
import { AnimationPreview, ControlledCharacter } from './AnimationPreview';
import { actorStateAt } from './animation-state';

const character = (id: string, type: AnimationPlan['characters'][number]['type']) => ({
  id, type, name: id, x: 30, y: 75, scale: 1, expression: 'neutral',
  appearance: { body_color: 'blue', accent_color: 'yellow', hair_style: 'short', accessory: 'none' },
} as const);

const plan: AnimationPlan = {
  title: '<script>alert(1)</script> Likovi u parku', duration_seconds: 8,
  background: { type: 'park', description: 'Park', palette: 'day' },
  characters: [character('person', 'person'), character('child', 'child'), character('robot', 'robot')],
  objects: [],
  timeline: [
    { start: 0, duration: 2, target_id: 'robot', action: 'move', parameters: { x: 60 } },
    { start: 0.5, duration: 1.5, target_id: 'robot', action: 'speech', parameters: { text: 'Zdravo!' } },
    { start: 2, duration: 2, target_id: 'robot', action: 'wave', parameters: {} },
    { start: 4, duration: 2, target_id: 'robot', action: 'look_up', parameters: {} },
    { start: 4, duration: 2, target_id: 'robot', action: 'smile', parameters: {} },
    { start: 6, duration: 2, target_id: 'robot', action: 'surprised', parameters: {} },
  ],
};

const renderCharacter = (id: string, time = 0) => renderToStaticMarkup(
  <svg><ControlledCharacter character={plan.characters.find((item) => item.id === id)!} state={actorStateAt(plan, id, time)}/></svg>,
);

describe('AnimationPreview anatomy and poses', () => {
  it.each(['person', 'child'] as const)('%s has visible left and right arms and hands', (id) => {
    const html = renderCharacter(id);
    expect(html).toContain('data-part="left-arm"');
    expect(html).toContain('data-part="right-arm"');
    expect(html).toContain('data-part="left-hand"');
    expect(html).toContain('data-part="right-hand"');
  });

  it('robot has independently controlled arms', () => {
    const html = renderCharacter('robot');
    expect(html).toContain('data-character-type="robot"');
    expect(html).toContain('data-part="left-arm"');
    expect(html).toContain('data-part="right-forearm"');
  });

  it('wave raises the right arm and oscillates only its forearm', () => {
    const first = actorStateAt(plan, 'robot', 2.2);
    const second = actorStateAt(plan, 'robot', 2.35);
    expect(first.rightUpperArmRotation).toBe(-125);
    expect(first.rightForearmRotation).not.toBe(second.rightForearmRotation);
    expect(first.headRotation).toBe(0);
  });

  it('look up changes head and eyes without translating the actor', () => {
    const state = actorStateAt(plan, 'robot', 4.5);
    expect(state.x).toBe(60);
    expect(state.headRotation).toBe(-5);
    expect(state.eyeOffsetY).toBe(-3);
    expect(state.bodyOffsetY).toBe(0);
  });

  it('renders controlled smile and surprised mouths', () => {
    expect(renderCharacter('robot', 4.5)).toContain('data-expression="smile"');
    expect(renderCharacter('robot', 6.5)).toContain('data-expression="surprised"');
  });

  it('nod affects the head channel only', () => {
    const nodPlan = { ...plan, timeline: [{ start: 0, duration: 2, target_id: 'robot', action: 'nod' as const, parameters: {} }] };
    const state = actorStateAt(nodPlan, 'robot', 0.25);
    expect(state.headRotation).not.toBe(0);
    expect(state.x).toBe(30);
    expect(state.rightUpperArmRotation).toBe(0);
  });

  it('sequential wave then look-up resets the arm but keeps the new head pose', () => {
    const waving = actorStateAt(plan, 'robot', 3);
    const looking = actorStateAt(plan, 'robot', 5);
    expect(waving.rightUpperArmRotation).toBe(-125);
    expect(looking.rightUpperArmRotation).toBe(0);
    expect(looking.eyeOffsetY).toBe(-3);
    expect(looking.expression).toBe('smile');
  });

  it('initial state used by replay resets position, pose, expression and bubbles', () => {
    const reset = actorStateAt(plan, 'robot', 0);
    expect(reset.x).toBe(30);
    expect(reset.rightUpperArmRotation).toBe(0);
    expect(reset.expression).toBe('neutral');
    expect(reset.bubble).toBeUndefined();
  });

  it('renders responsive controlled SVG and escapes provider text', () => {
    const html = renderToStaticMarkup(<AnimationPreview plan={plan} remaining={4}/>);
    expect(html).toContain('class="block h-auto w-full"');
    expect(html).toContain('Preostalo animacija danas: 4');
    expect(html).not.toContain('<script>alert');
    expect(html).toContain('&lt;script&gt;alert');
  });

  it('renders a stable static final scene for reduced motion', () => {
    const originalWindow = globalThis.window;
    Object.defineProperty(globalThis, 'window', { configurable: true, value: { matchMedia: () => ({ matches: true }) } });
    try {
      const html = renderToStaticMarkup(<AnimationPreview plan={plan}/>);
      expect(html).toContain('Prikazan je statičan kadar');
      expect(html).toContain('Ponovi');
    } finally {
      Object.defineProperty(globalThis, 'window', { configurable: true, value: originalWindow });
    }
  });
});
