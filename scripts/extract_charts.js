// 从源站 HTML 中提取所有 Plotly.newPlot 的图表数据
// 用法: node extract_charts.js <index.html> <out.json>
const fs = require('fs');

const html = fs.readFileSync(process.argv[2], 'utf8');

// 抓取所有普通 <script> 块(无 src、无 type=application/json)
const scripts = [];
const re = /<script(?![^>]*src=)(?![^>]*application\/json)[^>]*>([\s\S]*?)<\/script>/g;
let m;
while ((m = re.exec(html))) scripts.push(m[1]);

// 万能桩对象: 任何属性访问都返回可用值
function anyObj() {
  const fn = function () { return proxy; };
  const proxy = new Proxy(fn, {
    get(t, k) {
      if (k === Symbol.toPrimitive) return () => 0;
      if (k === 'length') return 0;
      if (k === Symbol.iterator) return function* () {};
      return proxy;
    },
    apply() { return proxy; },
    set() { return true; },
  });
  return proxy;
}

const captured = {};
const Plotly = {
  newPlot(id, traces, layout, config) {
    try {
      captured[id] = { traces: JSON.parse(JSON.stringify(traces, (k, v) => typeof v === 'function' ? undefined : v)), layout: JSON.parse(JSON.stringify(layout ?? {}, (k, v) => typeof v === 'function' ? undefined : v)) };
    } catch (e) { captured[id] = { error: String(e) }; }
    return Promise.resolve(anyObj());
  },
  react(id, traces, layout) {
    captured[id + '@react'] = { traces: JSON.parse(JSON.stringify(traces ?? {})) };
    return Promise.resolve(anyObj());
  },
  purge() {}, relayout() { return Promise.resolve(); }, restyle() { return Promise.resolve(); },
};

const documentStub = new Proxy({}, {
  get(t, k) {
    if (k === 'getElementById' || k === 'querySelector') return () => anyObj();
    if (k === 'querySelectorAll') return () => [];
    if (k === 'createElement' || k === 'createTextNode') return () => anyObj();
    if (k === 'addEventListener') return () => {};
    if (k === 'body' || k === 'documentElement') return anyObj();
    if (k === 'readyState') return 'complete';
    return anyObj();
  },
});

const sandbox = {
  Plotly, document: documentStub,
  window: undefined, // set below
  console, setTimeout: () => 0, setInterval: () => 0, clearInterval: () => {},
  requestAnimationFrame: (f) => 0, fetch: () => Promise.resolve(anyObj()),
  localStorage: { getItem: () => null, setItem: () => {} },
  location: { hash: '', search: '', href: '' },
  navigator: { userAgent: 'node' },
  matchMedia: () => ({ matches: false, addEventListener: () => {} }),
  ResizeObserver: class { observe() {} unobserve() {} disconnect() {} },
  IntersectionObserver: class { observe() {} unobserve() {} disconnect() {} },
};
sandbox.window = sandbox;
sandbox.globalThis = sandbox;

const vm = require('vm');
vm.createContext(sandbox);
for (const s of scripts) {
  try { vm.runInContext(s, sandbox, { timeout: 20000 }); }
  catch (e) { /* 忽略运行时错误, 图表已在执行中被捕获 */ }
}

fs.writeFileSync(process.argv[3], JSON.stringify(captured));
console.log('captured charts:', Object.keys(captured).join(', '));
console.log('count:', Object.keys(captured).length);
