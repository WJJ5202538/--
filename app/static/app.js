(function () {
  "use strict";

  const state = {
    file: null,
    maxMb: 30,
    engine: "",
    jobId: null,
    xhr: null,
    pollTimer: null,
    statusTimer: null,
    startedAt: 0,
    pollFailures: 0,
    uploadPercent: 0,
  };

  const $ = (selector) => document.querySelector(selector);
  const elements = {
    panel: $(".panel"),
    panelTitle: $("#panel-title"),
    stepPill: $("#step-pill"),
    views: {
      upload: $("#view-upload"),
      progress: $("#view-progress"),
      result: $("#view-result"),
      error: $("#view-error"),
    },
    form: $("#upload-form"),
    dropzone: $("#dropzone"),
    input: $("#file-input"),
    fileCard: $("#file-card"),
    fileType: $("#file-type"),
    fileName: $("#file-name"),
    fileSize: $("#file-size"),
    removeFile: $("#remove-file"),
    formError: $("#form-error"),
    submit: $("#submit-btn"),
    processingFile: $("#processing-file"),
    progressBar: $("#progress-bar"),
    progressLabel: $("#progress-label"),
    progressPercent: $("#progress-percent"),
    processSteps: Array.from(document.querySelectorAll(".process-steps li")),
    resultSummary: $("#result-summary"),
    resultName: $("#result-name"),
    download: $("#download-btn"),
    reset: $("#reset-btn"),
    engineNote: $("#engine-note"),
    errorMessage: $("#error-message"),
    errorRetry: $("#error-retry"),
  };

  const stagePlan = [
    { at: 0, value: 42, label: "正在解析文档结构…", step: 1 },
    { at: 1800, value: 55, label: "正在提取文字与表格…", step: 2 },
    { at: 3800, value: 68, label: "正在核对数学计算…", step: 3 },
    { at: 6200, value: 83, label: "正在写入红色批注…", step: 4 },
  ];

  function showView(name) {
    Object.entries(elements.views).forEach(([key, view]) => {
      view.hidden = key !== name;
    });
    const pills = { upload: "STEP 01", progress: "STEP 02", result: "STEP 03", error: "STEP 02" };
    const titles = { upload: "上传文档", progress: "正在批改", result: "批改结果", error: "批改未完成" };
    elements.stepPill.textContent = pills[name] || "STEP 01";
    elements.panelTitle.textContent = titles[name] || "上传文档";
    elements.panel.setAttribute("aria-busy", name === "progress" ? "true" : "false");
  }

  function setProgress(value, label) {
    const safeValue = Math.max(0, Math.min(100, Math.round(value)));
    elements.progressBar.value = safeValue;
    elements.progressPercent.textContent = safeValue + "%";
    if (label) {
      elements.progressLabel.textContent = label;
    }
  }

  function setStep(activeStep, allDone) {
    elements.processSteps.forEach((item) => {
      const step = Number(item.dataset.step);
      item.classList.toggle("is-done", allDone || step < activeStep);
      item.classList.toggle("is-active", !allDone && step === activeStep);
    });
  }

  function formatBytes(bytes) {
    if (!Number.isFinite(bytes) || bytes <= 0) return "0 KB";
    if (bytes >= 1024 * 1024) {
      return (bytes / (1024 * 1024)).toFixed(bytes >= 10 * 1024 * 1024 ? 1 : 2) + " MB";
    }
    return Math.max(1, Math.round(bytes / 1024)) + " KB";
  }

  function fileExtension(file) {
    const match = /\.([^.]+)$/.exec(file.name);
    return match ? match[1].toLowerCase() : "";
  }

  function describeError(data, fallback) {
    if (data && typeof data.detail === "string" && data.detail.trim()) {
      return data.detail;
    }
    return fallback;
  }

  function showFormError(message) {
    elements.formError.textContent = message;
    elements.formError.hidden = false;
  }

  function clearFormError() {
    elements.formError.textContent = "";
    elements.formError.hidden = true;
  }

  function validateFile(file) {
    const extension = fileExtension(file);
    if (!["docx", "pdf"].includes(extension)) {
      return "仅支持 .docx（Word）和 .pdf 文件。";
    }
    if (file.size === 0) {
      return "这个文件是空的，请重新选择。";
    }
    if (file.size > state.maxMb * 1024 * 1024) {
      return "文件不能超过 " + state.maxMb + " MB。";
    }
    return "";
  }

  function chooseFile(file) {
    if (!file) return;
    clearFormError();
    const error = validateFile(file);
    if (error) {
      showFormError(error);
      resetFile();
      return;
    }

    state.file = file;
    const extension = fileExtension(file);
    elements.fileType.textContent = extension === "pdf" ? "PDF" : "DOCX";
    elements.fileType.classList.toggle("is-pdf", extension === "pdf");
    elements.fileName.textContent = file.name;
    elements.fileSize.textContent = formatBytes(file.size) + " · " + (extension === "pdf" ? "PDF 文档" : "Word 文档");
    elements.fileCard.hidden = false;
    elements.dropzone.hidden = true;
    elements.submit.disabled = false;
    elements.submit.focus({ preventScroll: true });
  }

  function resetFile() {
    state.file = null;
    elements.input.value = "";
    elements.fileCard.hidden = true;
    elements.dropzone.hidden = false;
    elements.submit.disabled = true;
    clearFormError();
  }

  function stopProcessing() {
    if (state.statusTimer) {
      window.clearInterval(state.statusTimer);
      state.statusTimer = null;
    }
    if (state.pollTimer) {
      window.clearTimeout(state.pollTimer);
      state.pollTimer = null;
    }
  }

  function startStatusTicker() {
    stopProcessing();
    const started = Date.now();
    let lastValue = 40;
    state.statusTimer = window.setInterval(() => {
      const elapsed = Date.now() - started;
      let stage = stagePlan[0];
      for (const candidate of stagePlan) {
        if (elapsed >= candidate.at) stage = candidate;
      }
      const drift = Math.min(7, Math.floor(elapsed / 2500));
      lastValue = Math.max(lastValue, Math.min(92, stage.value + drift));
      setProgress(lastValue, stage.label);
      setStep(stage.step, false);
    }, 500);
  }

  function beginUpload() {
    if (!state.file) return;
    clearFormError();
    state.jobId = null;
    state.startedAt = Date.now();
    state.pollFailures = 0;
    state.uploadPercent = 0;

    elements.processingFile.textContent = state.file.name;
    elements.progressBar.value = 0;
    elements.progressPercent.textContent = "0%";
    elements.progressLabel.textContent = "正在上传文件…";
    setStep(1, false);
    showView("progress");
    elements.panel.scrollIntoView({ behavior: "smooth", block: "start" });

    const formData = new FormData();
    formData.append("file", state.file, state.file.name);

    const xhr = new XMLHttpRequest();
    state.xhr = xhr;
    xhr.open("POST", "/api/jobs");
    xhr.setRequestHeader("Accept", "application/json");
    xhr.timeout = 180000;

    xhr.upload.onprogress = (event) => {
      if (!event.lengthComputable) return;
      const percent = Math.max(1, Math.min(36, Math.round((event.loaded / event.total) * 36)));
      state.uploadPercent = percent;
      setProgress(percent, "正在上传 · " + formatBytes(event.loaded) + " / " + formatBytes(event.total));
    };

    xhr.onload = () => {
      state.xhr = null;
      let data = null;
      try {
        data = JSON.parse(xhr.responseText || "{}");
      } catch (_) {
        data = null;
      }

      if (xhr.status === 202 && data && data.id) {
        state.jobId = data.id;
        setProgress(40, "文件已接收，开始解析…");
        startStatusTicker();
        schedulePoll(250);
        return;
      }

      showError(describeError(data, "上传失败（HTTP " + xhr.status + "），请稍后重试。"));
    };

    xhr.onerror = () => {
      state.xhr = null;
      showError("无法连接服务器，请确认服务仍在运行后重试。");
    };

    xhr.ontimeout = () => {
      state.xhr = null;
      showError("上传等待超时，请检查网络后重试。");
    };

    xhr.onabort = () => {
      state.xhr = null;
    };

    xhr.send(formData);
  }

  function schedulePoll(delay) {
    if (!state.jobId) return;
    if (state.pollTimer) window.clearTimeout(state.pollTimer);
    state.pollTimer = window.setTimeout(pollJob, delay);
  }

  async function pollJob() {
    state.pollTimer = null;
    const jobId = state.jobId;
    if (!jobId) return;

    if (Date.now() - state.startedAt > 6 * 60 * 1000) {
      showError("处理时间过长，请重新上传。较大的 PDF 或复杂表格可能需要更久。");
      return;
    }

    try {
      const response = await fetch("/api/jobs/" + encodeURIComponent(jobId), {
        headers: { Accept: "application/json" },
        cache: "no-store",
      });
      let data = null;
      try {
        data = await response.json();
      } catch (_) {
        data = null;
      }

      if (!response.ok) {
        if (response.status === 404) {
          showError(describeError(data, "任务已失效，请重新上传。"));
          return;
        }
        throw new Error("poll-failed");
      }

      state.pollFailures = 0;
      if (data.status === "completed") {
        finishProcessing(data);
        return;
      }
      if (data.status === "failed") {
        showError(data.error || "批改没有成功，请换一个文件试试。");
        return;
      }

      if (data.status === "queued") {
        setProgress(Math.max(40, elements.progressBar.value), "任务排队中…");
        setStep(1, false);
      }
      schedulePoll(700);
    } catch (_) {
      state.pollFailures += 1;
      if (state.pollFailures >= 4) {
        showError("与服务器失去连接，请刷新页面后重新上传。");
        return;
      }
      schedulePoll(1400);
    }
  }

  function finishProcessing(job) {
    stopProcessing();
    state.jobId = null;
    setProgress(100, "批注稿已生成");
    setStep(4, true);

    const count = job.issue_count === null || job.issue_count === undefined ? null : Number(job.issue_count);
    elements.resultSummary.replaceChildren();
    if (count === null) {
      elements.resultSummary.textContent = "批注稿已生成，可立即下载。";
    } else if (count > 0) {
      elements.resultSummary.append(document.createTextNode("发现 "));
      const strong = document.createElement("b");
      strong.textContent = String(count);
      elements.resultSummary.append(strong, document.createTextNode(" 处计算问题，已用红色 # 标记。"));
    } else {
      elements.resultSummary.textContent = "没有发现可核对的错误，已生成 Word 副本。";
    }

    elements.resultName.textContent = job.output_name || "批注稿.docx";
    elements.download.href = job.download_url || "#";
    elements.download.setAttribute("download", job.output_name || "批注稿.docx");
    elements.engineNote.textContent = job.engine ? "批注引擎：" + job.engine : "";

    window.setTimeout(() => {
      showView("result");
      elements.panel.scrollIntoView({ behavior: "smooth", block: "start" });
      elements.download.focus({ preventScroll: true });
    }, 450);
  }

  function showError(message) {
    stopProcessing();
    state.jobId = null;
    elements.errorMessage.textContent = message || "处理失败，请稍后重试。";
    showView("error");
    elements.panel.scrollIntoView({ behavior: "smooth", block: "start" });
    window.setTimeout(() => elements.errorRetry.focus({ preventScroll: true }), 250);
  }

  function resetAll() {
    stopProcessing();
    if (state.xhr) {
      state.xhr.abort();
      state.xhr = null;
    }
    state.jobId = null;
    resetFile();
    elements.progressBar.value = 0;
    elements.progressPercent.textContent = "0%";
    elements.progressLabel.textContent = "正在上传文件…";
    elements.processingFile.textContent = "";
    elements.resultSummary.textContent = "";
    elements.resultName.textContent = "";
    elements.download.href = "#";
    elements.download.removeAttribute("download");
    elements.engineNote.textContent = "";
    setStep(1, false);
    showView("upload");
    elements.panel.scrollIntoView({ behavior: "smooth", block: "start" });
    window.setTimeout(() => elements.dropzone.focus({ preventScroll: true }), 250);
  }

  async function loadConfig() {
    try {
      const response = await fetch("/api/config", {
        headers: { Accept: "application/json" },
        cache: "no-store",
      });
      if (!response.ok) return;
      const config = await response.json();
      if (Number.isFinite(config.max_upload_mb) && config.max_upload_mb > 0) {
        state.maxMb = config.max_upload_mb;
        document.querySelectorAll("[data-max-mb]").forEach((node) => {
          node.textContent = String(config.max_upload_mb);
        });
      }
      state.engine = typeof config.engine === "string" ? config.engine : "";
    } catch (_) {
      // Keep defaults; the upload endpoint still enforces the real limit.
    }
  }

  elements.form.addEventListener("submit", (event) => {
    event.preventDefault();
    if (!state.file) {
      showFormError("请先选择一个 Word 或 PDF 文件。");
      return;
    }
    beginUpload();
  });

  elements.input.addEventListener("change", () => {
    const file = elements.input.files && elements.input.files[0];
    chooseFile(file);
  });

  elements.removeFile.addEventListener("click", () => {
    resetFile();
    elements.dropzone.focus({ preventScroll: true });
  });

  elements.dropzone.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      elements.input.click();
    }
  });

  ["dragenter", "dragover"].forEach((eventName) => {
    elements.dropzone.addEventListener(eventName, (event) => {
      event.preventDefault();
      event.stopPropagation();
      elements.dropzone.classList.add("is-dragging");
    });
  });

  ["dragleave", "dragend"].forEach((eventName) => {
    elements.dropzone.addEventListener(eventName, (event) => {
      event.preventDefault();
      elements.dropzone.classList.remove("is-dragging");
    });
  });

  elements.dropzone.addEventListener("drop", (event) => {
    event.preventDefault();
    event.stopPropagation();
    elements.dropzone.classList.remove("is-dragging");
    const file = event.dataTransfer && event.dataTransfer.files && event.dataTransfer.files[0];
    chooseFile(file);
  });

  window.addEventListener("dragover", (event) => event.preventDefault());
  window.addEventListener("drop", (event) => event.preventDefault());

  elements.reset.addEventListener("click", resetAll);
  elements.errorRetry.addEventListener("click", () => {
    showView("upload");
    elements.panel.scrollIntoView({ behavior: "smooth", block: "start" });
    if (state.file) {
      elements.submit.focus({ preventScroll: true });
    } else {
      window.setTimeout(() => elements.dropzone.focus({ preventScroll: true }), 250);
    }
  });

  window.addEventListener("pagehide", () => {
    if (state.statusTimer) window.clearInterval(state.statusTimer);
    if (state.pollTimer) window.clearTimeout(state.pollTimer);
  });

  loadConfig();
})();