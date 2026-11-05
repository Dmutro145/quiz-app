(function () {
  const $ = (id) => document.getElementById(id);
  let allRows = [];

  function query() {
    const params = new URLSearchParams();
    if ($('fDiscipline').value) params.set('discipline_id', $('fDiscipline').value);
    if ($('fLecture').value) params.set('lecture_id', $('fLecture').value);
    if ($('fGroup').value) params.set('group', $('fGroup').value);
    return params.toString();
  }

  // ---------- фільтри
  async function loadFilters() {
    const [disciplines, groups] = await Promise.all([api('/api/disciplines'), api('/api/groups')]);
    disciplines.forEach((d) => $('fDiscipline').append(h('option', { value: d.id, text: d.name })));
    groups.forEach((g) => $('fGroup').append(h('option', { value: g, text: g })));
  }

  async function loadLectures() {
    const select = $('fLecture');
    select.replaceChildren(h('option', { value: '', text: 'Усі лекції' }));
    select.disabled = true;
    if (!$('fDiscipline').value) return;
    const lectures = await api(`/api/disciplines/${$('fDiscipline').value}/lectures`);
    lectures.forEach((l) => select.append(h('option', { value: l.id, text: l.title })));
    select.disabled = false;
  }

  // ---------- графіки
  function bars(container, items, emptyText) {
    if (!items.length) { container.replaceChildren(h('div', { class: 'empty', text: emptyText })); return; }
    container.replaceChildren(...items.map((item) => h('div', { class: 'bar-row' },
      h('div', { class: 'bar-label' }, item.label, item.sub ? h('small', { text: item.sub }) : null),
      h('div', { class: 'bar-track' },
        h('div', { class: 'bar-fill ' + levelOf(item.value), style: `width:${Math.max(item.value, 1)}%` }),
        h('div', { class: 'bar-value', text: `${item.value}% · ${item.count}` }),
      ),
    )));
  }

  function timeline(container, days) {
    if (!days.length) { container.replaceChildren(h('div', { class: 'empty', text: 'Ще немає даних' })); return; }
    container.replaceChildren(h('div', { class: 'spark' }, ...days.map((day) => {
      const [, month, date] = day.day.split('-');
      return h('div', { class: 'col', title: `${date}.${month}: ${day.avg_percent}% (${day.tests} тест.)` },
        h('div', { class: 'bar', style: `height:${Math.max(day.avg_percent, 2) * 0.78}%` }),
        h('small', { text: `${date}.${month}` }));
    })));
  }

  // ---------- таблиця
  function renderRows() {
    const term = $('search').value.trim().toLowerCase();
    const rows = allRows.filter((r) => !term || r.student_name.toLowerCase().includes(term));
    const body = $('rows');
    if (!rows.length) {
      body.replaceChildren(h('tr', {}, h('td', { colspan: 4, class: 'muted', text: 'Немає результатів за цими умовами' })));
      return;
    }
    body.replaceChildren(...rows.map((r) => h('tr', {},
      h('td', { class: 'c-student' }, h('div', { class: 'name', text: r.student_name }), h('small', { text: r.group_name })),
      h('td', { class: 'c-lecture' }, h('div', { text: r.lecture_title }), h('small', { text: r.discipline_name })),
      h('td', { class: 'c-date' }, h('div', { text: formatDate(r.created_at) }), h('small', { text: 'Час ' + formatDuration(r.duration_sec) })),
      h('td', { class: 'c-result' }, h('span', { class: 'pill ' + levelOf(r.percent), text: `${r.score}/${r.total_questions} · ${Math.round(r.percent)}%` })),
    )));
  }

  // ---------- оновлення
  async function refresh() {
    const qs = query();
    $('exportBtn').href = '/api/export.csv' + (qs ? '?' + qs : '');
    try {
      const [stats, rows] = await Promise.all([api('/api/analytics?' + qs), api('/api/results?' + qs)]);
      $('kTests').textContent = stats.total_tests;
      $('kStudents').textContent = stats.unique_students;
      $('kAvg').textContent = stats.total_tests ? stats.average_score_percent + '%' : '–';
      $('kPass').textContent = stats.total_tests ? stats.pass_rate_percent + '%' : '–';
      $('kPassLabel').textContent = `Склали, від ${stats.pass_threshold}%`;

      bars($('byLecture'), stats.by_lecture.map((l) => ({
        label: l.lecture, sub: l.discipline, value: l.avg_percent, count: l.tests })), 'Ще немає даних');
      bars($('byGroup'), stats.by_group.map((g) => ({
        label: g.grp, sub: `${g.students} студ.`, value: g.avg_percent, count: g.tests })), 'Ще немає даних');
      timeline($('timeline'), stats.timeline);

      allRows = rows;
      renderRows();
      $('updatedAt').textContent = 'Оновлено ' + new Date().toLocaleTimeString('uk-UA', { hour: '2-digit', minute: '2-digit' });
    } catch (error) {
      $('rows').replaceChildren(h('tr', {}, h('td', { colspan: 4, class: 'form-error', text: 'Не вдалося завантажити дані: ' + error.message })));
    }
  }

  $('fDiscipline').addEventListener('change', async () => { await loadLectures(); refresh(); });
  $('fLecture').addEventListener('change', refresh);
  $('fGroup').addEventListener('change', refresh);
  $('search').addEventListener('input', renderRows);

  loadFilters().then(refresh).catch((error) => {
    $('rows').replaceChildren(h('tr', {}, h('td', { colspan: 4, class: 'form-error', text: error.message })));
  });
  setInterval(refresh, 30000); // дані оновлюються самі
})();
