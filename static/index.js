(function () {
  const $ = (id) => document.getElementById(id);
  const disciplineSelect = $('discipline');
  const lectureSelect = $('lecture');
  const errorBox = $('formError');

  function showError(message) {
    errorBox.textContent = message;
    errorBox.hidden = !message;
  }

  // Підставляємо ім'я та групу, які студент вводив раніше (зручність, не обов'язково)
  try {
    $('fullName').value = localStorage.getItem('fullName') || '';
    $('groupName').value = localStorage.getItem('groupName') || '';
  } catch (e) { /* ігноруємо */ }

  function fill(select, placeholder, items, label) {
    select.replaceChildren(h('option', { value: '', text: placeholder }));
    items.forEach((item) => select.append(h('option', { value: item.id, text: label(item) })));
  }

  const track = $('subjectsTrack');
  let catalog = [];

  function pluralLectures(n) {
    const m10 = n % 10, m100 = n % 100;
    if (m10 === 1 && m100 !== 11) return `${n} завантажена лекція`;
    if (m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14)) return `${n} завантажені лекції`;
    return `${n} завантажених лекцій`;
  }

  function fillLectures(disciplineId, selectedId) {
    const d = catalog.find((x) => String(x.id) === String(disciplineId));
    if (!d) {
      lectureSelect.replaceChildren(h('option', { value: '', text: 'Спочатку оберіть дисципліну' }));
      lectureSelect.disabled = true;
      return;
    }
    fill(lectureSelect, 'Оберіть лекцію', d.lectures, (l) => `${l.title} · ${l.question_count} питань`);
    lectureSelect.disabled = false;
    if (selectedId) lectureSelect.value = String(selectedId);
  }

  /** Підсвічує в картках те, що обрано у формі */
  function highlight() {
    track.querySelectorAll('.subject').forEach((card) => {
      const active = card.dataset.id === disciplineSelect.value;
      card.classList.toggle('is-active', active);
      card.querySelector('.subject-state').replaceChildren(
        active ? document.createTextNode('Обрано') : icon('book-open'));
    });
    track.querySelectorAll('.lec').forEach((btn) => {
      btn.classList.toggle('is-active', btn.dataset.id === lectureSelect.value);
    });
  }

  function choose(disciplineId, lectureId) {
    showError('');
    disciplineSelect.value = String(disciplineId);
    fillLectures(disciplineId, lectureId);
    highlight();
  }

  function renderCatalog() {
    if (!catalog.length) {
      track.replaceChildren(h('p', { class: 'muted', text: 'Поки що немає доступних лекцій.' }));
      return;
    }
    track.replaceChildren(...catalog.map((d, i) => h('article', { class: 'subject', 'data-id': d.id },
      h('div', { class: 'subject-top' },
        h('span', { class: 'subject-num', text: i + 1 }),
        h('span', { class: 'subject-state' }, icon('book-open'))),
      h('h3', { class: 'subject-name', text: d.name }),
      h('p', { class: 'subject-meta', text: pluralLectures(d.materials.length) }),
      h('div', { class: 'lec-list' },
        d.materials.length ? d.materials.map((material) => h('a', {
          class: 'lec material-link',
          href: material.url,
          target: '_blank',
          rel: 'noopener noreferrer',
          'aria-label': `Відкрити PDF: ${material.title}`,
        },
          icon('file-text'),
          h('span', { class: 'lec-text' },
            h('b', { text: material.title }),
            h('small', { text: 'PDF · Відкрити лекцію' })),
          h('span', { class: 'material-open', text: 'Відкрити' })))
          : h('p', { class: 'subject-empty', text: 'Лекції з’являться після завантаження PDF.' })))));
    updateNav();
  }

  /* ---- горизонтальне гортання предметів ---- */
  const prevBtn = $('subjPrev'), nextBtn = $('subjNext');
  function step() {
    const card = track.querySelector('.subject');
    return card ? card.getBoundingClientRect().width + 16 : track.clientWidth;
  }
  function updateNav() {
    // Стрілки показуємо лише тоді, коли предметів більше, ніж вміщається
    const scrollable = track.scrollWidth > track.clientWidth + 2;
    prevBtn.hidden = nextBtn.hidden = !scrollable;
    prevBtn.disabled = track.scrollLeft <= 2;
    nextBtn.disabled = track.scrollLeft + track.clientWidth >= track.scrollWidth - 2;
  }
  prevBtn.addEventListener('click', () => track.scrollBy({ left: -step(), behavior: 'smooth' }));
  nextBtn.addEventListener('click', () => track.scrollBy({ left: step(), behavior: 'smooth' }));
  track.addEventListener('scroll', updateNav, { passive: true });
  window.addEventListener('resize', updateNav);

  const subjectsSection = $('subjectsCollapse').closest('.subjects');
  const collapseBtn = $('subjectsCollapse');
  function setSubjectsCollapsed(collapsed) {
    subjectsSection.classList.toggle('is-collapsed', collapsed);
    collapseBtn.setAttribute('aria-expanded', String(!collapsed));
    collapseBtn.setAttribute('aria-label', collapsed ? 'Розгорнути ваші предмети' : 'Згорнути ваші предмети');
  }
  collapseBtn.addEventListener('click', () => {
    setSubjectsCollapsed(!subjectsSection.classList.contains('is-collapsed'));
  });

  api('/api/catalog')
    .then((items) => {
      catalog = items;
      fill(disciplineSelect, 'Оберіть дисципліну', items.filter((d) => d.lectures.length), (d) => d.name);
      renderCatalog();
    })
    .catch(() => showError('Не вдалося завантажити дисципліни. Оновіть сторінку.'));

  disciplineSelect.addEventListener('change', () => {
    showError('');
    fillLectures(disciplineSelect.value);
    highlight();
    const card = track.querySelector('.subject.is-active');
    if (card) track.scrollTo({ left: card.offsetLeft - track.offsetLeft, behavior: 'smooth' });
  });
  lectureSelect.addEventListener('change', highlight);

  $('regForm').addEventListener('submit', (event) => {
    event.preventDefault();
    const fullName = $('fullName').value.trim().replace(/\s+/g, ' ');
    const groupName = $('groupName').value.trim().replace(/\s+/g, ' ');

    if (fullName.length < 2) return showError('Вкажіть прізвище та ім\'я.');
    if (!groupName) return showError('Вкажіть академічну групу.');
    if (!disciplineSelect.value) return showError('Оберіть дисципліну.');
    if (!lectureSelect.value) return showError('Оберіть лекцію.');
    setSubjectsCollapsed(true);

    const title = lectureSelect.options[lectureSelect.selectedIndex].text.split(' · ')[0];
    try {
      sessionStorage.setItem('studentData', JSON.stringify({
        full_name: fullName,
        group_name: groupName,
        lecture_id: Number(lectureSelect.value),
        lecture_title: title,
        discipline_title: disciplineSelect.options[disciplineSelect.selectedIndex].text,
      }));
      localStorage.setItem('fullName', fullName);
      localStorage.setItem('groupName', groupName);
    } catch (e) {
      return showError('Браузер блокує збереження даних. Вимкніть приватний режим і спробуйте ще раз.');
    }
    location.href = '/test';
  });
})();