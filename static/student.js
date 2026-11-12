(function () {
  const $ = (id) => document.getElementById(id);

  async function api(url, options = {}) {
    const opts = {
      credentials: 'same-origin',
      ...options,
    };
    if (opts.body && !(opts.body instanceof FormData)) {
      opts.headers = { 'Content-Type': 'application/json', ...(opts.headers || {}) };
      if (typeof opts.body === 'object') opts.body = JSON.stringify(opts.body);
    }
    const res = await fetch(url, opts);
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      const msg = data.detail || (typeof data.detail === 'string' ? data.detail : res.statusText);
      throw new Error(Array.isArray(msg) ? msg[0]?.msg || 'Помилка' : msg || 'Помилка запиту');
    }
    return data;
  }

  function showGuest() {
    $('guestView').hidden = false;
    $('authView').hidden = true;
  }

  function showAuth() {
    $('guestView').hidden = true;
    $('authView').hidden = false;
  }

  // ----- предмети для гостя -----
  async function loadGuestSubjects() {
    try {
      const catalog = await api('/api/catalog');
      const container = $('guestSubjects');
      if (!catalog.length) {
        container.innerHTML = '<p class="muted">Поки немає доступних предметів.</p>';
        return;
      }
      container.innerHTML = '';
      catalog.forEach((d, i) => {
        const card = document.createElement('article');
        card.className = 'subject-card';
        card.innerHTML = `
          <div class="subject-num">${i + 1}</div>
          <h3>${d.name}</h3>
          <p class="muted">${(d.materials || []).length} завантажені лекції</p>
          <a class="btn ghost" href="/">Переглянути матеріали →</a>
        `;
        container.appendChild(card);
      });
      const cta = document.createElement('article');
      cta.className = 'subject-card cta';
      cta.innerHTML = `
        <h3>Готові перевірити знання?</h3>
        <p class="muted">Оберіть предмет і лекцію на вкладці «Тест».</p>
        <a class="btn primary" href="/">Перейти до тесту →</a>
      `;
      container.appendChild(cta);
    } catch (e) {
      $('guestSubjects').innerHTML = `<p class="form-error">${e.message}</p>`;
    }
  }

  // ----- кабінет -----
  async function loadCabinet(student) {
    $('studentMeta').textContent = `${student.full_name}  /  Академічна група ${student.group_name}`;

    const [stats, results] = await Promise.all([
      api('/api/student/stats'),
      api('/api/student/results'),
    ]);

    $('kTests').textContent = stats.tests || '0';
    $('kAvg').textContent = stats.tests ? `${Math.round(stats.average_percent)} / 100` : '–';

    const byDisc = {};
    let best = 0;
    let bestTitle = '';
    results.forEach((r) => {
      const pct = r.total_questions ? (r.score / r.total_questions) * 100 : 0;
      if (!byDisc[r.discipline_name]) byDisc[r.discipline_name] = { sum: 0, count: 0 };
      byDisc[r.discipline_name].sum += pct;
      byDisc[r.discipline_name].count += 1;
      if (pct >= best) {
        best = pct;
        bestTitle = r.discipline_name;
      }
    });

    const discCount = Object.keys(byDisc).length;
    $('kSubjects').textContent = discCount || '–';
    $('kSubjectsSub').textContent = discCount ? 'з усіх ваших дисциплін' : '';
    $('kBest').textContent = best ? `${Math.round(best)} / 100` : '–';
    $('kBestSub').textContent = bestTitle || '';

    // бари
    const bars = $('byDiscipline');
    const entries = Object.entries(byDisc);
    if (!entries.length) {
      bars.innerHTML = '<p class="muted">Ще немає пройдених тестів.</p>';
    } else {
      bars.innerHTML = entries.map(([name, data]) => {
        const avg = Math.round(data.sum / data.count);
        return `
          <div class="discipline-bar">
            <div class="discipline-bar-head">
              <span>${name}</span>
              <strong>${avg}</strong>
            </div>
            <div class="bar-track">
              <div class="bar-fill" style="width:${avg}%"></div>
            </div>
            <small class="muted">${data.count} тести пройдено</small>
          </div>
        `;
      }).join('');
    }

    // історія
    const body = $('historyRows');
    if (!results.length) {
      body.innerHTML = '<tr><td colspan="5" class="muted">Ще немає результатів.</td></tr>';
      return;
    }
    body.innerHTML = results.map((r) => {
      const pct = r.total_questions ? Math.round((r.score / r.total_questions) * 100) : 0;
      const date = (r.created_at || '').slice(0, 10).split('-').reverse().join('.');
      return `
        <tr>
          <td>${r.discipline_name} · ${r.lecture_title}</td>
          <td>${date}</td>
          <td>1</td>
          <td>${r.score} / ${r.total_questions}</td>
          <td><span class="pill ok">Завершено</span></td>
        </tr>
      `;
    }).join('');
  }

  // ----- вхід / вихід -----
  $('loginForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    const err = $('loginError');
    err.hidden = true;
    $('loginBtn').disabled = true;
    try {
      const student = await api('/api/student/login', {
        method: 'POST',
        body: {
          login: $('loginInput').value.trim(),
          password: $('passwordInput').value,
        },
      });
      showAuth();
      await loadCabinet(student);
    } catch (ex) {
      err.textContent = ex.message;
      err.hidden = false;
    } finally {
      $('loginBtn').disabled = false;
    }
  });

  $('logoutBtn').addEventListener('click', async () => {
    try {
      await api('/api/student/logout', { method: 'POST' });
    } catch (_) {}
    showGuest();
    $('passwordInput').value = '';
  });

  $('forgotBtn').addEventListener('click', () => {
    alert('Зверніться до викладача — він може скинути пароль у кабінеті.');
  });

  // ----- старт -----
  (async () => {
    try {
      const me = await api('/api/student/me');
      if (me.authenticated) {
        showAuth();
        await loadCabinet(me);
      } else {
        showGuest();
        await loadGuestSubjects();
      }
    } catch (_) {
      showGuest();
      await loadGuestSubjects();
    }
  })();
})();