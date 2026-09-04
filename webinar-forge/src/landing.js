'use strict';
// Renders the sales landing page from the same project.json that builds the
// webinar. Sections are data, exactly like slides — so a page is edited by
// changing JSON, never by hand-writing 1,300 lines of HTML per campaign.
//
// Output is one self-contained .html file (inline CSS/JS, no build step, no
// CDN) that sits next to the rendered webinar.mp4 in dist/.

const esc = (s) => String(s == null ? '' : s)
  .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  .replace(/"/g, '&quot;');

const rich = (s) => esc(s)
  .replace(/\[ACCENT\]/g, '<span class="accent">')
  .replace(/\[\/ACCENT\]/g, '</span>')
  .replace(/\n/g, '<br>');

const btn = (cta, cls = 'btn') => {
  if (!cta) return '';
  const label = rich(cta.label || 'Get Access');
  const note = cta.note ? `<div class="btn-note">${rich(cta.note)}</div>` : '';
  // A configured href wins; otherwise the button scrolls to the offer.
  const href = cta.href || '#offer';
  return `<div class="btn-wrap"><a class="${cls}" href="${esc(href)}">${label}</a>${note}</div>`;
};

const sections = {
  // Hero doubles as the video player. gate:true hides the video behind a
  // one-field opt-in that POSTs to /register.
  hero: (s, cfg) => `
    <section class="hero">
      <div class="inner">
        ${s.kicker ? `<div class="kicker">${esc(s.kicker)}</div>` : ''}
        <h1>${rich(s.headline)}</h1>
        ${s.sub ? `<p class="lede">${rich(s.sub)}</p>` : ''}
        ${s.video === false ? '' : `
        <div class="video-block" id="watch">
          ${s.gate ? `
          <form class="gate" id="gate">
            <div class="gate-title">${rich(s.gateTitle || 'Watch the free training')}</div>
            <div class="gate-row">
              <input type="email" name="email" required placeholder="${esc(s.gatePlaceholder || 'you@company.com')}" aria-label="Email address">
              <button type="submit">${esc(s.gateButton || 'Watch Now')}</button>
            </div>
            <div class="gate-note">${rich(s.gateNote || 'No spam. Unsubscribe any time.')}</div>
            <div class="gate-error" id="gate-error" hidden></div>
          </form>
          <video id="player" controls preload="metadata" hidden
                 ${s.poster ? `poster="${esc(s.poster)}"` : ''}
                 src="${esc(cfg.__videoSrc)}"></video>
          ` : `
          <video id="player" controls preload="metadata"
                 ${s.poster ? `poster="${esc(s.poster)}"` : ''}
                 src="${esc(cfg.__videoSrc)}"></video>
          `}
        </div>`}
        ${btn(s.cta, 'btn btn-lg')}
      </div>
    </section>`,

  proof: (s) => `
    <section class="band proof">
      <div class="inner">
        ${s.headline ? `<h2>${rich(s.headline)}</h2>` : ''}
        <div class="proof-row">
          ${(s.stats || []).map((st) => `
          <div class="proof-item">
            <div class="proof-value">${rich(st.value)}</div>
            <div class="proof-label">${rich(st.label)}</div>
          </div>`).join('')}
        </div>
      </div>
    </section>`,

  problem: (s) => `
    <section class="band">
      <div class="inner narrow">
        ${s.kicker ? `<div class="kicker">${esc(s.kicker)}</div>` : ''}
        <h2>${rich(s.headline)}</h2>
        ${s.body ? `<p class="body">${rich(s.body)}</p>` : ''}
        <ul class="pain">
          ${(s.points || []).map((p) => `<li>${rich(p)}</li>`).join('')}
        </ul>
      </div>
    </section>`,

  features: (s) => `
    <section class="band">
      <div class="inner">
        ${s.kicker ? `<div class="kicker">${esc(s.kicker)}</div>` : ''}
        <h2>${rich(s.headline)}</h2>
        <div class="cards">
          ${(s.items || []).map((it, i) => `
          <div class="card">
            <div class="card-num">${String(i + 1).padStart(2, '0')}</div>
            <div class="card-title">${rich(it.title)}</div>
            <div class="card-body">${rich(it.body)}</div>
          </div>`).join('')}
        </div>
      </div>
    </section>`,

  // The value stack: line items with prices, a struck-through total, then the
  // real price. Anchor before reveal.
  stack: (s) => `
    <section class="band" id="offer">
      <div class="inner narrow">
        ${s.kicker ? `<div class="kicker">${esc(s.kicker)}</div>` : ''}
        <h2>${rich(s.headline)}</h2>
        <div class="stack">
          ${(s.items || []).map((it) => `
          <div class="stack-row">
            <div class="stack-name">${rich(it.name)}</div>
            <div class="stack-value">${rich(it.value)}</div>
          </div>`).join('')}
          ${s.totalValue ? `
          <div class="stack-row stack-total">
            <div class="stack-name">${rich(s.totalLabel || 'Total value')}</div>
            <div class="stack-value struck">${rich(s.totalValue)}</div>
          </div>` : ''}
        </div>
        ${s.price ? `
        <div class="price-reveal">
          <div class="price-label">${rich(s.priceLabel || 'Your price today')}</div>
          <div class="price">${rich(s.price)}</div>
          ${s.priceNote ? `<div class="price-note">${rich(s.priceNote)}</div>` : ''}
        </div>` : ''}
        ${btn(s.cta, 'btn btn-lg')}
      </div>
    </section>`,

  pricing: (s) => `
    <section class="band" id="pricing">
      <div class="inner">
        ${s.kicker ? `<div class="kicker">${esc(s.kicker)}</div>` : ''}
        <h2>${rich(s.headline)}</h2>
        <div class="tiers">
          ${(s.tiers || []).map((t) => `
          <div class="tier${t.featured ? ' featured' : ''}">
            ${t.featured && t.badge ? `<div class="tier-badge">${esc(t.badge)}</div>` : ''}
            <div class="tier-name">${rich(t.name)}</div>
            <div class="tier-price">${rich(t.price)}</div>
            ${t.was ? `<div class="tier-was">${rich(t.was)}</div>` : ''}
            <ul>${(t.features || []).map((f) => `<li>${rich(f)}</li>`).join('')}</ul>
            ${t.cta ? `<a class="btn btn-tier" href="${esc(t.cta.href || '#')}">${rich(t.cta.label || 'Choose')}</a>` : ''}
          </div>`).join('')}
        </div>
        ${s.footnote ? `<p class="footnote">${rich(s.footnote)}</p>` : ''}
      </div>
    </section>`,

  testimonials: (s) => `
    <section class="band">
      <div class="inner">
        ${s.headline ? `<h2>${rich(s.headline)}</h2>` : ''}
        <div class="quotes">
          ${(s.items || []).map((q) => `
          <figure class="quote">
            <blockquote>${rich(q.quote)}</blockquote>
            <figcaption>${rich(q.name)}${q.role ? `<span>${rich(q.role)}</span>` : ''}</figcaption>
          </figure>`).join('')}
        </div>
        ${s.disclaimer ? `<p class="footnote">${rich(s.disclaimer)}</p>` : ''}
      </div>
    </section>`,

  faq: (s) => `
    <section class="band">
      <div class="inner narrow">
        ${s.kicker ? `<div class="kicker">${esc(s.kicker)}</div>` : ''}
        <h2>${rich(s.headline)}</h2>
        <div class="faq">
          ${(s.items || []).map((i) => `
          <details>
            <summary>${rich(i.q)}</summary>
            <div class="answer">${rich(i.a)}</div>
          </details>`).join('')}
        </div>
      </div>
    </section>`,

  // Risk reversal. The terms are the operator's to write and to honour — this
  // renderer never supplies a default policy, because a guarantee nobody
  // intends to pay out is a refund dispute wearing a conversion-rate costume.
  // Omitting the section is the correct state when there is no real policy.
  guarantee: (s) => `
    <section class="band">
      <div class="inner narrow center">
        ${s.kicker ? `<div class="kicker">${esc(s.kicker)}</div>` : ''}
        <div class="guarantee">
          ${s.badge ? `<div class="guarantee-badge">${rich(s.badge)}</div>` : ''}
          <h2>${rich(s.headline)}</h2>
          ${s.body ? `<p class="lede">${rich(s.body)}</p>` : ''}
          ${(s.terms || []).length ? `
          <ul class="guarantee-terms">
            ${(s.terms || []).map((t) => `<li>${rich(t)}</li>`).join('')}
          </ul>` : ''}
        </div>
        ${btn(s.cta, 'btn btn-lg')}
        ${s.footnote ? `<p class="footnote">${rich(s.footnote)}</p>` : ''}
      </div>
    </section>`,

  // Honest scarcity: counts down to one real timestamp in `until` (ISO 8601).
  // There is deliberately no evergreen mode. A timer that restarts for each
  // visitor states something false about availability, and it is precisely the
  // pattern that gets a page reported — so this renders a real deadline or it
  // renders no clock at all. After the date passes it shows `expiredText`
  // rather than looping.
  deadline: (s) => `
    <section class="band band-deadline">
      <div class="inner narrow center">
        ${s.kicker ? `<div class="kicker">${esc(s.kicker)}</div>` : ''}
        <h2>${rich(s.headline)}</h2>
        ${s.reason ? `<p class="lede">${rich(s.reason)}</p>` : ''}
        ${s.until ? `<div class="countdown" data-until="${esc(s.until)}" data-expired="${esc(s.expiredText || 'Enrolment for this round has closed.')}" hidden></div>` : ''}
        ${btn(s.cta, 'btn btn-lg')}
        ${s.footnote ? `<p class="footnote">${rich(s.footnote)}</p>` : ''}
      </div>
    </section>`,

  cta: (s) => `
    <section class="band band-cta">
      <div class="inner narrow center">
        ${s.kicker ? `<div class="kicker">${esc(s.kicker)}</div>` : ''}
        <h2>${rich(s.headline)}</h2>
        ${s.sub ? `<p class="lede">${rich(s.sub)}</p>` : ''}
        ${btn(s.cta, 'btn btn-lg')}
        ${s.footnote ? `<p class="footnote">${rich(s.footnote)}</p>` : ''}
      </div>
    </section>`,
};

function css(cfg) {
  const b = cfg.brand || {};
  const accent = b.accent || '#f5c518';
  const bg = b.background || '#07080b';
  const text = b.text || '#f2f4f8';
  const muted = b.muted || '#8b93a3';
  const font = b.font || "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif";
  const mono = b.monoFont || "ui-monospace, SFMono-Regular, Menlo, monospace";

  return `
  *{box-sizing:border-box;margin:0;padding:0}
  html{scroll-behavior:smooth}
  body{background:${bg};color:${text};font-family:${font};line-height:1.55;
    -webkit-font-smoothing:antialiased}
  img,video{max-width:100%;display:block}
  /* Author display:block outranks the UA stylesheet's [hidden]{display:none},
     which would otherwise leak the gated video before opt-in. */
  [hidden]{display:none!important}
  .inner{max-width:1120px;margin:0 auto;padding:0 24px}
  .inner.narrow{max-width:820px}
  .center{text-align:center}
  .accent{color:${accent}}
  .kicker{font-family:${mono};font-size:13px;letter-spacing:.2em;text-transform:uppercase;
    color:${accent};margin-bottom:18px}
  h1{font-size:clamp(34px,5.6vw,64px);line-height:1.08;font-weight:800;letter-spacing:-.02em}
  h2{font-size:clamp(27px,3.6vw,42px);line-height:1.15;font-weight:800;
    letter-spacing:-.015em;margin-bottom:28px}
  .lede{font-size:clamp(17px,2vw,22px);color:${muted};margin-top:20px;max-width:760px}
  .hero{padding:88px 0 64px;text-align:center;
    background:radial-gradient(ellipse at 50% -10%, rgba(255,255,255,.07), transparent 60%)}
  .hero .lede{margin-left:auto;margin-right:auto}
  .band{padding:72px 0;border-top:1px solid rgba(255,255,255,.07)}
  .band-cta{background:linear-gradient(180deg, rgba(245,197,24,.07), transparent)}
  .body{font-size:18px;color:${muted};margin-bottom:26px}

  .video-block{margin:40px auto 0;max-width:940px}
  video{width:100%;border-radius:14px;border:1px solid rgba(255,255,255,.12);background:#000;
    aspect-ratio:16/9}
  .gate{background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.12);
    border-radius:14px;padding:34px 26px}
  .gate-title{font-size:22px;font-weight:700;margin-bottom:18px}
  .gate-row{display:flex;gap:10px;max-width:520px;margin:0 auto;flex-wrap:wrap}
  .gate input{flex:1 1 240px;min-width:0;padding:15px 16px;font-size:16px;border-radius:10px;
    border:1px solid rgba(255,255,255,.18);background:rgba(0,0,0,.35);color:${text};font-family:inherit}
  .gate input:focus{outline:2px solid ${accent};outline-offset:1px}
  .gate button{padding:15px 26px;font-size:16px;font-weight:800;border:0;border-radius:10px;
    background:${accent};color:#000;cursor:pointer;font-family:inherit}
  .gate-note{font-size:13px;color:${muted};margin-top:14px}
  .gate-error{color:#ff5c7a;font-size:14px;margin-top:12px}

  .btn-wrap{margin-top:34px}
  .btn{display:inline-block;background:${accent};color:#000;font-weight:800;
    text-decoration:none;border-radius:12px;padding:17px 40px;font-size:18px}
  .btn-lg{padding:21px 52px;font-size:21px}
  .btn-tier{margin-top:22px;width:100%;text-align:center;padding:14px 20px;font-size:16px}
  .btn-note{font-size:14px;color:${muted};margin-top:14px}

  .proof-row{display:flex;flex-wrap:wrap;gap:22px;justify-content:center}
  .proof-item{flex:1 1 190px;background:rgba(255,255,255,.04);
    border:1px solid rgba(255,255,255,.09);border-radius:14px;padding:26px 20px;text-align:center}
  .proof-value{font-family:${mono};font-size:36px;font-weight:800;color:${accent}}
  .proof-label{font-size:14px;color:${muted};margin-top:8px}

  .pain{list-style:none;display:flex;flex-direction:column;gap:14px}
  .pain li{font-size:18px;padding-left:34px;position:relative;color:${text}}
  .pain li::before{content:'✕';position:absolute;left:0;color:#ff5c7a;font-weight:700}

  .cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:22px}
  .card{background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.09);
    border-radius:16px;padding:30px}
  .card-num{font-family:${mono};font-size:13px;color:${accent};letter-spacing:.16em;margin-bottom:14px}
  .card-title{font-size:21px;font-weight:700;margin-bottom:10px}
  .card-body{color:${muted};font-size:16px}

  .stack{border:1px solid rgba(255,255,255,.11);border-radius:16px;overflow:hidden}
  .stack-row{display:flex;justify-content:space-between;gap:18px;padding:17px 22px;
    border-bottom:1px solid rgba(255,255,255,.07);font-size:17px}
  .stack-row:last-child{border-bottom:0}
  .stack-value{font-family:${mono};color:${accent};white-space:nowrap}
  .stack-total{background:rgba(255,255,255,.04);font-weight:800}
  .struck{text-decoration:line-through;color:${muted}}
  .price-reveal{text-align:center;margin-top:38px}
  .price-label{font-family:${mono};font-size:13px;letter-spacing:.18em;
    text-transform:uppercase;color:${muted}}
  .price{font-size:clamp(48px,8vw,84px);font-weight:800;color:${accent};line-height:1.05;margin-top:10px}
  .price-note{color:${muted};margin-top:12px}

  .tiers{display:grid;grid-template-columns:repeat(auto-fit,minmax(270px,1fr));gap:22px}
  .tier{position:relative;background:rgba(255,255,255,.04);
    border:1px solid rgba(255,255,255,.1);border-radius:16px;padding:32px;
    display:flex;flex-direction:column}
  .tier.featured{border-color:${accent};background:rgba(245,197,24,.08)}
  .tier-badge{position:absolute;top:-13px;left:50%;transform:translateX(-50%);
    background:${accent};color:#000;font-size:12px;font-weight:800;letter-spacing:.1em;
    text-transform:uppercase;padding:5px 15px;border-radius:20px;white-space:nowrap}
  .tier-name{font-family:${mono};font-size:13px;letter-spacing:.16em;
    text-transform:uppercase;color:${muted}}
  .tier-price{font-size:46px;font-weight:800;color:${accent};margin:12px 0 2px}
  .tier-was{color:${muted};text-decoration:line-through;font-size:15px}
  .tier ul{list-style:none;margin-top:20px;display:flex;flex-direction:column;gap:11px;flex:1}
  .tier li{font-size:15px;padding-left:26px;position:relative;color:${text}}
  .tier li::before{content:'✓';position:absolute;left:0;color:${accent};font-weight:700}

  .quotes{display:grid;grid-template-columns:repeat(auto-fit,minmax(290px,1fr));gap:22px}
  .quote{background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.09);
    border-radius:16px;padding:28px}
  .quote blockquote{font-size:17px;line-height:1.5}
  .quote figcaption{margin-top:18px;font-family:${mono};font-size:13px;color:${accent}}
  .quote figcaption span{display:block;color:${muted};margin-top:4px}

  .faq details{border-bottom:1px solid rgba(255,255,255,.09);padding:20px 0}
  .faq summary{font-size:19px;font-weight:700;cursor:pointer;list-style:none;
    display:flex;justify-content:space-between;gap:16px;align-items:center}
  .faq summary::-webkit-details-marker{display:none}
  .faq summary::after{content:'+';color:${accent};font-size:26px;line-height:1;flex:none}
  .faq details[open] summary::after{content:'−'}
  .faq .answer{color:${muted};font-size:17px;margin-top:12px}

  .footnote{font-size:14px;color:${muted};margin-top:26px;line-height:1.5}
  footer{padding:48px 0;border-top:1px solid rgba(255,255,255,.07);
    color:${muted};font-size:14px;text-align:center}
  footer p{max-width:760px;margin:0 auto 10px}
  .guarantee{border:1px solid ${accent}55;border-radius:16px;padding:36px 28px;background:#ffffff05;margin-bottom:28px}
  .guarantee-badge{display:inline-block;border:2px solid ${accent};color:${accent};border-radius:999px;
    padding:8px 20px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;font-size:.78rem;margin-bottom:18px}
  .guarantee h2{margin:0 0 12px}
  .guarantee-terms{list-style:none;padding:0;margin:20px auto 0;max-width:38rem;text-align:left}
  .guarantee-terms li{position:relative;padding:8px 0 8px 30px;color:${muted};line-height:1.55}
  .guarantee-terms li:before{content:"";position:absolute;left:6px;top:.95em;width:10px;height:2px;background:${accent}}
  .band-deadline{border-top:1px solid ${accent}33;border-bottom:1px solid ${accent}33}
  .countdown{display:flex;gap:14px;justify-content:center;flex-wrap:wrap;margin:22px 0 26px}
  .countdown .unit{min-width:84px;border:1px solid #ffffff1a;border-radius:12px;padding:14px 10px;background:#ffffff08}
  .countdown .num{display:block;font-size:2.1rem;font-weight:800;line-height:1;color:${accent};
    font-variant-numeric:tabular-nums}
  .countdown .lbl{display:block;margin-top:6px;font-size:.72rem;letter-spacing:.12em;text-transform:uppercase;color:${muted}}
  .countdown.expired{font-size:1.05rem;color:${muted}}
  @media(max-width:640px){.band{padding:52px 0}.hero{padding:60px 0 44px}
    .guarantee{padding:26px 18px}.countdown .unit{min-width:68px}.countdown .num{font-size:1.6rem}}
  `;
}

function render(cfg) {
  const L = cfg.landing || {};
  const list = Array.isArray(L.sections) ? L.sections : [];

  const unknown = list.map((s) => s.type).filter((t) => !sections[t]);
  if (unknown.length) {
    throw new Error(
      `Unknown landing section type(s): ${[...new Set(unknown)].join(', ')}.\n` +
      `Known: ${Object.keys(sections).join(', ')}`
    );
  }

  cfg.__videoSrc = L.videoSrc || `${cfg.name}.mp4`;
  const body = list.map((s) => sections[s.type](s, cfg)).join('\n');
  const gated = list.some((s) => s.type === 'hero' && s.gate);
  const counting = list.some((s) => s.type === 'deadline' && s.until);

  return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>${esc(L.title || cfg.title || cfg.name)}</title>
${L.description ? `<meta name="description" content="${esc(L.description)}">` : ''}
<meta property="og:title" content="${esc(L.title || cfg.title || cfg.name)}">
${L.description ? `<meta property="og:description" content="${esc(L.description)}">` : ''}
<meta property="og:type" content="website">
<style>${css(cfg)}</style>
</head>
<body>
${body}
<footer>
  <div class="inner">
    ${(L.footer || []).map((p) => `<p>${rich(p)}</p>`).join('')}
    <p>&copy; ${new Date().getFullYear()} ${esc((cfg.brand || {}).product || cfg.name)}</p>
  </div>
</footer>
${gated ? `<script>
(function () {
  var form = document.getElementById('gate');
  var player = document.getElementById('player');
  var err = document.getElementById('gate-error');
  if (!form) return;

  function reveal() {
    form.hidden = true;
    player.hidden = false;
    try { player.play(); } catch (e) {}
  }

  // Returning visitors skip the gate.
  try { if (localStorage.getItem('wf_registered')) reveal(); } catch (e) {}

  form.addEventListener('submit', function (ev) {
    ev.preventDefault();
    err.hidden = true;
    var email = form.elements.email.value.trim();
    fetch('/register', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: email, page: location.pathname })
    }).then(function (r) {
      if (!r.ok) throw new Error('register failed');
      try { localStorage.setItem('wf_registered', '1'); } catch (e) {}
      reveal();
    }).catch(function () {
      // Never trap the viewer behind a broken endpoint: show the video,
      // and say the signup did not save.
      err.textContent = 'We could not save your email, but the training is unlocked.';
      err.hidden = false;
      reveal();
    });
  });
})();
</script>` : ''}
${counting ? `<script>
// Counts down to the real timestamp in data-until. When it passes, the clock
// is replaced by data-expired — it never loops back round, because a timer
// that restarts per visitor claims something untrue about availability.
(function () {
  var els = document.querySelectorAll('.countdown[data-until]');
  if (!els.length) return;

  function pad(n) { return (n < 10 ? '0' : '') + n; }
  function unit(n, label) {
    return '<span class="unit"><span class="num">' + pad(n) + '</span>' +
           '<span class="lbl">' + label + '</span></span>';
  }

  function tick() {
    var now = Date.now();
    for (var i = 0; i < els.length; i++) {
      var el = els[i];
      var end = Date.parse(el.getAttribute('data-until'));
      if (isNaN(end)) { el.hidden = true; continue; }
      el.hidden = false;
      var left = Math.floor((end - now) / 1000);
      if (left <= 0) {
        el.className = 'countdown expired';
        el.textContent = el.getAttribute('data-expired') || '';
        continue;
      }
      var d = Math.floor(left / 86400);
      var h = Math.floor((left % 86400) / 3600);
      var m = Math.floor((left % 3600) / 60);
      var s = left % 60;
      el.innerHTML = (d > 0 ? unit(d, 'days') : '') +
        unit(h, 'hours') + unit(m, 'minutes') + unit(s, 'seconds');
    }
  }

  tick();
  setInterval(tick, 1000);
})();
</script>` : ''}
</body>
</html>`;
}

module.exports = { render, sections };
