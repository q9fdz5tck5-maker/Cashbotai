'use strict';
// What $1,000,000 actually requires from this funnel.
// Conversion inputs are INDUSTRY-TYPICAL RANGES used as illustrative
// assumptions. They are not measured figures for this product - nothing has
// been sold through this funnel yet, so there is no real data to use.

const TARGET = 1_000_000;

const fmt = (n) => n.toLocaleString('en-US', { maximumFractionDigits: 0 });
const money = (n) => '$' + n.toLocaleString('en-US', { maximumFractionDigits: 2 });

function aov({ core, bump = 0, bumpRate = 0, upsell = 0, upsellRate = 0, high = 0, highRate = 0 }) {
  return core + bump * bumpRate + upsell * upsellRate + high * highRate;
}

function funnel(label, offer, { regToBuy, visitToReg }) {
  const a = aov(offer);
  const customers = TARGET / a;
  const registrants = customers / regToBuy;
  const visitors = registrants / visitToReg;
  return { label, a, customers, registrants, visitors };
}

// --- conversion assumptions (illustrative, mid-range for automated webinars)
const CONV = { regToBuy: 0.02, visitToReg: 0.30 };

const scenarios = [
  ['Today: $297, nothing else', { core: 297 }],
  ['+ $97 order bump @ 35%', { core: 297, bump: 97, bumpRate: 0.35 }],
  ['+ $997 upsell @ 15%', { core: 297, bump: 97, bumpRate: 0.35, upsell: 997, upsellRate: 0.15 }],
  ['+ $2,000 high-ticket @ 3%', { core: 297, bump: 97, bumpRate: 0.35, upsell: 997, upsellRate: 0.15, high: 2000, highRate: 0.03 }],
  ['Reprice core to $997, no ladder', { core: 997 }],
  ['$997 core + full ladder', { core: 997, bump: 197, bumpRate: 0.35, upsell: 1997, upsellRate: 0.15 }],
];

console.log(`TARGET: ${money(TARGET)}`);
console.log(`Assumed: ${(CONV.regToBuy * 100).toFixed(1)}% of registrants buy, ${(CONV.visitToReg * 100).toFixed(0)}% of visitors register\n`);
console.log('scenario'.padEnd(34) + 'AOV'.padStart(10) + 'customers'.padStart(11) + 'registrants'.padStart(13) + 'visitors'.padStart(11));
console.log('-'.repeat(79));
const rows = scenarios.map(([l, o]) => funnel(l, o, CONV));
for (const r of rows) {
  console.log(
    r.label.padEnd(34) +
    money(Math.round(r.a)).padStart(10) +
    fmt(Math.ceil(r.customers)).padStart(11) +
    fmt(Math.ceil(r.registrants)).padStart(13) +
    fmt(Math.ceil(r.visitors)).padStart(11)
  );
}

const base = rows[0];
console.log('\n--- traffic saved vs today ---');
for (const r of rows.slice(1)) {
  const cut = (1 - r.visitors / base.visitors) * 100;
  console.log(`  ${r.label.padEnd(34)} ${cut.toFixed(0)}% less traffic for the same ${money(TARGET)}`);
}

// --- the SMS throughput ceiling -------------------------------------------
console.log('\n=== the "Text To Buy" ceiling ===');
console.log('Every sale currently requires a human text conversation.');
for (const completion of [0.7, 0.5, 0.3]) {
  const convos = base.customers / completion;
  for (const perDay of [20, 50]) {
    const days = convos / perDay;
    console.log(
      `  ${(completion * 100).toFixed(0)}% of texters end up buying, ${perDay} conversations/day` +
      ` -> ${fmt(Math.ceil(convos))} conversations, ${fmt(Math.ceil(days))} days (${(days / 365).toFixed(1)} yrs)`
    );
  }
}
