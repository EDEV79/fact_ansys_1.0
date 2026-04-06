/* ============================================================
  Fact Ansys 1.0 — Upload page interactions
   ============================================================ */

document.addEventListener('DOMContentLoaded', () => {
  const dropzone = document.getElementById('dropzone');
  const fileInput = document.getElementById('file-input');
  const content = document.getElementById('upload-content');
  const selected = document.getElementById('upload-selected');
  const selectedName = document.getElementById('selected-name');
  const selectedSize = document.getElementById('selected-size');
  const spinner = document.getElementById('upload-spinner');
  const icon = document.getElementById('upload-icon');
  const form = document.getElementById('upload-form');

  if (!dropzone) return;

  function formatBytes(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / 1048576).toFixed(1) + ' MB';
  }

  function showSelected(file) {
    selectedName.textContent = file.name;
    selectedSize.textContent = formatBytes(file.size);
    content.classList.add('d-none');
    selected.classList.remove('d-none');
  }

  // File input change event
  fileInput.addEventListener('change', () => {
    if (fileInput.files.length > 0) {
      showSelected(fileInput.files[0]);
    }
  });

  // Drag & drop
  dropzone.addEventListener('dragover', (e) => {
    e.preventDefault();
    dropzone.classList.add('drag-over');
  });

  dropzone.addEventListener('dragleave', () => {
    dropzone.classList.remove('drag-over');
  });

  dropzone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropzone.classList.remove('drag-over');
    const files = e.dataTransfer.files;
    if (files.length > 0) {
      const dt = new DataTransfer();
      dt.items.add(files[0]);
      fileInput.files = dt.files;
      showSelected(files[0]);
    }
  });

  // Show spinner on submit
  form.addEventListener('submit', () => {
    spinner.classList.remove('d-none');
    icon.classList.add('d-none');
  });
});
