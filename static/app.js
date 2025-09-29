const apiKeySection = document.getElementById("api-key-section");
const apiKeyForm = document.getElementById("api-key-form");
const apiKeyInput = document.getElementById("api-key-input");
const clearKeyButton = document.getElementById("clear-key");

const uploadForm = document.getElementById("upload-form");
const dropArea = document.getElementById("drop-area");
const fileInput = document.getElementById("file-input");

const resultsSection = document.getElementById("results");
const resultsList = document.getElementById("results-list");
const resultItemTemplate = document.getElementById("result-item-template");
const modeSelect = document.getElementById("mode");
const vitModelRow = document.getElementById("vit-model-row");
const vitModelSelect = document.getElementById("vit_model");

let pastedImages = [];

// Get API key status from data attribute
const scriptTag = document.querySelector('script[data-api-key-set]');
window.__API_KEY_SET__ = JSON.parse(scriptTag.dataset.apiKeySet || 'false');

function showMessage(element, message, type = "success") {
  const status = document.createElement("p");
  status.className = `status ${type}`;
  status.textContent = message;
  element.insertBefore(status, element.firstChild);
  setTimeout(() => status.remove(), 4000);
}

async function handleApiKeySubmit(event) {
  event.preventDefault();
  if (!apiKeyInput.value) return;
  try {
    const response = await fetch("/api/set-key", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ api_key: apiKeyInput.value }),
    });
    if (!response.ok) {
      const data = await response.json();
      throw new Error(data.detail || "Не удалось сохранить API ключ");
    }
    showMessage(apiKeySection, "API ключ сохранен", "success");
    window.__API_KEY_SET__ = true;
    apiKeyForm.reset();
  } catch (error) {
    showMessage(apiKeySection, error.message, "error");
  }
}

async function handleClearKey() {
  try {
    const response = await fetch("/api/clear-key", { method: "POST" });
    if (!response.ok) throw new Error("Не удалось удалить ключ");
    showMessage(apiKeySection, "API ключ удален", "success");
    window.__API_KEY_SET__ = false;
  } catch (error) {
    showMessage(apiKeySection, error.message, "error");
  }
}

function preventDefaults(event) {
  event.preventDefault();
  event.stopPropagation();
}

function handleDrop(event) {
  preventDefaults(event);
  removeDragClass();
  const files = event.dataTransfer.files;
  if (files && files.length) {
    fileInput.files = files;
  }
}

function addDragClass() {
  dropArea.classList.add("dragover");
}

function removeDragClass() {
  dropArea.classList.remove("dragover");
}

async function sendFormData(formData) {
  const response = await fetch("/api/process", {
    method: "POST",
    body: formData,
  });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.detail || "Не удалось обработать изображения");
  }
  return response.json();
}

async function handleUploadSubmit(event) {
  event.preventDefault();
  if (!window.__API_KEY_SET__) {
    showMessage(uploadForm, "Сначала укажите API ключ", "error");
    return;
  }

  const formData = new FormData();
  const files = fileInput.files;

  formData.append("mode", modeSelect ? modeSelect.value : "ViT");
  if (modeSelect && modeSelect.value === "ViT") {
    formData.append("vit_model", vitModelSelect ? vitModelSelect.value : "pixtral-large-latest");
  }

  if (files && files.length) {
    Array.from(files).forEach((file) => formData.append("files", file));
  }

  pastedImages.forEach((dataUrl) => formData.append("pasted", dataUrl));

  if (!formData.has("files") && !formData.has("pasted")) {
    showMessage(uploadForm, "Добавьте хотя бы одно изображение", "error");
    return;
  }

  try {
    const { documents } = await sendFormData(formData);
    renderResults(documents);
    fileInput.value = "";
    pastedImages = [];
  } catch (error) {
    showMessage(uploadForm, error.message, "error");
  }
}

function renderResults(documents) {
  resultsList.innerHTML = "";
  documents.forEach((doc) => {
    const node = resultItemTemplate.content.cloneNode(true);
    node.querySelector(".file-name").textContent = doc.filename;
    const link = node.querySelector(".download-link");
    link.href = doc.download_url;
    try {
      // Hint the browser to use the suggested filename
      link.setAttribute("download", doc.filename);
    } catch (e) {}
    resultsList.appendChild(node);
  });
  resultsSection.classList.remove("hidden");
}

window.addEventListener("paste", async (event) => {
  if (!window.__API_KEY_SET__) return;
  const items = event.clipboardData.items;
  for (const item of items) {
    if (item.kind === "file") {
      const blob = item.getAsFile();
      if (!blob) continue;
      const reader = new FileReader();
      reader.onloadend = () => {
        if (typeof reader.result === "string") {
          pastedImages.push(reader.result);
          showMessage(uploadForm, "Изображение из буфера добавлено", "success");
        }
      };
      reader.readAsDataURL(blob);
    }
  }
});

if (apiKeyForm) {
  apiKeyForm.addEventListener("submit", handleApiKeySubmit);
}

if (clearKeyButton) {
  clearKeyButton.addEventListener("click", handleClearKey);
}

["dragenter", "dragover", "dragleave", "drop"].forEach((eventName) => {
  dropArea.addEventListener(eventName, preventDefaults);
});

["dragenter", "dragover"].forEach((eventName) => {
  dropArea.addEventListener(eventName, addDragClass);
});

["dragleave", "drop"].forEach((eventName) => {
  dropArea.addEventListener(eventName, removeDragClass);
});

dropArea.addEventListener("drop", handleDrop);
uploadForm.addEventListener("submit", handleUploadSubmit);

if (modeSelect) {
  const toggleVitRow = () => {
    if (modeSelect.value === "ViT") {
      vitModelRow.style.display = "block";
    } else {
      vitModelRow.style.display = "none";
    }
  };
  modeSelect.addEventListener("change", toggleVitRow);
  toggleVitRow();
}


