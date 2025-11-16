
let APP_STATE = {
  token: null,
  userId: null,
  username: null,
  summary: null,
  pdfName: null,
  chatHistory: [],
  currentDocumentId: null,
};

const $ = (sel) => document.querySelector(sel);
const $all = (sel) => document.querySelectorAll(sel);

// DOM refs (some may be missing if not present in DOM — guard accordingly)
const authPage = $('#auth-page');
const appPage = $('#app-page');
const loginForm = $('#login-form');
const signupForm = $('#signup-form');
const loginError = $('#login-error');
const signupMessage = $('#signup-message');
const showSignup = $('#show-signup');
const showLogin = $('#show-login');
const logoutButton = $('#logout-button');
const welcomeMessage = $('#welcome-message');

const fileUploader = $('#file-uploader');
const uploadButton = $('#upload-button');
const uploadStatus = $('#upload-status');
const summaryContainer = $('#summary-container');
const summaryText = $('#summary-text');

const precedentButton = $('#precedent-button');
const precedentContainer = $('#precedent-container');
const precedentText = $('#precedent-text');
const appError = $('#app-error');

const chatForm = $('#chat-form');
const chatInput = $('#chat-input');
const chatMessages = $('#chat-messages');

const API_URL = 'http://127.0.0.1:8000';

// ---------------------------
// Helpers
// ---------------------------
function authHeaders(extra = {}) {
  const token = APP_STATE.token || localStorage.getItem('legal_app_token');
  if (!token) throw new Error('Missing authentication token. Please log in.');
  return {
    ...extra,
    Authorization: `Bearer ${token}`,
  };
}

function handleAuthError(status) {
  if (status === 401) {
    showMessage(appError, '⚠️ Session expired. Please log in again.', true);
    logoutUser();
    throw new Error('Session expired or invalid token.');
  }
}

function toggleButtonLoading(button, isLoading) {
  if (!button) return;
  button.disabled = isLoading;
  button.classList.toggle('loading', isLoading);
  const spinner = button.querySelector('.loading-icon');
  if (spinner) spinner.style.display = isLoading ? 'inline-block' : 'none';
}

function showMessage(el, msg, isError = false) {
  if (!el) return;

  if (!msg) {
    el.style.display = "none";
    return;
  }

  el.textContent = msg;
  el.style.display = "block";
  el.className = isError ? "error-message" : "message";
}


function escapeHtml(text) {
  if (text === null || text === undefined) return '';
  return String(text).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

/* Minimal Markdown -> HTML (safe, small subset) */
function markdownToHtml(raw) {
  if (raw === null || raw === undefined) return '';
  let s = String(raw);
  s = s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  s = s.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
  s = s.replace(/^\s*#{3}\s*(.+)$/gm, '<div class="md-heading">$1</div>');
  s = s.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>');
  s = s.replace(/\r\n|\r|\n/g, '<br>');
  return s;
}

function setMarkdownInnerHTML(container, rawMarkdown) {
  if (!container) return;
  container.innerHTML = markdownToHtml(rawMarkdown);
}

// ---------------------------
// Auth & UI init
// ---------------------------
function logoutUser() {
  APP_STATE = {
    token: null,
    userId: null,
    username: null,
    summary: null,
    pdfName: null,
    chatHistory: [],
    currentDocumentId: null,
  };
  localStorage.removeItem('legal_app_token');
  localStorage.removeItem('legal_app_user');
  authPage && (authPage.style.display = 'flex');
  appPage && (appPage.style.display = 'none');
  chatMessages && (chatMessages.innerHTML = '');
  try { loginForm.reset(); signupForm.reset(); } catch (e) {}
}

document.addEventListener('DOMContentLoaded', async () => {
  // wire small UI toggles
  $all('.expander-header').forEach(h => {
    h.addEventListener('click', () => {
      const parent = h.parentElement;
      parent.classList.toggle('open');
      const content = parent.querySelector('.expander-content');
      if (content) content.style.display = content.style.display === 'block' ? 'none' : 'block';
      const icon = h.querySelector('i:last-child');
      if (icon) icon.classList.toggle('fa-chevron-up');
    });
  });

  // persisted login
  const token = localStorage.getItem('legal_app_token');
  const user = localStorage.getItem('legal_app_user');
  if (token && user) {
    try {
      const userData = JSON.parse(user);
      APP_STATE.token = token;
      APP_STATE.userId = userData.user_id;
      APP_STATE.username = userData.username;
      APP_STATE.summary = userData.summary;
      APP_STATE.pdfName = userData.pdf_name;
      APP_STATE.chatHistory = userData.chat_history || [];
      APP_STATE.currentDocumentId = userData.current_document_id || null;
      initializeAppUI(userData);
    } catch (e) {
      console.warn('Failed to parse stored user', e);
      localStorage.removeItem('legal_app_token');
      localStorage.removeItem('legal_app_user');
    }
  }
});

// ---------------------------
// UI initialiser + document list
// ---------------------------
async function loadDocuments() {
  try {
    const res = await fetch(`${API_URL}/get-documents`, { headers: authHeaders() });
    const data = await res.json();
    // populate a select if present
    const sel = document.getElementById('document-selector');
    if (sel) {
      sel.innerHTML = '';
      data.documents.forEach(doc => {
        const opt = document.createElement('option');
        opt.value = doc.id;
        opt.textContent = `${doc.pdf_name} (${new Date(doc.created_at).toLocaleDateString()})`;
        sel.appendChild(opt);
      });
      if (data.documents.length > 0) {
        APP_STATE.currentDocumentId = APP_STATE.currentDocumentId || data.documents[0].id;
        sel.value = APP_STATE.currentDocumentId;
      }
    }
  } catch (err) {
    console.warn('Could not load documents', err);
  }
}

function initializeAppUI(userData) {
  authPage && (authPage.style.display = 'none');
  appPage && (appPage.style.display = 'flex');
  if (welcomeMessage) welcomeMessage.textContent = `Welcome, ${userData.username || 'User'}!`;

  if (userData.summary) {
    setMarkdownInnerHTML(summaryText, userData.summary);
    summaryContainer.style.display = 'block';
  } else {
    summaryContainer.style.display = 'none';
  }

  if (userData.pdf_name) {
    uploadStatus.textContent = `✅ Index ready for: ${userData.pdf_name}`;
    uploadStatus.className = 'status-message success';
  } else {
    uploadStatus.textContent = 'ℹ️ No PDF uploaded.';
    uploadStatus.className = 'status-message info';
  }

  chatMessages && (chatMessages.innerHTML = '');
  APP_STATE.chatHistory.forEach(msg => addMessageToChat(msg.role, msg.content, msg.source));

  // load docs & precedents
  loadDocuments().catch(() => {});
  if (userData.precedents && userData.precedents.length) {
    setMarkdownInnerHTML(precedentText, formatPrecedents(userData.precedents || []));
    precedentContainer.style.display = 'block';
  } else {
    loadPreviousPrecedents();
  }
}

// ---------------------------
// Auth events
// ---------------------------
showSignup && showSignup.addEventListener('click', (e) => {
  e.preventDefault();
  loginForm.style.display = 'none';
  signupForm.style.display = 'block';
  showSignup.style.display = 'none';
  showLogin.style.display = 'block';
  showMessage(loginError, '', false);
});

showLogin && showLogin.addEventListener('click', (e) => {
  e.preventDefault();
  loginForm.style.display = 'block';
  signupForm.style.display = 'none';
  showSignup.style.display = 'block';
  showLogin.style.display = 'none';
  showMessage(signupMessage, '', false);
});

function isValidEmail(e) { return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(e); }
function isStrongPassword(pw) { return /^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[\W_]).{8,}$/.test(pw); }

loginForm && loginForm.addEventListener('submit', async (ev) => {
  ev.preventDefault();
  const btn = loginForm.querySelector('button');
  toggleButtonLoading(btn, true);
  showMessage(loginError, '', false);

  const username = $('#login-username').value.trim();
  const password = $('#login-password').value;

  if (!isValidEmail(username)) {
    showMessage(loginError, 'Please use a valid email address to login.', true);
    toggleButtonLoading(btn, false);
    return;
  }

  try {
    const resp = await fetch(`${API_URL}/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
    });
    let data;
    try { data = await resp.json(); } catch (e) { throw new Error('Server returned non-JSON login response'); }
    if (!resp.ok) throw new Error(data.detail || 'Login failed');

    APP_STATE.token = data.access_token;
    APP_STATE.userId = data.user_id;
    APP_STATE.username = data.username;
    APP_STATE.summary = data.summary;
    APP_STATE.pdfName = data.pdf_name;
    APP_STATE.chatHistory = data.chat_history || [];
    APP_STATE.currentDocumentId = data.current_document_id || null;

    localStorage.setItem('legal_app_token', data.access_token);
    localStorage.setItem('legal_app_user', JSON.stringify(data));

    initializeAppUI(data);
  } catch (err) {
    showMessage(loginError, err.message || String(err), true);
  } finally {
    toggleButtonLoading(btn, false);
  }
});

signupForm && signupForm.addEventListener('submit', async (ev) => {
  ev.preventDefault();
  const btn = signupForm.querySelector('button');
  toggleButtonLoading(btn, true);
  showMessage(signupMessage, '', false);

  const username = $('#signup-username').value.trim();
  const password = $('#signup-password').value;

  if (!isValidEmail(username)) {
    showMessage(signupMessage, 'Please register with a valid email address.', true);
    toggleButtonLoading(btn, false);
    return;
  }
  if (!isStrongPassword(password)) {
    showMessage(signupMessage, 'Password must be at least 8 chars and include upper, lower, number, symbol.', true);
    toggleButtonLoading(btn, false);
    return;
  }

  try {
    const resp = await fetch(`${API_URL}/signup`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
    });
    let data;
    try { data = await resp.json(); } catch (e) { throw new Error('Server returned non-JSON signup response'); }
    if (!resp.ok) throw new Error(data.detail || 'Signup failed');

    showMessage(signupMessage, data.message || 'Signup successful. Please login.', false);
    showLogin.click();
  } catch (err) {
    showMessage(signupMessage, err.message || String(err), true);
  } finally {
    toggleButtonLoading(btn, false);
  }
});

logoutButton && logoutButton.addEventListener('click', () => logoutUser());

// ---------------------------
// Upload PDF
// ---------------------------
uploadButton && uploadButton.addEventListener('click', () => fileUploader.click());

fileUploader && fileUploader.addEventListener('change', async () => {
  const file = fileUploader.files[0];
  if (!file) return;
  if (file.type !== 'application/pdf') {
    showMessage(appError, 'Error: Only PDF files are allowed.', true);
    return;
  }

  const btn = uploadButton;
  toggleButtonLoading(btn, true);
  showMessage(appError, '', false);

  const fd = new FormData();
  fd.append('file', file);

  try {
    const resp = await fetch(`${API_URL}/upload`, {
      method: 'POST',
      headers: authHeaders(), // may throw
      body: fd,
    });
    if (resp.status === 401) handleAuthError(resp.status);

    let data;
    try { data = await resp.json(); } catch (e) { throw new Error('Unexpected upload response (not JSON)'); }
    if (!resp.ok) throw new Error(data.detail || 'File upload failed');

    // Save info + refresh doc list
    APP_STATE.currentDocumentId = data.document_id;
    APP_STATE.summary = data.summary;
    APP_STATE.pdfName = data.pdf_name;
    setMarkdownInnerHTML(summaryText, data.summary);
    summaryContainer.style.display = 'block';
    uploadStatus.textContent = `✅ Index ready for: ${data.pdf_name}`;
    uploadStatus.className = 'status-message success';

    try {
      const user = JSON.parse(localStorage.getItem('legal_app_user') || '{}');
      user.summary = data.summary;
      user.pdf_name = data.pdf_name;
      user.current_document_id = data.document_id;
      localStorage.setItem('legal_app_user', JSON.stringify(user));
    } catch (err) { console.warn('Failed to update local user', err); }

    await loadDocuments();
  } catch (err) {
    showMessage(appError, err.message || String(err), true);
  } finally {
    toggleButtonLoading(btn, false);
    fileUploader.value = '';
  }
});

// ---------------------------
// Find Precedents
// ---------------------------
precedentButton && precedentButton.addEventListener('click', async () => {
  if (!APP_STATE.summary) {
    showMessage(appError, 'Error: Please upload a document first.', true);
    return;
  }
  toggleButtonLoading(precedentButton, true);
  showMessage(appError, '', false);

  try {
    const res = await fetch(`${API_URL}/find-precedents`, {
      method: 'POST',
      headers: authHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({ document_id: APP_STATE.currentDocumentId }),
    });
    if (res.status === 401) handleAuthError(res.status);

    let data;
    try { data = await res.json(); } catch (e) { throw new Error('Unexpected response while finding precedents'); }
    if (!res.ok) throw new Error(data.detail || 'Failed to find precedents');

    let rendered = '';
    if (Array.isArray(data.precedents)) {
      rendered = data.precedents.map((p, i) => `**${i+1}. ${escapeHtml(p.name || p.title || 'Unnamed')}**<br>${p.court || ''} ${p.year || ''}<br>${p.url ? `[View Case](${p.url})` : ''}`).join('<br><br>');
    } else if (typeof data.precedents === 'object' && data.precedents !== null) {
      rendered = JSON.stringify(data.precedents, null, 2);
    } else {
      rendered = data.precedents || 'No precedents found.';
    }

    setMarkdownInnerHTML(precedentText, rendered);
    precedentContainer.style.display = 'block';
  } catch (err) {
    showMessage(appError, err.message || String(err), true);
  } finally {
    toggleButtonLoading(precedentButton, false);
  }
});

function formatPrecedents(precedents) {
  return precedents.map((p, i) => `**${i+1}. ${escapeHtml(p.name || 'Unnamed')}**<br>${escapeHtml(p.court || 'Unknown')} (${p.year || 'N/A'})<br>${p.url ? `[Read](${p.url})` : ''}`).join('<br><hr>');
}

function loadPreviousPrecedents() {
  fetch(`${API_URL}/get-precedents`, {
    method: 'GET',
    headers: authHeaders(),
  })
  .then(res => res.json())
  .then(data => {
    if (!Array.isArray(data) && Array.isArray(data.precedents)) data = data.precedents;
    const pText = document.getElementById('precedent-text');
    if (!pText) return;
    if (!data || !data.length) {
      pText.innerHTML = "<i>No saved precedents yet.</i>";
      return;
    }
    pText.innerHTML = data.map(p => `
      <div class="precedent-card">
        <b>${escapeHtml(p.name)}</b><br>
        ${escapeHtml(p.court || 'Unknown')} (${escapeHtml(p.year || 'N/A')})<br>
        ${p.url ? `<a href="${p.url}" target="_blank">View Case</a><br>` : ''}
        <small>Source: ${escapeHtml(p.source || 'N/A')} • ${new Date(p.created_at || Date.now()).toLocaleString()}</small>
      </div>
    `).join('<hr>');
    document.getElementById('precedent-container').style.display = 'block';
  })
  .catch(err => {
    console.warn('Error loading precedents:', err);
  });
}

// ---------------------------
// Chat
// ---------------------------
chatForm && chatForm.addEventListener('submit', async (e) => {
  e.preventDefault();
  const query = chatInput.value.trim();
  if (!query) return;
  chatInput.value = '';
  addMessageToChat('user', query);

  addMessageToChat('assistant', '...', null, true); // loading

  try {
    const resp = await fetch(`${API_URL}/chat`, {
      method: 'POST',
      headers: authHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({ query, document_id: APP_STATE.currentDocumentId }),
    });
    if (resp.status === 401) handleAuthError(resp.status);

    let data;
    try { data = await resp.json(); } catch (e) { throw new Error('Unexpected response from server (not JSON).'); }
    if (!resp.ok) throw new Error(data.detail || 'Chat request failed');

    updateLastAssistantMessage(data.answer, data.source);

    // fact check UI (optional)
    // Save fact checks silently (NOT shown in chat)
if (data.fact_check && data.fact_check.length) {
  try {
    const user = JSON.parse(localStorage.getItem('legal_app_user') || '{}');

    if (!user.fact_history) user.fact_history = [];

    data.fact_check.forEach(fc => {
      user.fact_history.push({
        statement: fc.statement,
        supported: fc.supported,
        confidence: fc.confidence,
        evidence: fc.evidence,
        timestamp: Date.now()
      });
    });

    localStorage.setItem('legal_app_user', JSON.stringify(user));
  } catch (err) {
    console.warn("Could not save fact history", err);
  }
}


    // persist chat locally
    APP_STATE.chatHistory.push({ role: 'user', content: query });
    APP_STATE.chatHistory.push({ role: 'assistant', content: data.answer, source: data.source });
    try {
      const user = JSON.parse(localStorage.getItem('legal_app_user') || '{}');
      user.chat_history = APP_STATE.chatHistory;
      localStorage.setItem('legal_app_user', JSON.stringify(user));
    } catch (err) { console.warn('Failed to update chat history locally', err); }

  } catch (err) {
    updateLastAssistantMessage(`Error: ${err.message}`, 'Error');
  }
});

// Chat UI helpers
function addMessageToChat(role, content, source = null, isLoading = false) {
  if (!chatMessages) return;
  const msgDiv = document.createElement('div');
  msgDiv.className = `chat-message ${role}`;
  const iconClass = role === 'user' ? 'fa-user' : 'fa-gavel';
  const iconColor = role === 'user' ? 'var(--text-secondary)' : 'var(--color-primary)';
  let contentHTML = '';
  if (isLoading) {
    contentHTML = '<i class="fas fa-spinner fa-spin loading-icon"></i>';
  } else {
    contentHTML = `<div class="markdown-content">${markdownToHtml(content)}</div>`;
    if (source) contentHTML += `<div class="message-source">Source: ${escapeHtml(source)}</div>`;
  }
  msgDiv.innerHTML = `
    <div class="icon"><i class="fas ${iconClass}" style="color:${iconColor}"></i></div>
    <div class="message-content">${contentHTML}</div>
  `;
  chatMessages.appendChild(msgDiv);
  chatMessages.scrollTop = chatMessages.scrollHeight;
}

function updateLastAssistantMessage(content, source = null) {
  if (!chatMessages) return;
  const loadingMsg = chatMessages.querySelector('.chat-message.assistant:last-child');
  const isLoading = loadingMsg && loadingMsg.querySelector('.fa-spinner');
  if (loadingMsg && isLoading) {
    loadingMsg.querySelector('.message-content').innerHTML = `<div class="markdown-content">${markdownToHtml(content)}</div>${source ? `<div class="message-source">Source: ${escapeHtml(source)}</div>`: ''}`;
    chatMessages.scrollTop = chatMessages.scrollHeight;
  } else addMessageToChat('assistant', content, source);
}

// ---------------------------
// Fact history
// ---------------------------
const factBtn = $("#fact-history-button");
factBtn && factBtn.addEventListener('click', async () => {
  toggleButtonLoading(factBtn, true);
  try {
    const res = await fetch(`${API_URL}/fact-history`, { method: 'GET', headers: authHeaders() });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Failed to load history');

    const container = $("#fact-history-container");
    const content = $("#fact-history-content");
    if (!content) return;
    container.style.display = 'block';
    if (!data.history || !data.history.length) {
      content.innerHTML = "<i>No fact checks yet.</i>";
    } else {
      content.innerHTML = data.history.map(h => `
        <div class="fact-item">
          <strong>${escapeHtml(h.statement)}</strong><br>
          Supported: ${h.supported ? '✅' : '❌'} • Confidence: ${(h.confidence*100).toFixed(1)}%<br>
          Evidence: ${escapeHtml(h.evidence || 'N/A')}<br>
          <small>${new Date(h.timestamp).toLocaleString()}</small>
        </div>
      `).join('<hr>');
      
    }
  } catch (err) {
    appError && (appError.textContent = err.message || String(err));
  } finally {
    toggleButtonLoading(factBtn, false);
  }
});
// ---------------------------
// Geoapify + Leaflet lawyer search (fixed)
// ---------------------------
document.getElementById("search-lawyer-btn")?.addEventListener("click", () => {
  const place = document.getElementById("lawyer-search-input").value.trim();

  if (!place) {
    alert("Please enter a location.");
    return;
  }

  // open Google Maps directly
  const url = `https://www.google.com/maps/search/lawyers+near+${encodeURIComponent(place)}`;
  // window.location.href = url; // go to maps directly
  window.open(url, "_blank");  // go to new tab

});



function renderPrecedents(list) {
    const container = document.getElementById("precedents-list");
    container.innerHTML = "";

    list.forEach((html) => {
        const div = document.createElement("div");
        div.innerHTML = html;   // PRETTY RENDERED
        container.appendChild(div);
    });
}
