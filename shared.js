// ── Shared state across all pages (via sessionStorage) ─────────────────────
const Store = {
    get: (k, def) => { try { return JSON.parse(sessionStorage.getItem('vault_'+k)) ?? def; } catch { return def; } },
    set: (k, v) => sessionStorage.setItem('vault_' + k, JSON.stringify(v)),
    inc: (k, by = 1) => Store.set(k, (Store.get(k, 0) + by)),
};

// ── Particle background ────────────────────────────────────────────────────
(function initParticles() {
    const canvas = document.getElementById('particles');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    let W, H, pts = [];

    function resize() { W = canvas.width = window.innerWidth; H = canvas.height = window.innerHeight; }

    function init() {
        pts = Array.from({ length: 70 }, () => ({
            x: Math.random() * W, y: Math.random() * H,
            r: Math.random() * 1.2 + 0.3,
            vx: (Math.random() - 0.5) * 0.25,
            vy: (Math.random() - 0.5) * 0.25,
            a: Math.random() * 0.4 + 0.1
        }));
    }

    function draw() {
        ctx.clearRect(0, 0, W, H);
        pts.forEach(p => {
            p.x = (p.x + p.vx + W) % W;
            p.y = (p.y + p.vy + H) % H;
            ctx.beginPath();
            ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
            ctx.fillStyle = `rgba(96,165,250,${p.a})`;
            ctx.fill();
        });
        pts.forEach((a, i) => pts.slice(i + 1).forEach(b => {
            const d = Math.hypot(a.x - b.x, a.y - b.y);
            if (d < 110) {
                ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y);
                ctx.strokeStyle = `rgba(96,165,250,${0.05 * (1 - d / 110)})`;
                ctx.stroke();
            }
        }));
        requestAnimationFrame(draw);
    }

    resize(); init(); draw();
    window.addEventListener('resize', () => { resize(); init(); });
})();

// ── Logger utility ─────────────────────────────────────────────────────────
function appendLog(containerId, msg, tag = 'INFO') {
    const term = document.getElementById(containerId);
    if (!term) return;
    const ts = new Date().toLocaleTimeString('en', { hour12: false });
    const line = document.createElement('div');
    line.className = 'log-line';
    line.innerHTML = `<span class="log-ts">${ts}</span><span class="log-tag ${tag}">${tag}</span><span class="log-msg">${msg}</span>`;
    term.appendChild(line);
    term.scrollTo({ top: term.scrollHeight, behavior: 'smooth' });
    Store.inc('logCount');

    // Also persist to global log feed
    const feed = Store.get('logFeed', []);
    feed.push({ ts, tag, msg });
    if (feed.length > 200) feed.shift();
    Store.set('logFeed', feed);
}

// ── Highlight / flash helper ───────────────────────────────────────────────
function flash(el, cls, durationMs = 700) {
    el.classList.add(cls);
    setTimeout(() => el.classList.remove(cls), durationMs);
}
