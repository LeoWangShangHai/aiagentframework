const messagesEl = document.getElementById('messages');
const formEl = document.getElementById('chatForm');
const inputEl = document.getElementById('chatInput');
const sendBtnEl = document.getElementById('sendBtn');

const menuChatEl = document.getElementById('menuChat');
const menuKnowledgeEl = document.getElementById('menuKnowledge');
const menuStatsEl = document.getElementById('menuStats');
const menuEnvEl = document.getElementById('menuEnv');
const viewChatEl = document.getElementById('viewChat');
const viewKnowledgeEl = document.getElementById('viewKnowledge');
const viewStatsEl = document.getElementById('viewStats');
const viewEnvEl = document.getElementById('viewEnv');

const statsConversationIdEl = document.getElementById('statsConversationId');
const statsListEl = document.getElementById('statsList');
const statsEmptyEl = document.getElementById('statsEmpty');
const statsPrevEl = document.getElementById('statsPrev');
const statsNextEl = document.getElementById('statsNext');
const statsPageInfoEl = document.getElementById('statsPageInfo');

const historyListEl = document.getElementById('statsHistory');
const historyEmptyEl = document.getElementById('statsHistoryEmpty');
const historyPrevEl = document.getElementById('historyPrev');
const historyNextEl = document.getElementById('historyNext');
const historyPageInfoEl = document.getElementById('historyPageInfo');

const envDeploymentEl = document.getElementById('envDeployment');
const envEmbeddingEl = document.getElementById('envEmbedding');
const envApiVersionEl = document.getElementById('envApiVersion');
const envEndpointEl = document.getElementById('envEndpoint');
const envEndpointHostEl = document.getElementById('envEndpointHost');
const envAuthModeEl = document.getElementById('envAuthMode');
const envTenantEl = document.getElementById('envTenant');

const uploadFormEl = document.getElementById('uploadForm');
const uploadInputEl = document.getElementById('uploadInput');
const uploadBtnEl = document.getElementById('uploadBtn');
const uploadStatusEl = document.getElementById('uploadStatus');
const knowledgeFormEl = document.getElementById('knowledgeForm');
const knowledgeInputEl = document.getElementById('knowledgeInput');
const knowledgeBtnEl = document.getElementById('knowledgeBtn');
const knowledgeNoLlmEl = document.getElementById('knowledgeNoLlm');
const knowledgeAnswerEl = document.getElementById('knowledgeAnswer');
const knowledgeSourcesEl = document.getElementById('knowledgeSources');
const uploadListEl = document.getElementById('uploadList');
const uploadEmptyEl = document.getElementById('uploadEmpty');

const STORAGE_CONVERSATION_KEY = 'codex.conversationId';

let conversationId = null;
let usagePage = 1;
let usagePageSize = 20;
let usageTotal = 0;
let usageItems = [];
let historyPage = 1;
let historyPageSize = 10;
let historyTotal = 0;
let historyItems = [];
let agentInfo = null;
let knowledgeSources = [];
let knowledgeAnswer = '';
let uploadItems = [];

function loadStoredConversationId() {
  try {
    const value = localStorage.getItem(STORAGE_CONVERSATION_KEY);
    return value && value.trim() ? value : null;
  } catch {
    return null;
  }
}

function saveConversationId(id) {
  try {
    if (id && String(id).trim()) {
      localStorage.setItem(STORAGE_CONVERSATION_KEY, String(id));
    }
  } catch {
    // ignore storage failures
  }
}

function setActiveView(view) {
  const isChat = view === 'chat';
  const isKnowledge = view === 'knowledge';
  const isStats = view === 'stats';
  const isEnv = view === 'env';

  if (viewChatEl) viewChatEl.hidden = !isChat;
  if (viewKnowledgeEl) viewKnowledgeEl.hidden = !isKnowledge;
  if (viewStatsEl) viewStatsEl.hidden = !isStats;
  if (viewEnvEl) viewEnvEl.hidden = !isEnv;

  if (menuChatEl) menuChatEl.classList.toggle('sidebar__item--active', isChat);
  if (menuKnowledgeEl) menuKnowledgeEl.classList.toggle('sidebar__item--active', isKnowledge);
  if (menuStatsEl) menuStatsEl.classList.toggle('sidebar__item--active', isStats);
  if (menuEnvEl) menuEnvEl.classList.toggle('sidebar__item--active', isEnv);
}

function fmt(v) {
  return typeof v === 'number' && Number.isFinite(v) ? String(v) : '-';
}

function fmtBytes(bytes) {
  if (typeof bytes !== 'number' || !Number.isFinite(bytes)) return '-';
  if (bytes < 1024) return `${bytes} B`;
  const kb = bytes / 1024;
  if (kb < 1024) return `${kb.toFixed(1)} KB`;
  const mb = kb / 1024;
  if (mb < 1024) return `${mb.toFixed(1)} MB`;
  const gb = mb / 1024;
  return `${gb.toFixed(1)} GB`;
}

function fmtChunkLengths(lengths) {
  if (!Array.isArray(lengths) || lengths.length === 0) return '-';
  return lengths.map((n) => (Number.isFinite(n) ? String(n) : '-')).join(', ');
}

function statsViewActive() {
  return viewStatsEl && !viewStatsEl.hidden;
}

function renderStats() {
  if (!statsConversationIdEl) return;

  statsConversationIdEl.textContent = conversationId || '-';

  if (!statsListEl || !statsEmptyEl || !statsPageInfoEl || !statsPrevEl || !statsNextEl) return;

  statsListEl.innerHTML = '';

  if (!Array.isArray(usageItems) || usageItems.length === 0) {
    statsEmptyEl.hidden = false;
  } else {
    statsEmptyEl.hidden = true;
    for (const item of usageItems) {
      const row = document.createElement('div');
      row.className = 'stats__list-row';

      const turnEl = document.createElement('span');
      turnEl.textContent = fmt(item?.turn_index);

      const modelEl = document.createElement('span');
      modelEl.textContent = item?.model_name ? String(item.model_name) : '-';

      const inputEl = document.createElement('span');
      inputEl.textContent = fmt(item?.input_tokens);

      const outputEl = document.createElement('span');
      outputEl.textContent = fmt(item?.output_tokens);

      const totalEl = document.createElement('span');
      totalEl.textContent = fmt(item?.total_tokens);

      const createdEl = document.createElement('span');
      createdEl.textContent = item?.created_at ? String(item.created_at) : '-';

      row.appendChild(turnEl);
      row.appendChild(modelEl);
      row.appendChild(inputEl);
      row.appendChild(outputEl);
      row.appendChild(totalEl);
      row.appendChild(createdEl);

      statsListEl.appendChild(row);
    }
  }

  const totalPages = usageTotal ? Math.max(1, Math.ceil(usageTotal / usagePageSize)) : 1;
  const currentPage = usageTotal ? usagePage : 1;
  statsPageInfoEl.textContent = usageTotal
    ? `Page ${currentPage} / ${totalPages} (${usageTotal})`
    : 'No data';
  statsPrevEl.disabled = currentPage <= 1;
  statsNextEl.disabled = currentPage >= totalPages;
}

function renderHistory() {
  if (!historyListEl || !historyEmptyEl || !historyPrevEl || !historyNextEl || !historyPageInfoEl) return;

  historyListEl.innerHTML = '';

  if (!Array.isArray(historyItems) || historyItems.length === 0) {
    historyEmptyEl.hidden = false;
  } else {
    historyEmptyEl.hidden = true;
    for (const item of historyItems) {
      const row = document.createElement('div');
      row.className = 'stats__history-item';
      if (item?.conversation_id && item.conversation_id === conversationId) {
        row.classList.add('stats__history-item--active');
      }

      const left = document.createElement('div');
      left.className = 'stats__history-id';
      left.textContent = item?.conversation_id ? String(item.conversation_id) : '-';

      const right = document.createElement('div');
      right.className = 'stats__history-meta';
      const turns = typeof item?.turns === 'number' ? item.turns : 0;
      const total = typeof item?.total_tokens === 'number' ? item.total_tokens : 0;
      right.textContent = `turns ${turns} / total ${total}`;

      row.appendChild(left);
      row.appendChild(right);

      row.addEventListener('click', async () => {
        if (!item?.conversation_id) return;
        conversationId = item.conversation_id;
        saveConversationId(conversationId);
        usagePage = 1;
        try {
          await loadUsagePage(usagePage);
        } catch {
          renderStats();
        }
        renderHistory();
      });

      historyListEl.appendChild(row);
    }
  }

  const totalPages = historyTotal ? Math.max(1, Math.ceil(historyTotal / historyPageSize)) : 1;
  const currentPage = historyTotal ? historyPage : 1;
  historyPageInfoEl.textContent = historyTotal
    ? `Page ${currentPage} / ${totalPages} (${historyTotal})`
    : 'No data';
  historyPrevEl.disabled = currentPage <= 1;
  historyNextEl.disabled = currentPage >= totalPages;
}

function renderKnowledge() {
  if (knowledgeAnswerEl) {
    knowledgeAnswerEl.textContent = knowledgeAnswer || '';
  }
  if (!knowledgeSourcesEl) return;
  knowledgeSourcesEl.innerHTML = '';
  if (!Array.isArray(knowledgeSources) || knowledgeSources.length === 0) return;

  for (const [idx, src] of knowledgeSources.entries()) {
    const card = document.createElement('div');
    card.className = 'knowledge__source';

    const meta = document.createElement('div');
    meta.className = 'knowledge__source-meta';
    const label = src?.source ? String(src.source) : 'unknown';
    const distance = typeof src?.distance === 'number' ? src.distance.toFixed(3) : '-';
    meta.textContent = `[${idx + 1}] 来源: ${label} / 距离: ${distance}`;

    const text = document.createElement('div');
    text.className = 'knowledge__source-text';
    text.textContent = src?.text || '';

    card.appendChild(meta);
    card.appendChild(text);
    knowledgeSourcesEl.appendChild(card);
  }
}

function renderUploads() {
  if (!uploadListEl || !uploadEmptyEl) return;
  uploadListEl.innerHTML = '';
  if (!Array.isArray(uploadItems) || uploadItems.length === 0) {
    uploadEmptyEl.hidden = false;
    return;
  }
  uploadEmptyEl.hidden = true;
  for (const item of uploadItems) {
    const row = document.createElement('div');
    row.className = 'knowledge__list-row';

    const nameEl = document.createElement('span');
    nameEl.textContent = item?.original_name || item?.stored_name || '-';

    const sizeEl = document.createElement('span');
    sizeEl.textContent = fmtBytes(item?.size_bytes);

    const timeEl = document.createElement('span');
    timeEl.textContent = item?.uploaded_at ? String(item.uploaded_at) : '-';

    const chunksEl = document.createElement('span');
    chunksEl.textContent = fmt(item?.chunks_indexed);

    const lengthsEl = document.createElement('span');
    lengthsEl.textContent = fmtChunkLengths(item?.chunk_lengths);

    row.appendChild(nameEl);
    row.appendChild(sizeEl);
    row.appendChild(timeEl);
    row.appendChild(chunksEl);
    row.appendChild(lengthsEl);
    uploadListEl.appendChild(row);
  }
}

async function loadUploads() {
  try {
    const res = await fetch('/api/knowledge/uploads');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    uploadItems = Array.isArray(data?.items) ? data.items : [];
  } catch {
    uploadItems = [];
  } finally {
    renderUploads();
  }
}

async function loadHistoryPage(page) {
  const params = new URLSearchParams({
    page: String(page),
    page_size: String(historyPageSize),
  });

  const res = await fetch(`/api/agent/conversations?${params.toString()}`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const data = await res.json();

  historyPage = typeof data?.page === 'number' ? data.page : page;
  historyPageSize = typeof data?.page_size === 'number' ? data.page_size : historyPageSize;
  historyTotal = typeof data?.total === 'number' ? data.total : 0;
  historyItems = Array.isArray(data?.items) ? data.items : [];
  renderHistory();
}

function setText(el, value) {
  if (!el) return;
  el.textContent = value && String(value).trim() ? String(value) : '-';
}

function renderAgentInfo() {
  setText(envDeploymentEl, agentInfo?.deployment_name);
  setText(envEmbeddingEl, agentInfo?.embedding_deployment_name);
  setText(envApiVersionEl, agentInfo?.api_version);
  setText(envEndpointEl, agentInfo?.endpoint);
  setText(envEndpointHostEl, agentInfo?.endpoint_host);
  setText(envAuthModeEl, agentInfo?.auth_mode);
  setText(envTenantEl, agentInfo?.tenant_id);
}

async function loadAgentInfo() {
  try {
    const res = await fetch('/api/agent/info');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    agentInfo = await res.json();
  } catch {
    agentInfo = null;
  } finally {
    renderAgentInfo();
  }
}

async function loadUsagePage(page) {
  if (!conversationId) {
    usagePage = 1;
    usageTotal = 0;
    usageItems = [];
    renderStats();
    return;
  }

  const params = new URLSearchParams({
    conversation_id: conversationId,
    page: String(page),
    page_size: String(usagePageSize),
  });

  const res = await fetch(`/api/agent/usage?${params.toString()}`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const data = await res.json();

  usagePage = typeof data?.page === 'number' ? data.page : page;
  usagePageSize = typeof data?.page_size === 'number' ? data.page_size : usagePageSize;
  usageTotal = typeof data?.total === 'number' ? data.total : 0;
  usageItems = Array.isArray(data?.items) ? data.items : [];
  renderStats();
}


function appendMessage(role, text) {
  const wrapper = document.createElement('div');
  wrapper.className = `message ${role}`;

  const bubble = document.createElement('div');
  bubble.className = 'bubble';
  bubble.textContent = text;

  wrapper.appendChild(bubble);
  messagesEl.appendChild(wrapper);
  messagesEl.scrollTop = messagesEl.scrollHeight;

  return bubble;
}

function scrollToBottom() {
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

async function runAgent(message) {
  const payload = { message };
  if (conversationId) payload.conversation_id = conversationId;

  const res = await fetch('/api/agent/run', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    let detail = '';
    try {
      const data = await res.json();
      detail = data?.detail ? `: ${data.detail}` : '';
    } catch {
      // ignore
    }
    throw new Error(`HTTP ${res.status}${detail}`);
  }

  const data = await res.json();
  if (data?.conversation_id) {
    conversationId = data.conversation_id;
    saveConversationId(conversationId);
  }
  return data;
}

async function runAgentStream(message, onDelta) {
  const payload = { message };
  if (conversationId) payload.conversation_id = conversationId;

  const res = await fetch('/api/agent/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });

  const contentType = (res.headers.get('content-type') || '').toLowerCase();

  // Web UI must use streaming. If the server doesn't stream, surface an error.
  if (!res.ok) {
    let detail = '';
    try {
      const data = await res.json();
      detail = data?.detail ? `: ${data.detail}` : '';
    } catch {
      // ignore
    }
    throw new Error(`HTTP ${res.status}${detail}`);
  }

  if (!contentType.includes('text/event-stream') || !res.body) {
    throw new Error('Server did not return text/event-stream');
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder('utf-8');
  let buffer = '';

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });

    let sepIndex;
    while ((sepIndex = buffer.indexOf('\n\n')) !== -1) {
      const chunk = buffer.slice(0, sepIndex);
      buffer = buffer.slice(sepIndex + 2);

      let eventName = 'message';
      let dataJson = '';
      for (const line of chunk.split('\n')) {
        if (line.startsWith('event:')) eventName = line.slice('event:'.length).trim();
        if (line.startsWith('data:')) dataJson += line.slice('data:'.length).trim();
      }

      if (!dataJson) continue;

      let data;
      try {
        data = JSON.parse(dataJson);
      } catch {
        continue;
      }

      if (eventName === 'meta' && data?.conversation_id) {
        conversationId = data.conversation_id;
        saveConversationId(conversationId);
        usagePage = 1;
        if (statsViewActive()) {
          try {
            await loadUsagePage(usagePage);
          } catch {
            renderStats();
          }
          try {
            await loadHistoryPage(historyPage);
          } catch {
            renderHistory();
          }
        } else {
          renderStats();
        }
      } else if (eventName === 'delta' && typeof data?.delta === 'string') {
        onDelta(data.delta);
      } else if (eventName === 'stats' && data) {
        if (statsViewActive()) {
          try {
            await loadUsagePage(usagePage);
          } catch {
            renderStats();
          }
          try {
            await loadHistoryPage(historyPage);
          } catch {
            renderHistory();
          }
        }
      } else if (eventName === 'error') {
        throw new Error(data?.message || 'stream error');
      } else if (eventName === 'done') {
        if (data?.conversation_id) conversationId = data.conversation_id;
        if (statsViewActive()) {
          try {
            await loadUsagePage(usagePage);
          } catch {
            renderStats();
          }
          try {
            await loadHistoryPage(historyPage);
          } catch {
            renderHistory();
          }
        } else {
          renderStats();
        }
        return;
      }
    }
  }
}

function setBusy(isBusy) {
  inputEl.disabled = isBusy;
  sendBtnEl.disabled = isBusy;
  sendBtnEl.textContent = isBusy ? '发送中…' : '发送';
}

const storedConversationId = loadStoredConversationId();
if (storedConversationId) {
  conversationId = storedConversationId;
}

appendMessage('assistant', '你好！我可以帮你回答问题。');

setActiveView('chat');
renderStats();
renderAgentInfo();
loadAgentInfo();

if (menuChatEl) menuChatEl.addEventListener('click', () => setActiveView('chat'));
if (menuKnowledgeEl) menuKnowledgeEl.addEventListener('click', () => {
  setActiveView('knowledge');
  renderKnowledge();
  loadUploads();
});
if (menuStatsEl) menuStatsEl.addEventListener('click', async () => {
  setActiveView('stats');
  usagePage = 1;
  historyPage = 1;
  try {
    await loadUsagePage(usagePage);
  } catch {
    renderStats();
  }
  try {
    await loadHistoryPage(historyPage);
  } catch {
    renderHistory();
  }
});
if (menuEnvEl) menuEnvEl.addEventListener('click', () => {
  setActiveView('env');
  renderAgentInfo();
});

if (uploadFormEl) uploadFormEl.addEventListener('submit', async (e) => {
  e.preventDefault();
  if (!uploadInputEl || !uploadInputEl.files || uploadInputEl.files.length === 0) {
    uploadStatusEl.textContent = '请选择文件';
    return;
  }
  const file = uploadInputEl.files[0];
  uploadBtnEl.disabled = true;
  uploadStatusEl.textContent = '上传中...';
  try {
    const form = new FormData();
    form.append('file', file);
    const res = await fetch('/api/knowledge/upload', { method: 'POST', body: form });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    uploadStatusEl.textContent = `已索引 ${data?.chunks_indexed ?? 0} 段；文件：${data?.file ?? ''}`;
    loadUploads();
  } catch (err) {
    uploadStatusEl.textContent = `上传失败：${String(err)}`;
  } finally {
    uploadBtnEl.disabled = false;
  }
});

if (knowledgeFormEl) knowledgeFormEl.addEventListener('submit', async (e) => {
  e.preventDefault();
  const question = (knowledgeInputEl?.value || '').trim();
  if (!question) return;
  knowledgeBtnEl.disabled = true;
  knowledgeAnswer = '';
  knowledgeSources = [];
  renderKnowledge();
  try {
    const res = await fetch('/api/knowledge/query', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question, use_llm: !(knowledgeNoLlmEl && knowledgeNoLlmEl.checked) }),
    });
    if (!res.ok) {
      let detail = '';
      try {
        const data = await res.json();
        detail = data?.detail ? `: ${data.detail}` : '';
      } catch {
        // ignore
      }
      throw new Error(`HTTP ${res.status}${detail}`);
    }
    const data = await res.json();
    knowledgeAnswer = data?.answer || '';
    knowledgeSources = Array.isArray(data?.sources) ? data.sources : [];
  } catch (err) {
    knowledgeAnswer = `查询失败：${String(err)}`;
  } finally {
    knowledgeBtnEl.disabled = false;
    renderKnowledge();
  }
});

if (statsPrevEl) statsPrevEl.addEventListener('click', async () => {
  if (usagePage <= 1) return;
  try {
    await loadUsagePage(usagePage - 1);
  } catch {
    // ignore
  }
});

if (statsNextEl) statsNextEl.addEventListener('click', async () => {
  const totalPages = usageTotal ? Math.max(1, Math.ceil(usageTotal / usagePageSize)) : 1;
  if (usagePage >= totalPages) return;
  try {
    await loadUsagePage(usagePage + 1);
  } catch {
    // ignore
  }
});

if (historyPrevEl) historyPrevEl.addEventListener('click', async () => {
  if (historyPage <= 1) return;
  try {
    await loadHistoryPage(historyPage - 1);
  } catch {
    // ignore
  }
});

if (historyNextEl) historyNextEl.addEventListener('click', async () => {
  const totalPages = historyTotal ? Math.max(1, Math.ceil(historyTotal / historyPageSize)) : 1;
  if (historyPage >= totalPages) return;
  try {
    await loadHistoryPage(historyPage + 1);
  } catch {
    // ignore
  }
});

inputEl.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    formEl.requestSubmit();
  }
});

formEl.addEventListener('submit', async (e) => {
  e.preventDefault();
  const text = (inputEl.value || '').trim();
  if (!text) return;

  appendMessage('user', text);
  inputEl.value = '';

  setBusy(true);
  try {
    const assistantBubble = appendMessage('assistant', '');
    let acc = '';
    await runAgentStream(text, (delta) => {
      acc += delta;
      assistantBubble.textContent = acc;
      scrollToBottom();
    });
  } catch (err) {
    appendMessage('assistant', `出错了：${String(err)}`);
  } finally {
    setBusy(false);
    inputEl.focus();
  }
});
