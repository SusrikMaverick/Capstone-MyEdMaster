let activeChat = null;
let sending = false;

const $ = (s) => document.querySelector(s);
const chatArea = $('#chatArea');
const sidebarList = $('#sidebarList');
const msgInput = $('#msgInput');
const sendBtn = $('#sendBtn');

// ── API helpers ──

async function api(path, opts = {}) {
  const res = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...opts,
  });
  return res.json();
}

// ── Sidebar ──

async function loadChats() {
  const data = await api('/api/chats');
  activeChat = activeChat || data.active;
  renderSidebar(data.chats, activeChat);
}

function renderSidebar(chats, currentId) {
  if (!chats.length) {
    sidebarList.innerHTML = '<div class="sidebar-empty">No chats yet</div>';
    return;
  }
  sidebarList.innerHTML = chats.map(c => {
    const cls = c.id === currentId ? ' active' : '';
    const date = (c.created || '').slice(0, 10);
    return `<div class="sidebar-item${cls}">
      <div class="sidebar-link" data-id="${c.id}">
        <span class="sidebar-title">${esc(c.title)}</span>
        <span class="sidebar-date">${date}</span>
      </div>
      <button class="sidebar-del" data-id="${c.id}" title="Delete chat">&times;</button>
    </div>`;
  }).join('');
}

sidebarList.addEventListener('click', async (e) => {
  const link = e.target.closest('.sidebar-link');
  const del = e.target.closest('.sidebar-del');

  if (del) {
    if (!confirm('Delete this chat?')) return;
    await api(`/api/chats/${del.dataset.id}`, { method: 'DELETE' });
    if (del.dataset.id === activeChat) activeChat = null;
    await loadChats();
    if (activeChat) await selectChat(activeChat);
    else showEmpty();
    return;
  }

  if (link) {
    await selectChat(link.dataset.id);
    closeMobileSidebar();
  }
});

// ── Chat selection ──

async function selectChat(id) {
  activeChat = id;
  const data = await api(`/api/chats/${id}/messages`);
  renderMessages(data.messages);
  await loadChats();
}

function renderMessages(messages) {
  if (!messages.length) { showEmpty(); return; }
  chatArea.innerHTML = messages.map(m =>
    m.role === 'user'
      ? `<div class="msg-row msg-user"><div class="bubble bubble-user">${esc(m.content)}</div></div>`
      : `<div class="msg-row msg-bot"><div class="avatar">M</div><div class="bubble bubble-bot">${esc(m.content)}</div></div>`
  ).join('');
  scrollBottom();
}

function showEmpty() {
  chatArea.innerHTML =
    '<div class="empty-state">' +
    '<div class="empty-icon">&#9878;</div>' +
    '<p class="empty-title">Welcome to MyEdMaster Legal Chatbot</p>' +
    '<p class="empty-sub">Ask any legal question about business or education topics to get started.</p>' +
    '</div>';
}

// ── New chat ──

$('#newChatBtn').addEventListener('click', async () => {
  const data = await api('/api/chats', { method: 'POST' });
  activeChat = data.id;
  showEmpty();
  await loadChats();
  msgInput.focus();
});

// ── Send message ──

async function sendMessage() {
  const text = msgInput.value.trim();
  if (!text || sending) return;

  if (!activeChat) {
    const data = await api('/api/chats', { method: 'POST' });
    activeChat = data.id;
  }

  sending = true;
  sendBtn.disabled = true;

  // Show user bubble immediately
  if (chatArea.querySelector('.empty-state')) chatArea.innerHTML = '';
  appendBubble('user', text);
  msgInput.value = '';
  msgInput.style.height = 'auto';

  // Show typing indicator
  const typingEl = appendTyping();
  scrollBottom();

  try {
    const data = await api(`/api/chats/${activeChat}/messages`, {
      method: 'POST',
      body: JSON.stringify({ message: text }),
    });
    typingEl.remove();
    if (data.error) {
      appendError(data.error);
    } else {
      appendBubble('assistant', data.reply);
    }
  } catch (err) {
    typingEl.remove();
    appendError('Network error. Please try again.');
  }

  sending = false;
  sendBtn.disabled = false;
  scrollBottom();
  await loadChats();
  msgInput.focus();
}

sendBtn.addEventListener('click', sendMessage);

msgInput.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
});

msgInput.addEventListener('input', () => {
  msgInput.style.height = 'auto';
  msgInput.style.height = Math.min(msgInput.scrollHeight, 120) + 'px';
});

// ── DOM helpers ──

function appendBubble(role, content) {
  const div = document.createElement('div');
  if (role === 'user') {
    div.className = 'msg-row msg-user';
    div.innerHTML = `<div class="bubble bubble-user">${esc(content)}</div>`;
  } else {
    div.className = 'msg-row msg-bot';
    div.innerHTML = `<div class="avatar">M</div><div class="bubble bubble-bot">${esc(content)}</div>`;
  }
  chatArea.appendChild(div);
}

function appendTyping() {
  const div = document.createElement('div');
  div.className = 'msg-row msg-bot';
  div.innerHTML = '<div class="avatar">M</div><div class="bubble bubble-bot typing-dots"><span></span><span></span><span></span></div>';
  chatArea.appendChild(div);
  return div;
}

function appendError(msg) {
  const div = document.createElement('div');
  div.className = 'error-banner';
  div.textContent = msg;
  chatArea.appendChild(div);
}

function scrollBottom() {
  chatArea.scrollTop = chatArea.scrollHeight;
}

function esc(str) {
  const d = document.createElement('div');
  d.textContent = str;
  return d.innerHTML.replace(/\n/g, '<br>');
}

// ── Theme toggle ──

const toggle = $('#themeToggle');
const saved = localStorage.getItem('theme');
if (saved === 'dark' || (!saved && window.matchMedia('(prefers-color-scheme:dark)').matches)) {
  document.documentElement.setAttribute('data-theme', 'dark');
  toggle.classList.add('night');
}
toggle.addEventListener('click', () => {
  const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
  document.documentElement.setAttribute('data-theme', isDark ? 'light' : 'dark');
  toggle.classList.toggle('night', !isDark);
  localStorage.setItem('theme', isDark ? 'light' : 'dark');
});

// ── Mobile sidebar ──

const sidebar = $('#sidebar');
const overlay = $('#overlay');

$('#menuBtn').addEventListener('click', () => {
  sidebar.classList.toggle('open');
  overlay.classList.toggle('open');
});
overlay.addEventListener('click', closeMobileSidebar);

function closeMobileSidebar() {
  sidebar.classList.remove('open');
  overlay.classList.remove('open');
}

// ── Init ──

(async () => {
  await loadChats();
  if (activeChat) await selectChat(activeChat);
})();
