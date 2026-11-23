(function () {
  const $ = (id) => document.getElementById(id);
  let allRows = [];

  // ---------- навчальні PDF-матеріали
  const materialForm = $('materialForm');
  const materialFile = $('materialFile');
  const fileDrop = $('fileDrop');
  const uploadButton = $('uploadButton');
  const materialMessage = $('materialMessage');

  function showMaterialMessage(text, isError) {
    materialMessage.textContent = text;
    materialMessage.classList.toggle('form-error', Boolean(isError));
    materialMessage.classList.toggle('muted', !isError);
  }

  async function loadMaterialForm() {
    const disciplines = await api('/api/disciplines');
    const select = $('materialDiscipline');
    select.replaceChildren(h('option', { value: '', text: 'Оберіть предмет' }));
    disciplines.forEach((discipline) => {
      select.append(h('option', { value: discipline.id, text: discipline.name }));
    });
    select.disabled = disciplines.length === 0;
  }

  async function loadUploadedMaterials() {
    const materials = await api('/api/teacher/materials');
    const grouped = new Map();
    materials.forEach((material) => {
      if (!grouped.has(material.discipline_id)) {
        grouped.set(material.discipline_id, { name: material.discipline_name, items: [] });
      }
      grouped.get(material.discipline_id).items.push(material);
    });
    const container = $('uploadedMaterials');
    if (!grouped.size) {
      container.replaceChildren(h('p', { class: 'empty', text: 'Ще немає завантажених лекцій.' }));
      return;
    }
    const cards = Array.from(grouped.values(), (group) => {
      const links = group.items.map((material) => h('div', { class: 'uploaded-item' },
        icon('file-text'),
        h('span', { class: 'uploaded-item-text' },
          h('b', { text: material.title }),
          h('small', { text: 'PDF · Опубліковано · Доступно студентам' })),
        h('a', {
          class: 'uploaded-open',
          href: material.url,
          target: '_blank',
          rel: 'noopener noreferrer',
        }, 'Відкрити'),
        h('button', {
          type: 'button',
          class: 'uploaded-delete',
          title: `Видалити лекцію «${material.title}»`,
          'aria-label': `Видалити лекцію «${material.title}»`,
          onclick: async () => {
            if (!confirm(`Видалити лекцію «${material.title}»? Студенти більше не матимуть доступу до PDF.`)) return;
            try {
              await api(`/api/teacher/materials/${material.id}`, { method: 'DELETE' });
            } catch (error) {
              showMaterialMessage(`Не вдалося видалити лекцію: ${error.message}`, true);
              return;
            }
            try {
              await loadUploadedMaterials();
              showMaterialMessage(`Лекцію «${material.title}» видалено.`, false);
            } catch (error) {
              showMaterialMessage(`Лекцію видалено, але список не оновився: ${error.message}`, true);
            }
          },
        }, 'Видалити')));
      return h('article', { class: 'uploaded-subject' },
        h('h3', { text: group.name }),
        h('div', { class: 'uploaded-list' }, ...links));
    });
    container.replaceChildren(...cards);
  }

  function updateFileName(file) {
    $('fileName').textContent = file ? file.name : 'Оберіть PDF-файл або перетягніть його сюди';
  }

  materialFile.addEventListener('change', () => updateFileName(materialFile.files[0]));
  fileDrop.addEventListener('dragover', (event) => {
    event.preventDefault();
    fileDrop.classList.add('is-dragging');
  });
  fileDrop.addEventListener('dragleave', () => fileDrop.classList.remove('is-dragging'));
  fileDrop.addEventListener('drop', (event) => {
    event.preventDefault();
    fileDrop.classList.remove('is-dragging');
    const [file] = event.dataTransfer.files;
    if (!file) return;
    const transfer = new DataTransfer();
    transfer.items.add(file);
    materialFile.files = transfer.files;
    updateFileName(file);
  });
  materialForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    const file = materialFile.files[0];
    if (!file || !file.name.toLowerCase().endsWith('.pdf')) {
      showMaterialMessage('Оберіть файл із розширенням PDF.', true);
      return;
    }
    if (file.size > 20 * 1024 * 1024) {
      showMaterialMessage('Розмір PDF не має перевищувати 20 МБ.', true);
      return;
    }
    uploadButton.disabled = true;
    showMaterialMessage('Завантаження лекції…', false);
    try {
      const response = await api('/api/teacher/materials', {
        method: 'POST',
        body: new FormData(materialForm),
      });
      $('materialTitle').value = '';
      materialFile.value = '';
      updateFileName(null);
      showMaterialMessage(`Лекцію «${response.title}» завантажено та опубліковано.`, false);
      try {
        await loadUploadedMaterials();
      } catch (error) {
        showMaterialMessage(`Лекцію опубліковано, але список не оновився: ${error.message}`, true);
      }
    } catch (error) {
      showMaterialMessage(`Не вдалося завантажити лекцію: ${error.message}`, true);
    } finally {
      uploadButton.disabled = false;
    }
  });

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
    const lectureTerm = $('searchLecture').value.trim().toLowerCase();
    const groupTerm = $('searchGroup').value.trim().toLowerCase();
    const rows = allRows.filter((r) =>
      (!term || r.student_name.toLowerCase().includes(term)) &&
      (!lectureTerm || r.lecture_title.toLowerCase().includes(lectureTerm)) &&
      (!groupTerm || r.group_name.toLowerCase().includes(groupTerm)));
    const body = $('rows');
    if (!rows.length) {
      body.replaceChildren(h('tr', {}, h('td', { colspan: 5, class: 'muted', text: 'Немає результатів за цими умовами' })));
      return;
    }
    body.replaceChildren(...rows.map((r) => h('tr', {},
      h('td', { class: 'c-student' }, h('div', { class: 'name', text: r.student_name }), h('small', { text: r.group_name })),
      h('td', { class: 'c-lecture' }, h('div', { text: r.lecture_title }), h('small', { text: r.discipline_name })),
      h('td', { class: 'c-date' }, h('div', { text: formatDate(r.created_at) }), h('small', { text: 'Час ' + formatDuration(r.duration_sec) })),
      h('td', { class: 'c-result' }, h('span', { class: 'pill ' + levelOf(r.percent), text: `${Math.round(r.percent)}%` })),
      h('td', { class: 'c-score' }, h('strong', { text: `${r.score} / ${r.total_questions}` })),
    )));
  }

  // ---------- оновлення
  async function refresh() {
    const qs = query();
    $('exportBtn').href = '/api/export.csv' + (qs ? '?' + qs : '');
    try {
      const rows = await api('/api/results?' + qs);
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
  $('searchLecture').addEventListener('input', renderRows);
  $('searchGroup').addEventListener('input', renderRows);

  loadFilters().then(refresh).catch((error) => {
    $('rows').replaceChildren(h('tr', {}, h('td', { colspan: 4, class: 'form-error', text: error.message })));
  });
  Promise.all([loadMaterialForm(), loadUploadedMaterials()]).catch((error) => {
    showMaterialMessage(`Не вдалося завантажити дані лекцій: ${error.message}`, true);
  });
  setInterval(refresh, 30000); // дані оновлюються самі
})();
