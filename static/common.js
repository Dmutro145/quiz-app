/* Спільні функції для всіх сторінок. Усі дані з сервера виводимо через textContent (захист від XSS). */

/** SVG-іконка зі спрайта в base.html: icon('check') */
function icon(name, extraClass) {
  const NS = 'http://www.w3.org/2000/svg';
  const svg = document.createElementNS(NS, 'svg');
  svg.setAttribute('class', 'i' + (extraClass ? ' ' + extraClass : ''));
  svg.setAttribute('aria-hidden', 'true');
  const use = document.createElementNS(NS, 'use');
  use.setAttribute('href', '#i-' + name);
  svg.append(use);
  return svg;
}

/** Створює DOM-елемент: h('div', {class: 'x', text: '...'}, child1, child2) */
function h(tag, props, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props || {})) {
    if (value === null || value === undefined || value === false) continue;
    if (key === 'class') node.className = value;
    else if (key === 'text') node.textContent = value;
    else if (key.startsWith('on') && typeof value === 'function') node.addEventListener(key.slice(2), value);
    else node.setAttribute(key, value === true ? '' : value);
  }
  for (const child of children.flat()) {
    if (child === null || child === undefined || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

/** fetch + JSON + зрозуміла помилка */
async function api(url, options) {
  const response = await fetch(url, options);
  let data = null;
  try { data = await response.json(); } catch (e) { /* не JSON */ }
  if (!response.ok) {
    const detail = data && data.detail;
    const error = new Error(typeof detail === 'string' ? detail : 'Перевірте правильність введених даних');
    error.status = response.status;
    throw error;
  }
  return data;
}

/** Сервер зберігає час у UTC: '2026-11-04T19:22:51Z' або '2026-11-04 19:22:51' */
function parseUtc(value) {
  if (!value) return null;
  let text = String(value).trim();
  if (!text.includes('T')) text = text.replace(' ', 'T');
  if (!/[zZ]|[+-]\d\d:?\d\d$/.test(text)) text += 'Z';
  const date = new Date(text);
  return isNaN(date) ? null : date;
}

function formatDate(value) {
  const date = parseUtc(value);
  return date
    ? date.toLocaleString('uk-UA', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' })
    : '—';
}

function formatDuration(seconds) {
  if (seconds === null || seconds === undefined) return '—';
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return String(m).padStart(2, '0') + ':' + String(s).padStart(2, '0');
}

/** good ≥ 75%, warn ≥ 60% (залік), інакше bad */
function levelOf(percent) {
  return percent >= 75 ? 'good' : percent >= 60 ? 'warn' : 'bad';
}
