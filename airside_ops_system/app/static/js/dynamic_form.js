window.DynamicForm = {
  initProgress: function (formSelector, progressSelector) {
    const form = document.querySelector(formSelector);
    const progress = document.querySelector(progressSelector);
    if (!form || !progress) return;

    const update = () => {
      const fields = form.querySelectorAll('input,select,textarea');
      let done = 0;
      fields.forEach((f) => {
        if ((f.type === 'checkbox' || f.type === 'radio') && f.checked) done++;
        else if (f.value && f.value.trim() !== '') done++;
      });
      const pct = fields.length ? Math.round((done / fields.length) * 100) : 0;
      progress.style.width = pct + '%';
      progress.setAttribute('aria-valuenow', pct);
      progress.textContent = pct + '%';
    };

    form.addEventListener('input', update);
    update();
  }
};
