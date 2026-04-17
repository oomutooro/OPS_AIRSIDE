(function () {
  async function attachCamera(videoEl, captureBtn, outputInput) {
    if (!navigator.mediaDevices?.getUserMedia) return;
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' } });
      videoEl.srcObject = stream;
      await videoEl.play();

      captureBtn.addEventListener('click', () => {
        const canvas = document.createElement('canvas');
        canvas.width = videoEl.videoWidth;
        canvas.height = videoEl.videoHeight;
        const ctx = canvas.getContext('2d');
        ctx.drawImage(videoEl, 0, 0);
        outputInput.value = canvas.toDataURL('image/jpeg', 0.85);
      });
    } catch (err) {
      console.warn('Camera unavailable', err);
    }
  }

  document.querySelectorAll('[data-camera-wrapper]').forEach((wrapper) => {
    const video = wrapper.querySelector('video');
    const btn = wrapper.querySelector('.btn-camera-capture');
    const input = wrapper.querySelector('input[type="hidden"]');
    if (video && btn && input) attachCamera(video, btn, input);
  });
})();
