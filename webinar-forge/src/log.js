'use strict';

const t0 = Date.now();
const stamp = () => {
  const s = (Date.now() - t0) / 1000;
  return String(s.toFixed(1)).padStart(6) + 's';
};

const info = (msg) => console.log(`[${stamp()}] ${msg}`);
const step = (msg) => console.log(`\n[${stamp()}] === ${msg} ===\n`);
const warn = (msg) => console.warn(`[${stamp()}] WARN  ${msg}`);
const fail = (msg) => console.error(`[${stamp()}] ERROR ${msg}`);
const ok = (msg) => console.log(`[${stamp()}] ok    ${msg}`);

module.exports = { info, step, warn, fail, ok };
