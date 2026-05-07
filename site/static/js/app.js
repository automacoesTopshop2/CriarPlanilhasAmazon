/* ==========================================================================
   PLANILHAS AMAZON — INTERAÇÕES DE FRONTEND
   --------------------------------------------------------------------------
   - Dropzones (drag-and-drop + click-to-select)
   - Sincronização de bases (sidebar)
   - Pipeline de processamento com SSE
   - CRUD de termos de limpeza
   ========================================================================== */

(function () {
    'use strict';

    // ---------- CSRF ----------
    function csrf() {
        const m = document.querySelector('meta[name="csrf-token"]');
        return m ? m.getAttribute('content') : '';
    }

    // ---------- Toasts ----------
    const toastHost = () => document.getElementById('toast-host');
    function toast(msg, kind) {
        const host = toastHost();
        if (!host) return;
        const el = document.createElement('div');
        el.className = 'toast' + (kind === 'ok' ? ' toast--ok' : kind === 'err' ? ' toast--err' : '');
        el.textContent = msg;
        host.appendChild(el);
        setTimeout(() => {
            el.style.opacity = '0';
            el.style.transform = 'translateX(20px)';
            el.style.transition = 'opacity 0.2s, transform 0.2s';
            setTimeout(() => el.remove(), 220);
        }, 3500);
    }
    window.toast = toast;

    // ---------- Helpers ----------
    function fmtBytes(bytes) {
        if (!bytes && bytes !== 0) return '';
        const k = 1024, units = ['B', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return (bytes / Math.pow(k, i)).toFixed(i ? 1 : 0) + ' ' + units[i];
    }

    // ==========================================================
    // DROPZONES
    // ==========================================================
    const dropzoneFiles = {}; // field -> File

    function setupDropzones() {
        document.querySelectorAll('[data-role="dropzone"]').forEach(setupDropzone);
    }

    function setupDropzone(zone) {
        const field = zone.dataset.field || 'entrada';
        const input = zone.querySelector('[data-role="dropzone-input"]');
        const empty = zone.querySelector('[data-role="dropzone-empty"]');
        const iconEmpty = zone.querySelector('[data-role="dropzone-icon-empty"]');
        const filled = zone.querySelector('[data-role="dropzone-filled"]');
        const nameEl = zone.querySelector('[data-role="dropzone-name"]');
        const sizeEl = zone.querySelector('[data-role="dropzone-size"]');
        const clearBtn = zone.querySelector('[data-role="dropzone-clear"]');

        function setFile(file) {
            if (!file) return;
            dropzoneFiles[field] = file;
            zone.classList.add('has-file');
            empty.classList.add('hide');
            iconEmpty.classList.add('hide');
            filled.classList.remove('hide');
            nameEl.textContent = file.name;
            sizeEl.textContent = fmtBytes(file.size);
            updateProcessButton();
            updateSteps();
        }

        function clearFile(e) {
            if (e) { e.preventDefault(); e.stopPropagation(); }
            delete dropzoneFiles[field];
            zone.classList.remove('has-file');
            empty.classList.remove('hide');
            iconEmpty.classList.remove('hide');
            filled.classList.add('hide');
            input.value = '';
            updateProcessButton();
            updateSteps();
        }

        input.addEventListener('change', () => {
            if (input.files && input.files[0]) setFile(input.files[0]);
        });
        clearBtn.addEventListener('click', clearFile);

        ['dragenter', 'dragover'].forEach(ev =>
            zone.addEventListener(ev, e => {
                e.preventDefault(); e.stopPropagation();
                zone.classList.add('is-dragging');
            })
        );
        ['dragleave', 'drop'].forEach(ev =>
            zone.addEventListener(ev, e => {
                e.preventDefault(); e.stopPropagation();
                zone.classList.remove('is-dragging');
            })
        );
        zone.addEventListener('drop', e => {
            const file = e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0];
            if (file) setFile(file);
        });
    }

    function updateProcessButton() {
        const btn = document.getElementById('btn-processar');
        if (!btn) return;
        if (!window.__procConfig) {
            btn.title = 'Configuração de processamento ausente — recarregue a página (Ctrl+F5).';
            return;
        }
        const required = Object.values(window.__procConfig.camposArquivos);
        const faltando = required.filter(f => !dropzoneFiles[f]);
        const allReady = faltando.length === 0;
        btn.disabled = !allReady;
        btn.title = allReady
            ? ''
            : 'Falta selecionar: ' + faltando.join(', ') + ' (use as áreas tracejadas acima)';
        console.debug('[processar]', { required, dropzoneFiles: Object.keys(dropzoneFiles), faltando, allReady });
    }

    function updateSteps() {
        const steps = document.querySelectorAll('.step');
        if (!steps.length) return;
        const filesReady = Object.keys(dropzoneFiles).length > 0;
        const allReady = !document.getElementById('btn-processar') ||
                         !document.getElementById('btn-processar').disabled;
        steps.forEach(s => s.classList.remove('is-active', 'is-done'));
        if (steps[0]) steps[0].classList.add(filesReady ? 'is-done' : 'is-active');
        if (filesReady && steps[1]) steps[1].classList.add(allReady ? 'is-done' : 'is-active');
        if (allReady && steps[2]) steps[2].classList.add('is-active');
    }

    // ==========================================================
    // PROCESSAMENTO (SSE)
    // ==========================================================
    function initProcessamento(opts) {
        window.__procConfig = opts;
        const btn = document.getElementById('btn-processar');
        if (!btn) return;
        btn.addEventListener('click', () => iniciarProcessamento(opts));
        updateProcessButton();
    }
    window.initProcessamento = initProcessamento;

    function iniciarProcessamento(opts) {
        const fd = new FormData();
        for (const [campo, field] of Object.entries(opts.camposArquivos)) {
            const f = dropzoneFiles[field];
            if (!f) { toast('Arquivo faltando: ' + campo, 'err'); return; }
            fd.append(campo, f);
        }

        const card = document.getElementById('processing');
        const consoleEl = document.getElementById('console');
        const statusEl = document.getElementById('processing-status');
        const badge = document.getElementById('processing-badge');
        const progressBar = document.getElementById('progress-bar');
        const resultHost = document.getElementById('result-host');

        card.classList.remove('hide');
        consoleEl.innerHTML = '';
        progressBar.style.width = '0%';
        resultHost.innerHTML = '';
        statusEl.textContent = 'Enviando arquivos...';
        badge.className = 'badge badge--info';
        badge.textContent = 'enviando';

        const btn = document.getElementById('btn-processar');
        btn.disabled = true;

        fetch(opts.endpoint, { method: 'POST', headers: { 'X-CSRFToken': csrf() }, body: fd })
            .then(r => r.json())
            .then(data => {
                if (!data.job_id) throw new Error('Sem job_id');
                streamLogs(data.job_id);
            })
            .catch(err => {
                statusEl.textContent = 'Falha ao enviar';
                badge.className = 'badge badge--off';
                badge.textContent = 'erro';
                appendLog({ tipo: 'error', mensagem: String(err), timestamp: agora() });
                btn.disabled = false;
            });
    }

    function streamLogs(jobId) {
        const consoleEl = document.getElementById('console');
        const statusEl = document.getElementById('processing-status');
        const badge = document.getElementById('processing-badge');
        const progressBar = document.getElementById('progress-bar');
        const resultHost = document.getElementById('result-host');
        const btn = document.getElementById('btn-processar');

        const es = new EventSource('/api/jobs/' + jobId + '/stream');

        es.onmessage = (e) => {
            let payload;
            try { payload = JSON.parse(e.data); } catch { return; }

            if (payload.tipo === 'progresso') {
                const pct = Math.round((payload.valor || 0) * 100);
                progressBar.style.width = pct + '%';
                return;
            }
            if (payload.tipo === 'status') {
                statusEl.textContent = payload.mensagem;
            }
            if (payload.tipo === 'done') {
                badge.className = 'badge badge--ok';
                badge.textContent = 'concluído';
                statusEl.textContent = payload.mensagem;
                progressBar.style.width = '100%';
                renderResultado(resultHost, payload, jobId, false);
                btn.disabled = false;
                es.close();
            }
            if (payload.tipo === 'error') {
                badge.className = 'badge badge--off';
                badge.textContent = 'falhou';
                statusEl.textContent = 'Erro durante processamento';
                renderResultado(resultHost, payload, jobId, true);
                btn.disabled = false;
                es.close();
            }
            if (payload.tipo === 'end') {
                es.close();
                return;
            }
            appendLog(payload);
        };

        es.onerror = () => {
            // Conexão pode cair no fim do stream — não tratamos como erro fatal aqui
        };
    }

    function appendLog(payload) {
        const consoleEl = document.getElementById('console');
        if (!consoleEl) return;
        const line = document.createElement('div');
        line.className = 'console__line console__line--' + (payload.tipo || 'log');
        const time = document.createElement('span');
        time.className = 'console__time';
        time.textContent = payload.timestamp || agora();
        const msg = document.createElement('span');
        msg.className = 'console__msg';
        msg.textContent = payload.mensagem || '';
        line.appendChild(time);
        line.appendChild(msg);
        consoleEl.appendChild(line);
        consoleEl.scrollTop = consoleEl.scrollHeight;
    }

    function renderResultado(host, payload, jobId, isError) {
        const div = document.createElement('div');
        div.className = 'result' + (isError ? ' result--error' : '');
        if (isError) {
            div.innerHTML = `
                <div class="result__icon">⚠️</div>
                <div>
                    <div class="result__title">Não foi possível concluir</div>
                    <div class="result__sub">${escape(payload.mensagem || 'Erro desconhecido')}</div>
                </div>
            `;
        } else {
            div.innerHTML = `
                <div class="result__icon">✓</div>
                <div style="flex:1; min-width:0;">
                    <div class="result__title">${escape(payload.mensagem || 'Processamento concluído')}</div>
                    <div class="result__sub">Arquivo gerado: <strong>${escape(payload.arquivo || '')}</strong></div>
                    <div class="result__metrics">
                        ${payload.total != null ? `<div><strong>${payload.total}</strong> registros</div>` : ''}
                        ${payload.erros != null ? `<div><strong>${payload.erros}</strong> erros</div>` : ''}
                        ${payload.avisos != null ? `<div><strong>${payload.avisos}</strong> avisos</div>` : ''}
                        ${payload.tempo != null ? `<div><strong>${payload.tempo}s</strong></div>` : ''}
                    </div>
                </div>
                <a class="btn btn--primary" href="/api/jobs/${jobId}/download" download>
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
                    Baixar
                </a>
            `;
        }
        host.appendChild(div);
    }

    function agora() {
        const d = new Date();
        return String(d.getHours()).padStart(2, '0') + ':' +
               String(d.getMinutes()).padStart(2, '0') + ':' +
               String(d.getSeconds()).padStart(2, '0');
    }

    function escape(s) {
        return String(s).replace(/[&<>"']/g, c => ({
            '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
        }[c]));
    }

    // ==========================================================
    // SIDEBAR: bases
    // ==========================================================
    function setupSidebar() {
        function uploadBase(inputId, endpoint, rotuloFalha) {
            const input = document.getElementById(inputId);
            if (!input) return;
            input.addEventListener('change', async () => {
                if (!input.files[0]) return;
                const fd = new FormData();
                fd.append('arquivo', input.files[0]);
                try {
                    const r = await fetch(endpoint, {
                        method: 'POST',
                        headers: { 'X-CSRFToken': csrf() },
                        body: fd,
                    });
                    const data = await r.json();
                    toast(data.mensagem, data.sucesso ? 'ok' : 'err');
                    if (data.sucesso) setTimeout(() => location.reload(), 700);
                } catch (e) {
                    toast(rotuloFalha + ': ' + e, 'err');
                } finally {
                    input.value = '';
                }
            });
        }

        uploadBase('input-upload-preco', '/api/bases/precificacao/upload', 'Falha no upload da Precificação');
        uploadBase('input-upload-desc', '/api/bases/descricao/upload', 'Falha no upload da Descrição');

        const btnSync = document.getElementById('btn-sync-sharepoint');
        if (btnSync) {
            btnSync.addEventListener('click', async () => {
                if (btnSync.classList.contains('is-spinning')) return;
                btnSync.classList.add('is-spinning');
                btnSync.disabled = true;
                try {
                    const r = await fetch('/api/config/sharepoint/sincronizar', {
                        method: 'POST',
                        headers: { 'X-CSRFToken': csrf() },
                    });
                    const data = await r.json();
                    toast(data.mensagem || (data.sucesso ? 'Precificação atualizada' : 'Falha ao sincronizar'),
                          data.sucesso ? 'ok' : 'err');
                    if (data.sucesso) setTimeout(() => location.reload(), 800);
                } catch (e) {
                    toast('Falha ao sincronizar: ' + e, 'err');
                } finally {
                    btnSync.classList.remove('is-spinning');
                    btnSync.disabled = false;
                }
            });
        }
    }

    // ==========================================================
    // LIMPEZA: termos
    // ==========================================================
    function initLimpezaTermos() {
        const formRem = document.getElementById('form-remover');
        const formSub = document.getElementById('form-substituir');

        if (formRem) {
            formRem.addEventListener('submit', async (e) => {
                e.preventDefault();
                const inp = document.getElementById('input-remover');
                const termo = inp.value.trim();
                if (!termo) return;
                const r = await fetch('/api/termos/remover', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf() },
                    body: JSON.stringify({ termo })
                });
                const data = await r.json();
                if (data.sucesso) {
                    inp.value = '';
                    toast('Termo adicionado', 'ok');
                    await refreshTermos();
                } else {
                    toast(data.mensagem || 'Falha', 'err');
                }
            });
        }

        if (formSub) {
            formSub.addEventListener('submit', async (e) => {
                e.preventDefault();
                const a = document.getElementById('input-antigo');
                const n = document.getElementById('input-novo');
                const antigo = a.value.trim();
                const novo = n.value.trim();
                if (!antigo) return;
                const r = await fetch('/api/termos/substituir', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf() },
                    body: JSON.stringify({ antigo, novo })
                });
                const data = await r.json();
                if (data.sucesso) {
                    a.value = ''; n.value = '';
                    toast('Substituição adicionada', 'ok');
                    await refreshTermos();
                } else {
                    toast(data.mensagem || 'Falha', 'err');
                }
            });
        }

        document.addEventListener('click', async (e) => {
            const btn = e.target.closest('[data-action="del-remover"]');
            if (btn) {
                const termo = btn.dataset.termo;
                await deletarTermoRemover(termo);
            }
            const btn2 = e.target.closest('[data-action="del-substituir"]');
            if (btn2) {
                const antigo = btn2.dataset.antigo;
                await deletarTermoSubstituir(antigo);
            }
        });

        // Filtro local sobre as listas colapsáveis
        document.querySelectorAll('input[data-filter-target]').forEach(inp => {
            inp.addEventListener('input', () => {
                const tabela = document.getElementById(inp.dataset.filterTarget);
                if (!tabela) return;
                const q = inp.value.trim().toLowerCase();
                tabela.querySelectorAll('tbody tr').forEach(tr => {
                    if (tr.querySelector('.tbl__empty')) return;
                    const txt = tr.textContent.toLowerCase();
                    tr.style.display = (!q || txt.includes(q)) ? '' : 'none';
                });
            });
        });
    }
    window.initLimpezaTermos = initLimpezaTermos;

    async function refreshTermos() {
        const r = await fetch('/api/termos');
        const data = await r.json();
        renderTermosRemover(data.remover);
        renderTermosSubstituir(data.substituir);
    }

    function renderTermosRemover(lista) {
        const tbody = document.querySelector('#tbl-remover tbody');
        const counter = document.getElementById('count-remover');
        const counterInline = document.getElementById('count-remover-inline');
        if (!tbody) return;
        if (counter) counter.textContent = lista.length;
        if (counterInline) counterInline.textContent = lista.length;
        if (!lista.length) {
            tbody.innerHTML = '<tr><td colspan="2" class="tbl__empty">Nenhum termo cadastrado.</td></tr>';
            return;
        }
        tbody.innerHTML = lista.map(t => `
            <tr data-termo="${escape(t)}">
                <td>${escape(t)}</td>
                <td>
                    <button class="tbl-icon-btn" data-action="del-remover" data-termo="${escape(t)}" title="Remover">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-2 14a2 2 0 0 1-2 2H9a2 2 0 0 1-2-2L5 6"/></svg>
                    </button>
                </td>
            </tr>
        `).join('');
    }

    function renderTermosSubstituir(lista) {
        const tbody = document.querySelector('#tbl-substituir tbody');
        const counter = document.getElementById('count-substituir');
        const counterInline = document.getElementById('count-substituir-inline');
        if (!tbody) return;
        if (counter) counter.textContent = lista.length;
        if (counterInline) counterInline.textContent = lista.length;
        if (!lista.length) {
            tbody.innerHTML = '<tr><td colspan="3" class="tbl__empty">Nenhum par cadastrado.</td></tr>';
            return;
        }
        tbody.innerHTML = lista.map(p => `
            <tr data-antigo="${escape(p.antigo)}">
                <td>${escape(p.antigo)}</td>
                <td>${escape(p.novo)}</td>
                <td>
                    <button class="tbl-icon-btn" data-action="del-substituir" data-antigo="${escape(p.antigo)}" title="Remover">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-2 14a2 2 0 0 1-2 2H9a2 2 0 0 1-2-2L5 6"/></svg>
                    </button>
                </td>
            </tr>
        `).join('');
    }

    async function deletarTermoRemover(termo) {
        const r = await fetch('/api/termos');
        const data = await r.json();
        const novaLista = data.remover.filter(t => t !== termo);
        const r2 = await fetch('/api/termos/remover', {
            method: 'DELETE',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf() },
            body: JSON.stringify({ termos: novaLista })
        });
        const data2 = await r2.json();
        if (data2.sucesso) {
            toast('Termo removido', 'ok');
            await refreshTermos();
        }
    }

    async function deletarTermoSubstituir(antigo) {
        const r = await fetch('/api/termos');
        const data = await r.json();
        const novaLista = data.substituir.filter(p => p.antigo !== antigo);
        const r2 = await fetch('/api/termos/substituir', {
            method: 'DELETE',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf() },
            body: JSON.stringify({ pares: novaLista })
        });
        const data2 = await r2.json();
        if (data2.sucesso) {
            toast('Substituição removida', 'ok');
            await refreshTermos();
        }
    }

    // ==========================================================
    // BOOT
    // ==========================================================
    document.addEventListener('DOMContentLoaded', () => {
        setupDropzones();
        setupSidebar();
        updateSteps();
    });
})();
