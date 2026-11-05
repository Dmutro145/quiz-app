(function () {
  const $ = (id) => document.getElementById(id);
  const LETTERS = ['A', 'B', 'C', 'D'];

  let student = null;
  try { student = JSON.parse(sessionStorage.getItem('studentData') || 'null'); } catch (e) { /* ігноруємо */ }
  if (!student) { location.replace('/'); return; }

  let token = '';
  let questions = [];
  let answers = {};          // question_id -> початкова літера варіанта (A–D)
  let index = 0;
  let startedAt = 0;
  let timerId = null;
  let busy = false;

  $('studentInfo').textContent = `${student.full_name} · ${student.group_name}`;
  $('lectureTitle').textContent = student.lecture_title;

  function show(id) {
    ['loading', 'errorBox', 'quiz', 'result'].forEach((name) => { $(name).hidden = name !== id; });
  }

  function fail(message) {
    stopTimer();
    $('errorText').textContent = message;
    show('errorBox');
  }

  // ---------- таймер
  function tick() { $('timer').textContent = formatDuration(Math.floor((Date.now() - startedAt) / 1000)); }
  function stopTimer() { if (timerId) { clearInterval(timerId); timerId = null; } }

  // ---------- старт
  function load() {
    show('loading');
    answers = {}; index = 0; busy = false;
    api(`/api/lectures/${student.lecture_id}/test?limit=10`)
      .then((data) => {
        token = data.token;
        questions = data.questions;
        startedAt = Date.now();
        stopTimer(); tick(); timerId = setInterval(tick, 1000);
        show('quiz');
        render();
      })
      .catch((error) => fail(error.message));
  }

  // ---------- відображення
  function render() {
    const q = questions[index];
    const total = questions.length;
    $('qMeta').textContent = `Питання ${index + 1} з ${total}`;
    $('qText').textContent = q.text;
    $('progressBar').style.width = `${(Object.keys(answers).length / total) * 100}%`;

    $('options').replaceChildren(...q.options.map((option, i) => {
      const selected = answers[q.id] === option.key;
      return h('button', {
        type: 'button', class: 'option' + (selected ? ' selected' : ''),
        role: 'radio', 'aria-checked': selected ? 'true' : 'false',
        onclick: () => choose(i),
      }, h('span', { class: 'letter', text: LETTERS[i] }), h('span', { text: option.text }));
    }));

    $('dots').replaceChildren(...questions.map((item, i) => h('button', {
      type: 'button', text: String(i + 1),
      class: 'dot' + (answers[item.id] ? ' answered' : '') + (i === index ? ' current' : ''),
      'aria-label': `Питання ${i + 1}` + (answers[item.id] ? ' (є відповідь)' : ''),
      onclick: () => { index = i; render(); },
    })));

    $('prevBtn').disabled = index === 0;
    setNext(index === total - 1 ? 'Завершити' : 'Далі', index === total - 1 ? 'check' : 'arrow-right');
  }

  function setNext(label, iconName) {
    $('nextBtn').replaceChildren(label, icon(iconName));
  }

  function choose(optionIndex) {
    const q = questions[index];
    const option = q.options[optionIndex];
    if (!option) return;
    answers[q.id] = option.key;
    render();
  }

  function go(delta) {
    const next = index + delta;
    if (next >= 0 && next < questions.length) { index = next; render(); }
  }

  // ---------- завершення
  function finish() {
    if (busy) return;
    const unanswered = questions.length - Object.keys(answers).length;
    if (unanswered > 0 && !confirm(`Без відповіді: ${unanswered}. Такі питання зарахуються як неправильні. Завершити тест?`)) return;

    busy = true;
    $('nextBtn').disabled = true;
    $('nextBtn').replaceChildren('Перевірка…');
    stopTimer();

    api('/api/submit_test', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        token,
        full_name: student.full_name,
        group_name: student.group_name,
        duration_sec: Math.round((Date.now() - startedAt) / 1000),
        answers: Object.entries(answers).map(([id, key]) => ({ question_id: Number(id), selected_option: key })),
      }),
    })
      .then(showResult)
      .catch((error) => {
        busy = false;
        $('nextBtn').disabled = false;
        setNext('Завершити', 'check');
        if (error.status === 404 || error.status === 409) return fail(error.message);
        alert('Не вдалося зберегти результат: ' + error.message + '\nСпробуйте ще раз.');
      });
  }

  function showResult(data) {
    $('verdict').textContent = data.percent >= 90 ? 'Відмінний результат'
      : data.passed ? 'Добрий результат' : 'Варто повторити матеріал';
    $('statusPill').replaceChildren(h('span', { class: 'status ' + (data.passed ? 'ok' : 'low') },
      icon(data.passed ? 'check' : 'x'), data.passed ? 'Залік' : 'Не складено'));
    $('scoreText').textContent = `${data.score} з ${data.total}`;
    $('percentText').textContent = `${Math.round(data.percent)}%`;
    $('timeText').textContent = `Час: ${$('timer').textContent}`;
    show('result');

    // анімація кільця (довжина кола = 2πr ≈ 326.7)
    const circumference = 2 * Math.PI * 52;
    requestAnimationFrame(() => {
      $('ringFill').setAttribute('stroke-dasharray', `${(circumference * data.percent) / 100} ${circumference}`);
    });

    $('review').replaceChildren(
      h('h3', { text: 'Розбір відповідей' }),
      ...data.review.map((item, i) => h('div', { class: 'review-item ' + (item.is_correct ? 'ok' : 'bad') },
        h('span', { class: 'mark' }, icon(item.is_correct ? 'check' : 'x')),
        h('div', {},
          h('div', { class: 'q', text: `${i + 1}. ${item.text}` }),
          item.is_correct
            ? h('div', { class: 'a' }, 'Ваша відповідь: ', h('b', { text: item.selected_text }))
            : h('div', { class: 'a' },
                'Ваша відповідь: ', h('b', { text: item.selected_text || 'немає відповіді' }),
                h('br'), 'Правильно: ', h('b', { text: item.correct_text })),
        ),
      )),
    );
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  // ---------- події
  $('prevBtn').addEventListener('click', () => go(-1));
  $('nextBtn').addEventListener('click', () => (index === questions.length - 1 ? finish() : go(1)));
  $('againBtn').addEventListener('click', load);

  document.addEventListener('keydown', (event) => {
    if ($('quiz').hidden || busy || event.ctrlKey || event.metaKey || event.altKey) return;
    if (['1', '2', '3', '4'].includes(event.key)) choose(Number(event.key) - 1);
    else if (event.key === 'ArrowRight') go(1);
    else if (event.key === 'ArrowLeft') go(-1);
  });

  load();
})();
