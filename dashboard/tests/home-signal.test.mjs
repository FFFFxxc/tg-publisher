import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const read = path => readFileSync(new URL(`../src/${path}`, import.meta.url), 'utf8');
const css = read('app/home.css');

test('signal is decorative and rendered by the home route, not the shared shell', () => {
  const page = read('app/page.tsx');
  assert.match(page, /<HomeSignal \/>/);
  assert.doesNotMatch(read('app/layout.tsx') + read('components/AppShell.tsx'), /HomeSignal/);
  assert.match(read('components/HomeSignal.tsx'), /className="home-signal" aria-hidden="true"/);
  assert.match(css, /\.home-signal\s*\{[^}]*pointer-events: none/);
});

test('native checkbox pauses each moving layer and reduced motion disables them', () => {
  const page = read('app/page.tsx');
  assert.match(page, /id="home-signal-pause"[^>]+type="checkbox"/);
  assert.match(page, /<label htmlFor="home-signal-pause"/);
  const layers = /:is\(\.home-signal-haze, \.home-signal-traces, \.home-signal-pulse\)/.source;
  assert.match(css, new RegExp(`\\.home-motion-input:checked ~ \\.home-signal ${layers}[^}]*animation-play-state: paused`));
  assert.match(css, new RegExp(`prefers-reduced-motion: reduce[\\s\\S]*${layers}[^}]*animation: none`));
});
