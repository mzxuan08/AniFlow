(() => {
  const root = document.documentElement;
  const buttons = [...document.querySelectorAll('#theme-toggle, #theme-toggle-mobile')];
  const labels = { auto: '自动', light: '浅色', dark: '深色' };
  const order = ['auto', 'light', 'dark'];
  const render = () => {
    const mode = root.dataset.theme || 'auto';
    buttons.forEach((button) => {
      const label = button.querySelector('small');
      if (label) label.textContent = labels[mode];
      button.title = `当前：${labels[mode]}`;
    });
  };
  buttons.forEach((button) => button.addEventListener('click', () => {
    const current = root.dataset.theme || 'auto';
    const next = order[(order.indexOf(current) + 1) % order.length];
    root.dataset.theme = next;
    localStorage.setItem('aniflow-theme', next);
    render();
  }));
  render();
})();
