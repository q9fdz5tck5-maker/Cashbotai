'use strict';
// Renders project.json -> a single self-contained deck.html.
//
// The original decks were 50-96KB of hand-written HTML per webinar, which is
// why each one needed its own bespoke build script. Here the slides are data
// and the layouts are shared, so one renderer serves every deck.
//
// Capture contract (src/capture.js depends on this):
//   - every slide is <section class="slide" id="...">
//   - the active slide carries class "active"
//   - nothing animates in; slides are static and screenshot-ready

const esc = (s) => String(s == null ? '' : s)
  .replace(/&/g, '&amp;')
  .replace(/</g, '&lt;')
  .replace(/>/g, '&gt;')
  .replace(/"/g, '&quot;');

// [ACCENT]highlighted[/ACCENT] -> a coloured span. Kept from the original decks.
const rich = (s) => esc(s)
  .replace(/\[ACCENT\]/g, '<span class="accent">')
  .replace(/\[\/ACCENT\]/g, '</span>')
  .replace(/\n/g, '<br>');

const layouts = {
  title: (s) => `
    <div class="wrap center">
      ${s.kicker ? `<div class="kicker">${esc(s.kicker)}</div>` : ''}
      <h1>${rich(s.headline)}</h1>
      ${s.sub ? `<p class="sub">${rich(s.sub)}</p>` : ''}
    </div>`,

  bullets: (s) => `
    <div class="wrap">
      ${s.kicker ? `<div class="kicker">${esc(s.kicker)}</div>` : ''}
      <h2>${rich(s.headline)}</h2>
      <ul class="bullets">
        ${(s.bullets || []).map((b) => `<li>${rich(b)}</li>`).join('\n        ')}
      </ul>
    </div>`,

  stats: (s) => `
    <div class="wrap center">
      ${s.kicker ? `<div class="kicker">${esc(s.kicker)}</div>` : ''}
      <h2>${rich(s.headline)}</h2>
      <div class="stats">
        ${(s.stats || []).map((st) => `
        <div class="stat">
          <div class="stat-value">${rich(st.value)}</div>
          <div class="stat-label">${rich(st.label)}</div>
        </div>`).join('')}
      </div>
    </div>`,

  compare: (s) => `
    <div class="wrap">
      ${s.kicker ? `<div class="kicker">${esc(s.kicker)}</div>` : ''}
      <h2>${rich(s.headline)}</h2>
      <div class="compare">
        ${['left', 'right'].map((side) => {
          const col = s[side] || {};
          return `
        <div class="col ${side === 'right' ? 'col-win' : 'col-lose'}">
          <div class="col-title">${rich(col.title)}</div>
          <ul>${(col.items || []).map((i) => `<li>${rich(i)}</li>`).join('')}</ul>
          ${col.total ? `<div class="col-total">${rich(col.total)}</div>` : ''}
        </div>`;
        }).join('')}
      </div>
    </div>`,

  quote: (s) => `
    <div class="wrap center">
      <blockquote>${rich(s.quote)}</blockquote>
      ${s.attribution ? `<div class="attribution">${rich(s.attribution)}</div>` : ''}
    </div>`,

  pricing: (s) => `
    <div class="wrap">
      ${s.kicker ? `<div class="kicker">${esc(s.kicker)}</div>` : ''}
      <h2>${rich(s.headline)}</h2>
      <div class="tiers">
        ${(s.tiers || []).map((t) => `
        <div class="tier${t.featured ? ' featured' : ''}">
          <div class="tier-name">${rich(t.name)}</div>
          <div class="tier-price">${rich(t.price)}</div>
          ${t.was ? `<div class="tier-was">${rich(t.was)}</div>` : ''}
          <ul>${(t.features || []).map((f) => `<li>${rich(f)}</li>`).join('')}</ul>
        </div>`).join('')}
      </div>
      ${s.footnote ? `<p class="footnote">${rich(s.footnote)}</p>` : ''}
    </div>`,

  faq: (s) => `
    <div class="wrap">
      ${s.kicker ? `<div class="kicker">${esc(s.kicker)}</div>` : ''}
      <h2>${rich(s.headline)}</h2>
      <div class="faq">
        ${(s.items || []).map((i) => `
        <div class="qa">
          <div class="q">${rich(i.q)}</div>
          <div class="a">${rich(i.a)}</div>
        </div>`).join('')}
      </div>
    </div>`,

  cta: (s) => `
    <div class="wrap center">
      ${s.kicker ? `<div class="kicker">${esc(s.kicker)}</div>` : ''}
      <h1>${rich(s.headline)}</h1>
      ${s.sub ? `<p class="sub">${rich(s.sub)}</p>` : ''}
      ${s.button ? `<div class="cta-btn">${rich(s.button)}</div>` : ''}
      ${s.url ? `<div class="cta-url">${rich(s.url)}</div>` : ''}
      ${s.footnote ? `<p class="footnote">${rich(s.footnote)}</p>` : ''}
    </div>`,
};

function css(cfg) {
  const b = cfg.brand || {};
  const accent = b.accent || '#f5c518';
  const bg = b.background || '#07080b';
  const text = b.text || '#f2f4f8';
  const muted = b.muted || '#8b93a3';
  const font = b.font || "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif";
  const mono = b.monoFont || "'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, monospace";
  const { width, height } = cfg.video;

  return `
  *{box-sizing:border-box;margin:0;padding:0}
  html,body{background:${bg};color:${text};font-family:${font};width:${width}px;height:${height}px;overflow:hidden}
  .slide{position:absolute;inset:0;display:none;padding:96px 120px;
    background:radial-gradient(ellipse at 50% -20%, rgba(255,255,255,.06), transparent 60%), ${bg}}
  .slide.active{display:flex;align-items:center}
  .wrap{width:100%}
  .center{text-align:center}
  .kicker{font-family:${mono};font-size:22px;letter-spacing:.22em;text-transform:uppercase;
    color:${accent};margin-bottom:28px}
  h1{font-size:82px;line-height:1.08;font-weight:800;letter-spacing:-.02em}
  h2{font-size:60px;line-height:1.12;font-weight:800;letter-spacing:-.015em;margin-bottom:44px}
  .accent{color:${accent}}
  .sub{font-size:32px;line-height:1.45;color:${muted};margin-top:32px;max-width:1180px;
    margin-left:auto;margin-right:auto}
  .bullets{list-style:none;display:flex;flex-direction:column;gap:26px}
  .bullets li{font-size:34px;line-height:1.4;padding-left:52px;position:relative}
  .bullets li::before{content:'';position:absolute;left:0;top:.55em;width:22px;height:3px;background:${accent}}
  .stats{display:flex;gap:56px;justify-content:center;flex-wrap:wrap;margin-top:24px}
  .stat{background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.09);
    border-radius:18px;padding:40px 52px;min-width:280px}
  .stat-value{font-family:${mono};font-size:66px;font-weight:800;color:${accent}}
  .stat-label{font-size:22px;color:${muted};margin-top:12px;line-height:1.35}
  .compare{display:flex;gap:40px}
  .col{flex:1;border-radius:18px;padding:40px;border:1px solid rgba(255,255,255,.09);
    background:rgba(255,255,255,.03)}
  .col-win{border-color:${accent};background:rgba(245,197,24,.07)}
  .col-title{font-family:${mono};font-size:24px;letter-spacing:.12em;text-transform:uppercase;
    margin-bottom:28px;color:${muted}}
  .col-win .col-title{color:${accent}}
  .col ul{list-style:none;display:flex;flex-direction:column;gap:18px}
  .col li{font-size:27px;line-height:1.35}
  .col-total{margin-top:30px;padding-top:26px;border-top:1px solid rgba(255,255,255,.14);
    font-family:${mono};font-size:38px;font-weight:800}
  blockquote{font-size:56px;line-height:1.25;font-weight:700;max-width:1400px;margin:0 auto}
  .attribution{font-family:${mono};font-size:24px;color:${muted};margin-top:38px}
  .tiers{display:flex;gap:32px}
  .tier{flex:1;border:1px solid rgba(255,255,255,.1);border-radius:18px;padding:38px;
    background:rgba(255,255,255,.03)}
  .tier.featured{border-color:${accent};background:rgba(245,197,24,.08)}
  .tier-name{font-family:${mono};font-size:22px;letter-spacing:.14em;text-transform:uppercase;color:${muted}}
  .tier-price{font-size:64px;font-weight:800;margin:16px 0 4px;color:${accent}}
  .tier-was{font-size:22px;color:${muted};text-decoration:line-through;margin-bottom:22px}
  .tier ul{list-style:none;display:flex;flex-direction:column;gap:13px;margin-top:20px}
  .tier li{font-size:22px;line-height:1.35;color:${text}}
  .faq{display:flex;flex-direction:column;gap:32px}
  .qa .q{font-size:32px;font-weight:700;margin-bottom:10px}
  .qa .a{font-size:26px;line-height:1.45;color:${muted}}
  .cta-btn{display:inline-block;margin-top:44px;background:${accent};color:#000;font-weight:800;
    font-size:38px;padding:26px 62px;border-radius:14px}
  .cta-url{font-family:${mono};font-size:32px;color:${muted};margin-top:28px}
  .footnote{font-size:20px;color:${muted};margin-top:34px;line-height:1.4}
  .brandmark{position:absolute;bottom:44px;left:120px;font-family:${mono};font-size:19px;
    color:${muted};letter-spacing:.1em}
  .slideno{position:absolute;bottom:44px;right:120px;font-family:${mono};font-size:19px;color:${muted}}
  `;
}

function render(cfg) {
  const b = cfg.brand || {};
  const slides = cfg.slides.map((s) => {
    const body = layouts[s.layout](s);
    return `<section class="slide" id="${esc(s.id)}">
      ${body}
      ${b.product ? `<div class="brandmark">${esc(b.product)}</div>` : ''}
      <div class="slideno">${s.index} / ${cfg.slides.length}</div>
    </section>`;
  }).join('\n');

  return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>${esc(cfg.title || cfg.name)}</title>
<style>${css(cfg)}</style>
</head>
<body>
${slides}
<script>
  // Capture driver. capture.js calls showSlide(id) over CDP; the ?slide= param
  // is only so a human can eyeball one slide in a browser.
  function showSlide(id) {
    document.querySelectorAll('.slide.active').forEach(function (el) {
      el.classList.remove('active');
    });
    var el = document.getElementById(id);
    if (el) el.classList.add('active');
    return !!el;
  }
  var params = new URLSearchParams(location.search);
  var first = params.get('slide') || document.querySelector('.slide').id;
  showSlide(first);
</script>
</body>
</html>`;
}

module.exports = { render, layouts };
