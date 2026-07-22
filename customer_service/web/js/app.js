/**
 * 智能客服落地页 — 对接 POST /v1/chat/stream（SSE）与 resume。
 */

(function () {
  const modeBar = document.querySelector(".mode-bar");
  const modeButtons = document.querySelectorAll(".mode-btn");
  const chips = document.querySelectorAll(".chip");
  const composer = document.getElementById("composer");
  const message = document.getElementById("message");
  const attachBtn = document.getElementById("attach-btn");
  const sendBtn = document.getElementById("send-btn");
  const hint = document.getElementById("status-hint");
  const transcript = document.getElementById("transcript");
  const resumePanel = document.getElementById("resume-panel");
  const resumeInput = document.getElementById("resume-message");
  const resumeBtn = document.getElementById("resume-btn");

  const API_BASE = (window.CS_API_BASE || "").replace(/\/$/, "");
  const MODE_LABEL = {
    fast: "快速咨询",
    expert: "专家协助",
    vision: "识图反馈",
  };

  function sessionId() {
    let id = localStorage.getItem("cs_session_id");
    if (!id) {
      id = crypto.randomUUID();
      localStorage.setItem("cs_session_id", id);
    }
    return id;
  }

  function setHint(text, flash = false) {
    hint.textContent = text;
    hint.classList.toggle("is-flash", flash);
  }

  function currentMode() {
    return modeBar?.dataset.mode || "fast";
  }

  function selectedToggles() {
    return [...chips]
      .filter((el) => el.classList.contains("is-on"))
      .map((el) => el.dataset.toggle);
  }

  function renderMarkdown(text) {
    const raw = String(text ?? "");
    if (typeof marked === "undefined") {
      return null;
    }
    try {
      if (marked.setOptions) {
        marked.setOptions({ breaks: true, gfm: true });
      }
      const html = typeof marked.parse === "function" ? marked.parse(raw) : marked(raw);
      if (typeof DOMPurify !== "undefined") {
        return DOMPurify.sanitize(html);
      }
      return html;
    } catch {
      return null;
    }
  }

  function setAssistantBody(bodyEl, text) {
    const html = renderMarkdown(text);
    if (html != null) {
      bodyEl.classList.add("bubble-md");
      bodyEl.innerHTML = html;
    } else {
      bodyEl.classList.remove("bubble-md");
      bodyEl.textContent = text;
    }
  }

  function appendBubble(role, text, meta = "") {
    const el = document.createElement("article");
    el.className = `bubble bubble-${role}`;
    const body = document.createElement("div");
    body.className = "bubble-text";
    if (role === "assistant") {
      setAssistantBody(body, text);
    } else {
      body.textContent = text;
    }
    el.appendChild(body);
    if (meta) {
      const m = document.createElement("div");
      m.className = "bubble-meta";
      m.textContent = meta;
      el.appendChild(m);
    }
    transcript.appendChild(el);
    transcript.scrollTop = transcript.scrollHeight;
    return el;
  }

  // 打字机显示速度（与网络收包解耦）。可在控制台覆盖：
  // window.CS_TYPEWRITER = { charsPerTick: 1, intervalMs: 40 }
  const TYPEWRITER = Object.assign(
    { charsPerTick: 2, intervalMs: 32 },
    window.CS_TYPEWRITER || {}
  );

  function beginAssistantStream() {
    const el = document.createElement("article");
    el.className = "bubble bubble-assistant is-streaming";
    const body = document.createElement("div");
    body.className = "bubble-text bubble-md";
    body.innerHTML = '<span class="stream-cursor">▌</span>';
    el.appendChild(body);
    const meta = document.createElement("div");
    meta.className = "bubble-meta";
    meta.textContent = "生成中…";
    el.appendChild(meta);
    transcript.appendChild(el);
    transcript.scrollTop = transcript.scrollHeight;

    const stream = {
      el,
      body,
      meta,
      pending: "", // 已收到、待打出
      shown: "", // 已展示
      networkDone: false,
      timer: null,
      doneData: null,
      resolveIdle: null,
    };

    stream.whenIdle = new Promise((resolve) => {
      stream.resolveIdle = resolve;
    });

    const tick = () => {
      const cps = Math.max(1, Number(TYPEWRITER.charsPerTick) || 2);
      if (stream.pending.length > 0) {
        const take = stream.pending.slice(0, cps);
        stream.pending = stream.pending.slice(cps);
        stream.shown += take;
        setAssistantBody(stream.body, stream.shown + "▌");
        transcript.scrollTop = transcript.scrollHeight;
      }
      if (stream.networkDone && stream.pending.length === 0) {
        if (stream.timer) {
          clearInterval(stream.timer);
          stream.timer = null;
        }
        stream.resolveIdle?.();
        stream.resolveIdle = null;
      }
    };

    stream.timer = setInterval(
      tick,
      Math.max(8, Number(TYPEWRITER.intervalMs) || 32)
    );
    stream.push = (delta) => {
      if (delta) stream.pending += delta;
    };
    stream.markNetworkDone = (data) => {
      stream.networkDone = true;
      stream.doneData = data || null;
      // 若已无待打字内容，立即结束等待
      if (stream.pending.length === 0) {
        if (stream.timer) {
          clearInterval(stream.timer);
          stream.timer = null;
        }
        stream.resolveIdle?.();
        stream.resolveIdle = null;
      }
    };
    return stream;
  }

  function finishAssistantStream(stream, data) {
    const answer = stream.shown || data.answer || "（无回复）";
    setAssistantBody(stream.body, answer);
    const bits = [`意图: ${data.intent || "-"}`];
    if (data.ticket_id) bits.push(`工单: ${data.ticket_id}`);
    if (data.needs_human) bits.push("等待人工");
    if (data.citations?.length) bits.push(`引用: ${data.citations.join(", ")}`);
    stream.meta.textContent = bits.join(" · ");
    stream.el.classList.remove("is-streaming");
    showResume(Boolean(data.needs_human));
    if (data.needs_human) {
      setHint("已转人工：可在下方填写处理说明并恢复会话。", true);
    } else {
      setHint("回复已返回。", true);
    }
  }

  function showResume(show) {
    resumePanel?.classList.toggle("is-hidden", !show);
  }

  function setBusy(busy) {
    if (sendBtn) sendBtn.disabled = busy;
    if (resumeBtn) resumeBtn.disabled = busy;
    if (message) message.disabled = busy;
  }

  function parseSseChunk(buffer) {
    const events = [];
    const parts = buffer.split("\n\n");
    const rest = parts.pop() || "";
    for (const part of parts) {
      const lines = part.split("\n");
      const dataLines = [];
      for (const line of lines) {
        if (line.startsWith("data:")) {
          dataLines.push(line.slice(5).trimStart());
        }
      }
      if (!dataLines.length) continue;
      try {
        events.push(JSON.parse(dataLines.join("\n")));
      } catch {
        // ignore malformed
      }
    }
    return { events, rest };
  }

  async function postChatStream(text, handlers) {
    const payload = {
      sessionId: sessionId(),
      message: text,
      metadata: {
        mode: currentMode(),
        toggles: selectedToggles(),
      },
    };
    const resp = await fetch(`${API_BASE}/v1/chat/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
      body: JSON.stringify(payload),
    });
    if (!resp.ok) {
      const data = await resp.json().catch(() => ({}));
      const detail = data.detail || resp.statusText || "请求失败";
      throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
    }
    if (!resp.body) {
      throw new Error("浏览器不支持流式响应");
    }

    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buf = "";
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      const parsed = parseSseChunk(buf);
      buf = parsed.rest;
      for (const ev of parsed.events) {
        if (ev.type === "token") handlers.onToken?.(ev.delta || "");
        else if (ev.type === "done") handlers.onDone?.(ev);
        else if (ev.type === "error") throw new Error(ev.message || "流式生成失败");
        else if (ev.type === "start") handlers.onStart?.(ev);
      }
    }
  }

  async function postResume(humanMessage) {
    const sid = sessionId();
    const resp = await fetch(
      `${API_BASE}/v1/admin/escalate/${encodeURIComponent(sid)}/resume`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: humanMessage, approve: true }),
      }
    );
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) {
      const detail = data.detail || resp.statusText || "恢复失败";
      throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
    }
    return data;
  }

  function renderAssistant(data) {
    const bits = [`意图: ${data.intent || "-"}`];
    if (data.ticket_id) bits.push(`工单: ${data.ticket_id}`);
    if (data.needs_human) bits.push("等待人工");
    if (data.citations?.length) bits.push(`引用: ${data.citations.join(", ")}`);
    appendBubble("assistant", data.answer || "（无回复）", bits.join(" · "));
    showResume(Boolean(data.needs_human));
    if (data.needs_human) {
      setHint("已转人工：可在下方填写处理说明并恢复会话。", true);
    } else {
      setHint("回复已返回。", true);
    }
  }

  modeButtons.forEach((btn) => {
    btn.addEventListener("click", () => {
      const mode = btn.dataset.mode;
      modeBar.dataset.mode = mode;
      modeButtons.forEach((b) => {
        const on = b === btn;
        b.classList.toggle("is-active", on);
        b.setAttribute("aria-selected", on ? "true" : "false");
      });
      setHint(`已切换到「${MODE_LABEL[mode] || mode}」`, true);
    });
  });

  chips.forEach((chip) => {
    chip.addEventListener("click", () => {
      const on = !chip.classList.contains("is-on");
      chip.classList.toggle("is-on", on);
      chip.setAttribute("aria-pressed", on ? "true" : "false");
      setHint(`${chip.textContent.trim()}已${on ? "开启" : "关闭"}（元数据随请求发送）`, true);
    });
  });

  attachBtn?.addEventListener("click", () => {
    setHint("附件上传尚未接入。", true);
  });

  composer?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const text = (message?.value || "").trim();
    if (!text) {
      setHint("请先输入问题。", true);
      message?.focus();
      return;
    }

    appendBubble("user", text);
    message.value = "";
    setBusy(true);
    setHint("正在生成回复…");

    const stream = beginAssistantStream();
    let doneData = null;
    try {
      await postChatStream(text, {
        onToken: (delta) => {
          stream.push(delta);
        },
        onDone: (data) => {
          doneData = data;
          // 若服务端最终答案比已收到的更完整，补齐到打字机队列
          const finalAnswer = data.answer || "";
          const already = stream.shown + stream.pending;
          if (finalAnswer && finalAnswer.length > already.length) {
            stream.push(finalAnswer.slice(already.length));
          } else if (!already && finalAnswer) {
            stream.push(finalAnswer);
          }
          stream.markNetworkDone(data);
        },
      });
      if (!doneData) {
        stream.markNetworkDone({ intent: "-", answer: stream.shown + stream.pending });
      }
      await stream.whenIdle;
      finishAssistantStream(
        stream,
        doneData || { intent: "-", answer: stream.shown || "（无回复）" }
      );
    } catch (err) {
      if (stream.timer) clearInterval(stream.timer);
      const msg = err?.message || String(err);
      stream.el.remove();
      appendBubble("assistant", `请求失败：${msg}`, "error");
      setHint(
        `无法连接 API（${API_BASE || "同域"}）。请确认已启动 uvicorn :8000。`,
        true
      );
    } finally {
      setBusy(false);
    }
  });

  resumeBtn?.addEventListener("click", async () => {
    const text = (resumeInput?.value || "").trim() || "已处理";
    setBusy(true);
    setHint("正在恢复会话…");
    try {
      const data = await postResume(text);
      if (resumeInput) resumeInput.value = "";
      renderAssistant(data);
    } catch (err) {
      setHint(`恢复失败：${err?.message || err}`, true);
    } finally {
      setBusy(false);
    }
  });

  message?.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      if (!sendBtn?.disabled) {
        composer?.requestSubmit();
      }
    }
  });

  setHint(`API: ${API_BASE || "同域"} · session: ${sessionId().slice(0, 8)}… · 流式输出`);
})();
