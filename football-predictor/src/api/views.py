from __future__ import annotations

# These pages intentionally remain dependency-free server-rendered tools.
SPORTTTERY_EDITOR_HTML = """
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>体彩让球盘编辑器</title>
  <style>
    body { margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: #f6f8fb; color: #1f2937; }
    header { padding: 18px 24px; background: #0f172a; color: #fff; }
    header h1 { margin: 0; font-size: 22px; }
    header p { margin: 6px 0 0; color: #cbd5e1; }
    main { max-width: 1180px; margin: 22px auto; padding: 0 18px 36px; }
    .toolbar { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; margin-bottom: 14px; }
    input, textarea { box-sizing: border-box; width: 100%; padding: 8px 10px; border: 1px solid #cbd5e1; border-radius: 8px; font: inherit; background: #fff; }
    input:focus, textarea:focus { outline: 2px solid #93c5fd; border-color: #2563eb; }
    input[type="date"] { width: 180px; }
    button { border: 0; border-radius: 8px; padding: 9px 14px; font-weight: 700; cursor: pointer; }
    .primary { background: #2563eb; color: #fff; }
    .secondary { background: #e2e8f0; color: #0f172a; }
    .danger { background: #fee2e2; color: #991b1b; }
    .card { background: #fff; border: 1px solid #e5e7eb; border-radius: 14px; box-shadow: 0 8px 20px rgba(15, 23, 42, 0.06); overflow: hidden; }
    .summary { padding: 14px 16px; border-bottom: 1px solid #e5e7eb; display: flex; gap: 16px; flex-wrap: wrap; color: #475569; }
    table { width: 100%; border-collapse: collapse; }
    th, td { border-bottom: 1px solid #e5e7eb; padding: 9px; vertical-align: top; }
    th { background: #f8fafc; text-align: left; font-size: 13px; color: #475569; }
    td { font-size: 14px; }
    .small { width: 105px; }
    .medium { width: 150px; }
    .handicap { width: 130px; }
    .notes { min-width: 180px; }
    .status { margin-top: 12px; padding: 10px 12px; border-radius: 10px; display: none; }
    .ok { display: block; background: #dcfce7; color: #166534; }
    .err { display: block; background: #fee2e2; color: #991b1b; }
    .hint { margin: 12px 0; color: #64748b; line-height: 1.6; }
    code { background: #eef2ff; color: #3730a3; padding: 2px 5px; border-radius: 5px; }
  </style>
</head>
<body>
  <header>
    <h1>体彩让球盘编辑器</h1>
    <p>填写中国体彩竞彩足球让球胜平负盘口，保存后日报流水线会优先使用这些真实盘口。</p>
  </header>
  <main>
    <div class="toolbar">
      <input id="date" type="date" />
      <input id="snapshotType" value="latest" placeholder="盘口阶段：opening/live/closing" />
      <input id="capturedAt" placeholder="采集时间，可留空自动生成" />
      <button class="secondary" id="load">加载当天比赛</button>
      <button class="primary" id="save">保存 CSV</button>
      <button class="danger" id="clear">清空盘口列</button>
    </div>
    <div class="hint">
      让球写法支持：<code>主队让1球</code>、<code>主队受让1球</code>、<code>平手盘</code>、<code>-1</code>、<code>+1</code>、<code>0</code>。
      负数代表主队让球，正数代表主队受让。请只填已核验的官方体彩盘口。
    </div>
    <div class="card" style="margin-bottom:14px; padding:14px 16px;">
      <strong>批量粘贴盘口</strong>
      <p class="hint">可从网页或 Excel 复制多行，例如：<code>周四001    Japan    Sweden    主队让1球</code>。解析后会按竞彩编号、match_id 或主客队填入下方表格。</p>
      <textarea id="pasteBox" rows="5" placeholder="周四001    Japan    Sweden    主队让1球&#10;周四002    Ecuador    Germany    平手盘"></textarea>
      <div class="toolbar" style="margin-top:10px; margin-bottom:0;">
        <button class="secondary" id="applyPaste">解析并填入</button>
        <button class="secondary" id="clearPaste">清空粘贴框</button>
      </div>
    </div>
    <div id="status" class="status"></div>
    <div class="card">
      <div class="summary" id="summary">尚未加载</div>
      <table>
        <thead>
          <tr>
            <th>日期</th>
            <th>match_id</th>
            <th>竞彩编号</th>
            <th>主队</th>
            <th>客队</th>
            <th>让球盘</th>
            <th>来源</th>
            <th>更新时间</th>
            <th>备注</th>
          </tr>
        </thead>
        <tbody id="rows"></tbody>
      </table>
    </div>
  </main>
  <script>
    const dateInput = document.getElementById('date');
    const rowsEl = document.getElementById('rows');
    const summaryEl = document.getElementById('summary');
    const statusEl = document.getElementById('status');
    const today = new Date().toISOString().slice(0, 10);
    dateInput.value = today;

    function setStatus(text, ok = true) {
      statusEl.textContent = text;
      statusEl.className = 'status ' + (ok ? 'ok' : 'err');
    }

    function cellInput(value, cls, placeholder = '') {
      const escaped = String(value || '').replaceAll('&', '&amp;').replaceAll('"', '&quot;').replaceAll('<', '&lt;');
      return `<input class="${cls}" value="${escaped}" placeholder="${placeholder}" />`;
    }

    function render(data) {
      summaryEl.textContent = `日期 ${data.date} | 文件 ${data.exists ? '已存在' : '未创建'} | 已填 ${data.filled_count}/${data.count} | ${data.path}`;
      rowsEl.innerHTML = data.rows.map(row => `
        <tr>
          <td data-field="date">${row.date}</td>
          <td data-field="match_id">${row.match_id || ''}</td>
          <td>${cellInput(row.match_number, 'match_number small', '周四001')}</td>
          <td data-field="home_team">${row.home_team}</td>
          <td data-field="away_team">${row.away_team}</td>
          <td>${cellInput(row.home_handicap_raw, 'home_handicap handicap', '主队让1球')}</td>
          <td>${cellInput(row.source || 'sporttery_manual', 'source medium')}</td>
          <td>${cellInput(row.updated_at, 'updated_at medium', '2026-06-25 10:00')}</td>
          <td>${cellInput(row.notes, 'notes')}</td>
        </tr>
      `).join('');
    }

    async function loadRows() {
      statusEl.className = 'status';
      const date = dateInput.value;
      const res = await fetch(`/world-cup/sporttery/handicap-markets?date=${encodeURIComponent(date)}`);
      if (!res.ok) {
        setStatus(await res.text(), false);
        return;
      }
      render(await res.json());
    }

    function collectRows() {
      return [...rowsEl.querySelectorAll('tr')].map(tr => ({
        date: tr.querySelector('[data-field="date"]').textContent.trim(),
        match_id: tr.querySelector('[data-field="match_id"]').textContent.trim(),
        match_number: tr.querySelector('.match_number').value.trim(),
        home_team: tr.querySelector('[data-field="home_team"]').textContent.trim(),
        away_team: tr.querySelector('[data-field="away_team"]').textContent.trim(),
        home_handicap: tr.querySelector('.home_handicap').value.trim(),
        source: tr.querySelector('.source').value.trim() || 'sporttery_manual',
        updated_at: tr.querySelector('.updated_at').value.trim(),
        notes: tr.querySelector('.notes').value.trim(),
      }));
    }

    async function saveRows() {
      const payload = {
        date: dateInput.value,
        snapshot_type: document.getElementById('snapshotType').value.trim() || 'latest',
        captured_at: document.getElementById('capturedAt').value.trim(),
        rows: collectRows()
      };
      const res = await fetch('/world-cup/sporttery/handicap-markets', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      const text = await res.text();
      if (!res.ok) {
        setStatus(text, false);
        return;
      }
      const data = JSON.parse(text);
      setStatus(`已保存：${data.filled_count}/${data.count} 条盘口，最新文件 ${data.path}，历史累计 ${data.history_count} 条`);
      await loadRows();
    }

    function normalizeText(value) {
      return String(value || "").trim().toLowerCase();
    }

    function applyParsedRows(parsedRows) {
      let applied = 0;
      const trs = [...rowsEl.querySelectorAll("tr")];
      for (const parsed of parsedRows) {
        const parsedMatchNumber = normalizeText(parsed.match_number);
        const parsedHome = normalizeText(parsed.home_team);
        const parsedAway = normalizeText(parsed.away_team);
        const target = trs.find(tr => {
          const matchNumber = normalizeText(tr.querySelector(".match_number").value);
          const matchId = normalizeText(tr.querySelector('[data-field="match_id"]').textContent);
          const home = normalizeText(tr.querySelector('[data-field="home_team"]').textContent);
          const away = normalizeText(tr.querySelector('[data-field="away_team"]').textContent);
          return (parsedMatchNumber && (parsedMatchNumber === matchNumber || parsedMatchNumber === matchId))
            || (parsedHome && parsedAway && home === parsedHome && away === parsedAway);
        });
        if (!target) continue;
        if (parsed.match_number) target.querySelector(".match_number").value = parsed.match_number;
        target.querySelector(".home_handicap").value = parsed.home_handicap || "";
        target.querySelector(".source").value = "sporttery_paste";
        applied += 1;
      }
      return applied;
    }

    async function parsePasteAndApply() {
      const text = document.getElementById("pasteBox").value;
      const res = await fetch("/world-cup/sporttery/parse-paste", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text }),
      });
      const body = await res.json();
      if (!res.ok) {
        setStatus(JSON.stringify(body), false);
        return;
      }
      const applied = applyParsedRows(body.rows || []);
      setStatus(`解析 ${body.count} 条，成功填入 ${applied} 条。请核对后保存。`, applied > 0);
    }

    document.getElementById('load').addEventListener('click', loadRows);
    document.getElementById('save').addEventListener('click', saveRows);
    document.getElementById('applyPaste').addEventListener('click', parsePasteAndApply);
    document.getElementById('clearPaste').addEventListener('click', () => {
      document.getElementById('pasteBox').value = '';
    });
    document.getElementById('clear').addEventListener('click', () => {
      rowsEl.querySelectorAll('.home_handicap').forEach(input => input.value = '');
    });
    loadRows();
  </script>
</body>
</html>
"""

CHAT_UI_HTML = """
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>足球预测研究员 Copilot</title>
  <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
  <style>
    body { font-family: 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; margin: 0; background-color: #f0f2f5; color: #333; }
    header { background: linear-gradient(135deg, #0b5fff, #0033a0); color: #fff; padding: 16px 20px; font-size: 1.2rem; font-weight: bold; box-shadow: 0 2px 4px rgba(0,0,0,0.1); display: flex; align-items: center; gap: 10px; }
    #chat-container { display: flex; flex-direction: column; height: calc(100vh - 60px); max-width: 900px; margin: 0 auto; background: #fff; box-shadow: 0 0 15px rgba(0,0,0,0.05); }
    #chat { flex: 1; padding: 20px; overflow-y: auto; display: flex; flex-direction: column; gap: 16px; scroll-behavior: smooth; }
    .msg { display: flex; width: 100%; }
    .msg.user { justify-content: flex-end; }
    .msg.assistant { justify-content: flex-start; }
    .bubble { max-width: 80%; padding: 12px 16px; border-radius: 12px; line-height: 1.5; font-size: 0.95rem; box-shadow: 0 1px 2px rgba(0,0,0,0.1); }
    .msg.user .bubble { background: #0b5fff; color: #fff; border-bottom-right-radius: 4px; }
    .msg.assistant .bubble { background: #f7f9fc; color: #333; border: 1px solid #e1e4e8; border-bottom-left-radius: 4px; }

    /* Markdown Styles */
    .bubble p { margin-top: 0; margin-bottom: 0.8em; }
    .bubble p:last-child { margin-bottom: 0; }
    .bubble a { color: #0b5fff; text-decoration: none; font-weight: 500; }
    .msg.user .bubble a { color: #eef3ff; text-decoration: underline; }
    .bubble code { background: rgba(0,0,0,0.06); padding: 2px 4px; border-radius: 4px; font-family: monospace; font-size: 0.9em; }
    .msg.user .bubble code { background: rgba(255,255,255,0.2); }
    .bubble pre { background: #2d3748; color: #f8f8f2; padding: 12px; border-radius: 8px; overflow-x: auto; margin: 10px 0; font-size: 0.9em; }
    .bubble pre code { background: transparent; color: inherit; padding: 0; }
    .bubble table { border-collapse: collapse; width: 100%; margin: 10px 0; font-size: 0.9em; }
    .bubble th, .bubble td { border: 1px solid #e2e8f0; padding: 8px 12px; text-align: left; }
    .bubble th { background-color: #edf2f7; font-weight: 600; }
    .bubble ul, .bubble ol { margin-top: 0; margin-bottom: 0.8em; padding-left: 20px; }
    .bubble blockquote { border-left: 4px solid #cbd5e0; margin: 0; padding-left: 12px; color: #4a5568; }

    #box { display: flex; gap: 12px; padding: 16px; background: #fff; border-top: 1px solid #eaeaea; }
    textarea { flex: 1; padding: 12px; border-radius: 8px; border: 1px solid #d1d5db; resize: none; height: 48px; font-family: inherit; font-size: 0.95rem; outline: none; transition: border-color 0.2s; box-shadow: inset 0 1px 2px rgba(0,0,0,0.05); }
    textarea:focus { border-color: #0b5fff; }
    button { padding: 0 24px; border: 0; border-radius: 8px; background: #0b5fff; color: #fff; font-weight: 600; font-size: 0.95rem; cursor: pointer; transition: background-color 0.2s; display: flex; align-items: center; justify-content: center; }
    button:hover { background: #0046cc; }
    button[disabled] { opacity: 0.6; cursor: not-allowed; }

    /* Loading animation */
    .typing { display: flex; gap: 4px; padding: 4px 8px; }
    .typing .dot { width: 6px; height: 6px; background-color: #888; border-radius: 50%; animation: typing 1.4s infinite ease-in-out both; }
    .typing .dot:nth-child(1) { animation-delay: -0.32s; }
    .typing .dot:nth-child(2) { animation-delay: -0.16s; }
    @keyframes typing { 0%, 80%, 100% { transform: scale(0); } 40% { transform: scale(1); } }
  </style>
</head>
<body>
  <header>
    <span>⚽</span> 足球预测研究员 Copilot
  </header>
  <div id="chat-container">
    <div id="chat">
        <div class="msg assistant">
            <div class="bubble">你好！我是你的 AI 足球预测助手 🤖。我可以帮你获取今日赛程、运行预测模型、分析回测数据。想了解点什么？</div>
        </div>
    </div>
    <div id="box">
      <textarea id="input" placeholder="输入你的问题，如：帮我查一下今天有什么比赛，并跑一下预测推荐..."></textarea>
      <button id="send">发送 🚀</button>
    </div>
  </div>
  <script>
    const chatDiv = document.getElementById('chat');
    const input = document.getElementById('input');
    const sendBtn = document.getElementById('send');
    const hist = [];

    // Configure marked to use breaks for newlines
    marked.setOptions({ breaks: true, gfm: true });

    function addMessage(role, text) {
      const wrapper = document.createElement('div');
      wrapper.className = `msg ${role}`;

      const bubble = document.createElement('div');
      bubble.className = 'bubble';

      if (role === 'assistant') {
          bubble.innerHTML = marked.parse(text);
      } else {
          bubble.textContent = text;
      }

      wrapper.appendChild(bubble);
      chatDiv.appendChild(wrapper);
      chatDiv.scrollTop = chatDiv.scrollHeight;
    }

    function addLoading() {
        const wrapper = document.createElement('div');
        wrapper.className = 'msg assistant';
        wrapper.id = 'loading-msg';

        const bubble = document.createElement('div');
        bubble.className = 'bubble';
        bubble.innerHTML = '<div class="typing"><div class="dot"></div><div class="dot"></div><div class="dot"></div></div>';

        wrapper.appendChild(bubble);
        chatDiv.appendChild(wrapper);
        chatDiv.scrollTop = chatDiv.scrollHeight;
    }

    function removeLoading() {
        const loading = document.getElementById('loading-msg');
        if (loading) {
            loading.remove();
        }
    }

    async function send() {
      const text = input.value.trim();
      if(!text) return;

      input.value = '';
      addMessage('user', text);
      hist.push({role:'user', content:text});

      sendBtn.disabled = true;
      input.disabled = true;
      addLoading();

      try {
        const r = await fetch('/chat', {
          method: 'POST',
          headers: {'Content-Type':'application/json'},
          body: JSON.stringify({messages: hist})
        });
        const j = await r.json();
        removeLoading();

        const content = j.content || '⚠️ [error] 无内容';
        addMessage('assistant', content);
        hist.push({role:'assistant', content});
      } catch(e) {
        removeLoading();
        addMessage('assistant', '❌ [error] ' + e);
      } finally {
        sendBtn.disabled = false;
        input.disabled = false;
        input.focus();
      }
    }

    sendBtn.addEventListener('click', send);
    input.addEventListener('keydown', e => {
      if (!e.shiftKey && e.key === 'Enter') {
          e.preventDefault();
          send();
      }
    });
  </script>
</body>
</html>
"""
