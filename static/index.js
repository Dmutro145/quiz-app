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

  api('/api/disciplines')
    .then((items) => fill(disciplineSelect, 'Оберіть дисципліну', items, (d) => d.name))
    .catch(() => showError('Не вдалося завантажити дисципліни. Оновіть сторінку.'));

  disciplineSelect.addEventListener('change', () => {
    showError('');
    lectureSelect.disabled = true;
    if (!disciplineSelect.value) {
      lectureSelect.replaceChildren(h('option', { value: '', text: 'Спочатку оберіть дисципліну' }));
      return;
    }
    lectureSelect.replaceChildren(h('option', { value: '', text: 'Завантаження…' }));
    api(`/api/disciplines/${disciplineSelect.value}/lectures`)
      .then((items) => {
        fill(lectureSelect, 'Оберіть лекцію', items, (l) => `${l.title} · ${l.question_count} питань`);
        lectureSelect.disabled = false;
      })
      .catch(() => showError('Не вдалося завантажити лекції.'));
  });

  $('regForm').addEventListener('submit', (event) => {
    event.preventDefault();
    const fullName = $('fullName').value.trim().replace(/\s+/g, ' ');
    const groupName = $('groupName').value.trim().replace(/\s+/g, ' ');

    if (fullName.length < 2) return showError('Вкажіть прізвище та ім\'я.');
    if (!groupName) return showError('Вкажіть академічну групу.');
    if (!disciplineSelect.value) return showError('Оберіть дисципліну.');
    if (!lectureSelect.value) return showError('Оберіть лекцію.');

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
