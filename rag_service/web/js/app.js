(() => {
  // 忽略历史缓存页里写死的 http://127.0.0.1:8100
  let apiBase = (window.RAG_API_BASE || "").replace(/\/$/, "");
  if (apiBase.includes(":8100") && location.port !== "8100") {
    apiBase = "";
  }

  const el = {
    kbSelect: document.getElementById("kb-select"),
    kbName: document.getElementById("kb-name"),
    createKbBtn: document.getElementById("create-kb-btn"),
    refreshKbBtn: document.getElementById("refresh-kb-btn"),
    uploadForm: document.getElementById("upload-form"),
    docTitle: document.getElementById("doc-title"),
    docFile: document.getElementById("doc-file"),
    uploadBtn: document.getElementById("upload-btn"),
    refreshDocsBtn: document.getElementById("refresh-docs-btn"),
    docsBody: document.getElementById("docs-body"),
    toast: document.getElementById("toast"),
    apiHint: document.getElementById("api-hint"),
  };

  let toastTimer = null;

  function showToast(message, isError = false) {
    el.toast.hidden = false;
    el.toast.textContent = message;
    el.toast.classList.toggle("is-error", Boolean(isError));
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => {
      el.toast.hidden = true;
    }, 4200);
  }

  async function api(path, options = {}) {
    const resp = await fetch(`${apiBase}${path}`, options);
    const text = await resp.text();
    let body = null;
    if (text) {
      try {
        body = JSON.parse(text);
      } catch {
        body = text;
      }
    }
    if (!resp.ok) {
      const detail =
        (body && typeof body === "object" && body.detail) ||
        (typeof body === "string" ? body : "") ||
        resp.statusText;
      throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
    }
    return body;
  }

  function formatTime(value) {
    if (!value) return "—";
    const d = new Date(value);
    if (Number.isNaN(d.getTime())) return String(value);
    return d.toLocaleString("zh-CN", { hour12: false });
  }

  function statusClass(status) {
    if (status === "ready") return "ready";
    if (status === "failed") return "failed";
    return "pending";
  }

  function renderDocs(docs) {
    if (!docs || docs.length === 0) {
      el.docsBody.innerHTML =
        '<tr class="empty"><td colspan="6">暂无文档，上传后将显示在这里</td></tr>';
      return;
    }
    el.docsBody.innerHTML = docs
      .map((doc) => {
        const err =
          doc.status === "failed" && doc.error
            ? `<td class="error-cell">${escapeHtml(doc.error)}</td>`
            : "<td>—</td>";
        const id = escapeHtml(doc.doc_id);
        return `<tr data-doc-id="${id}">
          <td>${escapeHtml(doc.title || doc.source_name || doc.doc_id)}</td>
          <td><span class="status ${statusClass(doc.status)}">${escapeHtml(doc.status)}</span></td>
          <td>${Number(doc.chunk_count || 0)}</td>
          <td>${escapeHtml(formatTime(doc.updated_at || doc.created_at))}</td>
          ${err}
          <td class="actions-cell">
            <button type="button" class="btn ghost sm" data-action="reindex" data-doc-id="${id}">重索引</button>
            <button type="button" class="btn danger ghost sm" data-action="delete" data-doc-id="${id}">删除</button>
          </td>
        </tr>`;
      })
      .join("");
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  async function loadKnowledgeBases(preferId) {
    const list = await api("/v1/kb");
    const selected = preferId || el.kbSelect.value || (list[0] && list[0].kb_id) || "";
    el.kbSelect.innerHTML = list
      .map(
        (kb) =>
          `<option value="${escapeHtml(kb.kb_id)}">${escapeHtml(kb.name)} (${escapeHtml(kb.kb_id)})</option>`
      )
      .join("");
    if (selected) el.kbSelect.value = selected;
    return list;
  }

  async function loadDocuments() {
    const kbId = el.kbSelect.value;
    if (!kbId) {
      renderDocs([]);
      return;
    }
    const docs = await api(`/v1/kb/${encodeURIComponent(kbId)}/documents`);
    renderDocs(docs);
  }

  async function createKb() {
    const name = (el.kbName.value || "").trim();
    if (!name) {
      showToast("请输入知识库名称", true);
      return;
    }
    el.createKbBtn.disabled = true;
    try {
      const created = await api("/v1/kb", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name }),
      });
      el.kbName.value = "";
      await loadKnowledgeBases(created.kb_id);
      await loadDocuments();
      showToast(`已创建知识库：${created.name}`);
    } catch (err) {
      showToast(err.message || String(err), true);
    } finally {
      el.createKbBtn.disabled = false;
    }
  }

  async function uploadDocument(event) {
    event.preventDefault();
    const kbId = el.kbSelect.value;
    const file = el.docFile.files && el.docFile.files[0];
    if (!kbId) {
      showToast("请先选择知识库", true);
      return;
    }
    if (!file) {
      showToast("请选择文件", true);
      return;
    }

    const form = new FormData();
    form.append("file", file, file.name);
    const title = (el.docTitle.value || "").trim();
    if (title) form.append("title", title);

    el.uploadBtn.disabled = true;
    try {
      const doc = await api(`/v1/kb/${encodeURIComponent(kbId)}/documents`, {
        method: "POST",
        body: form,
      });
      el.docFile.value = "";
      el.docTitle.value = "";
      await loadDocuments();
      if (doc.status === "ready") {
        showToast(`上传成功：${doc.title}（${doc.chunk_count} 个切片）`);
      } else if (doc.status === "failed") {
        showToast(`入库失败：${doc.error || "未知错误"}`, true);
      } else {
        showToast(`已提交：${doc.title}（状态 ${doc.status}）`);
      }
    } catch (err) {
      showToast(err.message || String(err), true);
    } finally {
      el.uploadBtn.disabled = false;
    }
  }

  async function deleteDocument(docId) {
    if (!docId) return;
    if (!window.confirm("确认删除该文档？将同时清理切片与索引。")) return;
    try {
      await api(`/v1/documents/${encodeURIComponent(docId)}`, { method: "DELETE" });
      await loadDocuments();
      showToast("文档已删除");
    } catch (err) {
      showToast(err.message || String(err), true);
    }
  }

  async function reindexDocument(docId) {
    if (!docId) return;
    try {
      const doc = await api(`/v1/documents/${encodeURIComponent(docId)}/reindex`, {
        method: "POST",
      });
      await loadDocuments();
      if (doc.status === "ready") {
        showToast(`重索引成功：${doc.title}（${doc.chunk_count} 个切片）`);
      } else if (doc.status === "failed") {
        showToast(`重索引失败：${doc.error || "未知错误"}`, true);
      } else {
        showToast(`重索引完成：${doc.title}（状态 ${doc.status}）`);
      }
    } catch (err) {
      showToast(err.message || String(err), true);
    }
  }

  async function boot() {
    el.apiHint.textContent = apiBase
      ? `API · ${apiBase}`
      : "API · 同域";
    try {
      await loadKnowledgeBases();
      await loadDocuments();
    } catch (err) {
      showToast(`无法连接 API：${err.message || err}`, true);
      renderDocs([]);
    }
  }

  el.createKbBtn.addEventListener("click", createKb);
  el.refreshKbBtn.addEventListener("click", async () => {
    try {
      await loadKnowledgeBases();
      await loadDocuments();
      showToast("知识库列表已刷新");
    } catch (err) {
      showToast(err.message || String(err), true);
    }
  });
  el.refreshDocsBtn.addEventListener("click", async () => {
    try {
      await loadDocuments();
      showToast("文档列表已刷新");
    } catch (err) {
      showToast(err.message || String(err), true);
    }
  });
  el.kbSelect.addEventListener("change", () => {
    loadDocuments().catch((err) => showToast(err.message || String(err), true));
  });
  el.uploadForm.addEventListener("submit", uploadDocument);
  el.docsBody.addEventListener("click", (event) => {
    const btn = event.target.closest("button[data-action]");
    if (!btn) return;
    const docId = btn.getAttribute("data-doc-id");
    const action = btn.getAttribute("data-action");
    if (action === "delete") {
      deleteDocument(docId);
    } else if (action === "reindex") {
      reindexDocument(docId);
    }
  });

  boot();
})();
