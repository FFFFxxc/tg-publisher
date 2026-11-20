import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, readdirSync } from 'node:fs';

const read = path => readFileSync(new URL(`../${path}`, import.meta.url), 'utf8');
const globalCss = read('src/app/globals.css');
const palette = Object.fromEntries([...globalCss.matchAll(/--([a-z-]+): (#\w{3,6});/g)].map(([, n, v]) => [n, v]));

function luminance(hex) {
  assert.ok(hex, 'palette color missing');
  const digits = hex.slice(1);
  const rgb = (digits.length === 3 ? [...digits].map(d => d + d) : digits.match(/../g))
    .map(d => Number.parseInt(d, 16) / 255)
    .map(v => v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4);
  return 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2];
}

test('normal dashboard text, controls and status labels reach 4.5:1', () => {
  const pairs = ['ink','muted','subtle','accent','success','warning','danger','info']
    .flatMap(ink => ['paper','canvas','tint','selected'].map(paper => [ink, paper]));
  for (const state of ['success','warning','danger','info']) pairs.push([state, `${state}-tint`]);
  pairs.push(['paper','accent']);
  for (const [fg,bg] of pairs) {
    const [lo,hi] = [luminance(palette[fg]), luminance(palette[bg])].sort((a,b)=>a-b);
    assert.ok((hi + 0.05) / (lo + 0.05) >= 4.5, `${fg} on ${bg}`);
  }
});

test('one shared palette and no legacy dark surface utilities in dashboard JSX', () => {
  assert.match(globalCss, /color-scheme: light/);
  assert.doesNotMatch(read('src/app/home.css'), /--home-(?:muted|card|accent|ink):/);
  const src = new URL('../src/', import.meta.url);
  for (const name of readdirSync(src, {recursive: true})) {
    if (!name.endsWith('.tsx')) continue;
    assert.doesNotMatch(read(`src/${name.replaceAll('\\', '/')}`), /\b(?:bg|text|border)-(?:slate|zinc)-\d+|home-theme/, name);
  }
});
