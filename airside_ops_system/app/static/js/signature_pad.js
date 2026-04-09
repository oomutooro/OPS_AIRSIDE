(function () {
  document.querySelectorAll('canvas.signature-pad').forEach(function (canvas) {
    const targetInputName = canvas.getAttribute('data-target');
    const hiddenInput = canvas.parentElement.querySelector(`input[name="${targetInputName}"]`);
    if (!hiddenInput || typeof SignaturePad === 'undefined') return;

    const pad = new SignaturePad(canvas, { backgroundColor: 'rgb(248,250,252)' });

    const resizeCanvas = () => {
      const ratio = Math.max(window.devicePixelRatio || 1, 1);
      canvas.width = canvas.offsetWidth * ratio;
      canvas.height = canvas.offsetHeight * ratio;
      canvas.getContext('2d').scale(ratio, ratio);
      pad.clear();
    };

    window.addEventListener('resize', resizeCanvas);
    resizeCanvas();

    canvas.closest('form')?.addEventListener('submit', function () {
      if (!pad.isEmpty()) {
        hiddenInput.value = pad.toDataURL('image/png');
      }
    });
  });
})();
