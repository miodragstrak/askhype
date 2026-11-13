import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import type { AnimationPlan } from '../../types/chat';
import { AnimationPreview } from './AnimationPreview';
import { actorStateAt } from './animation-state';

const plan: AnimationPlan = {
  title: 'Robot pozdravlja', duration_seconds: 6,
  background: { type: 'park', description: 'Park', palette: 'day' },
  characters: [{ id: 'robot', type: 'robot', name: 'Roki', x: 30, y: 75, scale: 1, expression: 'neutral', appearance: { body_color: 'blue', accent_color: 'yellow', hair_style: 'none', accessory: 'antenna' } }],
  objects: [],
  timeline: [{ start: 0, duration: 2, target_id: 'robot', action: 'move', parameters: { x: 60 } }, { start: 0, duration: 2, target_id: 'robot', action: 'speech', parameters: { text: '<script>alert(1)</script> Zdravo!' } }],
};

describe('AnimationPreview', () => {
  it('computes deterministic movement and bubbles', () => {
    expect(actorStateAt(plan, 'robot', 1).x).toBe(45);
    expect(actorStateAt(plan, 'robot', 1).bubble?.text).toContain('Zdravo');
  });

  it('renders controlled SVG and escapes provider text', () => {
    const html = renderToStaticMarkup(<AnimationPreview plan={plan} remaining={4} />);
    expect(html).toContain('<svg');
    expect(html).toContain('class="block h-auto w-full"');
    expect(html).toContain('Pusti');
    expect(html).toContain('Preostalo animacija danas: 4');
    expect(html).not.toContain('<script>alert');
    expect(html).toContain('&lt;script&gt;alert');
  });

  it('renders a static final scene for reduced motion', () => {
    const originalWindow = globalThis.window;
    Object.defineProperty(globalThis, 'window', { configurable: true, value: { matchMedia: () => ({ matches: true }) } });
    try {
      const html = renderToStaticMarkup(<AnimationPreview plan={plan} />);
      expect(html).toContain('Prikazan je statičan kadar');
      expect(html).toContain('Ponovi');
    } finally {
      Object.defineProperty(globalThis, 'window', { configurable: true, value: originalWindow });
    }
  });
});
