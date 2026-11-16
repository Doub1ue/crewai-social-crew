#!/usr/bin/env node
/**
 * Headless image-card renderer for the CrewAI social crew.
 *
 * Uses Two.js (renderer-agnostic 2D API) on top of node-canvas to draw one
 * branded PNG card per queued social post. Called by src/graphics.py with a
 * job JSON file:
 *
 *   node graphics/make_card.js <job.json>
 *
 * Job format:
 * {
 *   "width": 1080, "height": 1080,
 *   "brand": {
 *     "background_color": "#14213d", "text_color": "#ffffff",
 *     "accent_color": "#fca311", "account_name": "My Page",
 *     "handle": "@mypage"
 *   },
 *   "cards": [ { "text": "<post text>", "output": "/abs/path/post-1.png" } ]
 * }
 *
 * Prints one JSON line per card: {"output": ..., "ok": true|false}.
 */
'use strict';

const fs = require('fs');
const path = require('path');
const { createCanvas, Image } = require('canvas');
const Two = require('two.js');

const FONT_FAMILY = "Liberation Sans, DejaVu Sans, sans-serif";

/** Strip hashtags and trim a post down to a card-sized headline. */
function headlineFrom(text) {
  let t = String(text || '').replace(/#\S+/g, '').replace(/\s+/g, ' ').trim();
  if (t.length > 190) {
    const cut = t.slice(0, 190);
    const sentenceEnd = Math.max(
      cut.lastIndexOf('. '), cut.lastIndexOf('! '), cut.lastIndexOf('? '));
    t = sentenceEnd > 80
      ? cut.slice(0, sentenceEnd + 1)
      : cut.slice(0, cut.lastIndexOf(' ')) + '…';
  }
  return t;
}

/** Greedy word wrap using real canvas text measurement. */
function wrapLines(ctx, text, font, maxWidth) {
  ctx.font = font;
  const words = text.split(' ');
  const lines = [];
  let line = '';
  for (const word of words) {
    const trial = line ? line + ' ' + word : word;
    if (ctx.measureText(trial).width <= maxWidth || !line) {
      line = trial;
    } else {
      lines.push(line);
      line = word;
    }
  }
  if (line) lines.push(line);
  return lines;
}

/** Pick the largest font size whose wrapped headline fits the card. */
function fitHeadline(ctx, text, maxWidth, maxLines) {
  for (const size of [64, 58, 52, 46, 40, 34]) {
    const font = `700 ${size}px ${FONT_FAMILY}`;
    const lines = wrapLines(ctx, text, font, maxWidth);
    if (lines.length <= maxLines) return { size, lines };
  }
  const size = 34;
  const lines = wrapLines(ctx, text, `700 ${size}px ${FONT_FAMILY}`, maxWidth);
  const kept = lines.slice(0, maxLines);
  kept[maxLines - 1] = kept[maxLines - 1].replace(/\s*\S*$/, '') + '…';
  return { size, lines: kept };
}

function renderCard(job, card) {
  const W = job.width || 1080;
  const H = job.height || 1080;
  const brand = job.brand || {};
  const bg = brand.background_color || '#14213d';
  const fg = brand.text_color || '#ffffff';
  const accent = brand.accent_color || '#fca311';

  const canvas = createCanvas(W, H);
  try { Two.Utils.polyfill(canvas, Image); } catch (e) { /* newer two.js needs no polyfill */ }
  const ctx = canvas.getContext('2d');
  const two = new Two({ width: W, height: H, domElement: canvas });

  // Background + accent furniture.
  const background = two.makeRectangle(W / 2, H / 2, W, H);
  background.fill = bg;
  background.noStroke();

  const glow = two.makeCircle(W * 0.92, H * 0.94, W * 0.24);
  glow.fill = accent;
  glow.opacity = 0.12;
  glow.noStroke();

  const topBar = two.makeRectangle(W / 2, 14, W, 28);
  topBar.fill = accent;
  topBar.noStroke();

  // Headline (wrapped post text), drawn line by line so each line is
  // centered and the block's vertical extent is exactly known — a single
  // multi-line Two.Text misjudges its height in the canvas renderer and
  // can run over the footer.
  const headline = headlineFrom(card.text);
  const { size, lines } = fitHeadline(ctx, headline, W - 200, 7);
  const leading = Math.round(size * 1.28);
  const blockTop = H * 0.43 - ((lines.length - 1) * leading) / 2;
  lines.forEach((line, i) => {
    const t = two.makeText(line, W / 2, blockTop + i * leading);
    t.family = FONT_FAMILY;
    t.size = size;
    t.weight = 700;
    t.alignment = 'center';
    t.baseline = 'middle';
    t.fill = fg;
  });

  // Accent divider under the headline.
  const divider = two.makeRectangle(W / 2, H * 0.76, 120, 6);
  divider.fill = accent;
  divider.noStroke();

  // Account name + handle footer.
  if (brand.account_name) {
    const name = two.makeText(brand.account_name, W / 2, H * 0.83);
    name.family = FONT_FAMILY;
    name.size = 40;
    name.weight = 700;
    name.alignment = 'center';
    name.baseline = 'middle';
    name.fill = fg;
  }
  if (brand.handle) {
    const handle = two.makeText(brand.handle, W / 2, H * 0.885);
    handle.family = FONT_FAMILY;
    handle.size = 34;
    handle.alignment = 'center';
    handle.baseline = 'middle';
    handle.fill = accent;
  }

  two.update();
  fs.mkdirSync(path.dirname(card.output), { recursive: true });
  fs.writeFileSync(card.output, canvas.toBuffer('image/png'));
}

function main() {
  const jobPath = process.argv[2];
  if (!jobPath) {
    console.error('usage: node graphics/make_card.js <job.json>');
    process.exit(2);
  }
  const job = JSON.parse(fs.readFileSync(jobPath, 'utf-8'));
  let failures = 0;
  for (const card of job.cards || []) {
    try {
      renderCard(job, card);
      console.log(JSON.stringify({ output: card.output, ok: true }));
    } catch (err) {
      failures += 1;
      console.log(JSON.stringify({ output: card.output, ok: false, error: String(err) }));
    }
  }
  process.exit(failures ? 1 : 0);
}

main();
