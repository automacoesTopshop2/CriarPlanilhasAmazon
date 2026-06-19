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

    // Bases (Precificação/Descrição) carregadas? A página injeta window.__basesStatus.
    // Se a página não informou (ex.: limpeza), não bloqueia (retorna true).
    function basesCarregadas() {
        const b = window.__basesStatus;
        if (!b) return true;
        return !!(b.precificacao && b.descricao);
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

    // ==========================================================
    // ORIGEM DO TEMPLATE (usar pronto x enviar/atualizar)
    // ==========================================================
    // field (id da dropzone) -> { modo:'pronto'|'upload', temSalvo, salvar() }
    const templateSources = {};

    function setupTemplateSources() {
        document.querySelectorAll('[data-role="template-source"]').forEach(setupTemplateSource);
    }

    function setupTemplateSource(el) {
        const field = el.dataset.field;
        const temSalvo = el.dataset.temSalvo === '1';
        const uploadArea = el.querySelector('[data-role="ts-upload"]');
        const saveCheckbox = el.querySelector('[data-role="ts-save"]');
        const radios = el.querySelectorAll('[data-role="ts-mode"]');

        const state = {
            modo: temSalvo ? 'pronto' : 'upload',
            temSalvo,
            salvar: () => !!(saveCheckbox && saveCheckbox.checked),
        };
        templateSources[field] = state;

        function aplicar() {
            if (uploadArea) uploadArea.hidden = state.modo !== 'upload';
            updateProcessButton();
            if (typeof window.__manualRecompute === 'function') window.__manualRecompute();
            updateSteps();
        }

        radios.forEach(r => r.addEventListener('change', () => {
            if (r.checked) { state.modo = r.value; aplicar(); }
        }));
        aplicar();
    }

    // Campo de template exige upload? (true também quando não há componente
    // de template-source — preserva o comportamento antigo das outras páginas.)
    function templateRequerArquivo(field) {
        const ts = templateSources[field];
        if (!ts) return true;
        return ts.modo === 'upload';
    }

    // Anexa os flags de template pronto ao FormData de processamento.
    function aplicarFlagsTemplate(fd, field) {
        const ts = templateSources[field];
        if (!ts) return;
        if (ts.modo === 'pronto') {
            fd.append('usar_template_salvo', '1');
        } else if (dropzoneFiles[field] && ts.salvar()) {
            fd.append('salvar_template', '1');
        }
    }

    function updateProcessButton() {
        const btn = document.getElementById('btn-processar');
        if (!btn) return;
        if (!window.__procConfig) {
            btn.title = 'Configuração de processamento ausente — recarregue a página (Ctrl+F5).';
            return;
        }
        const required = Object.values(window.__procConfig.camposArquivos);
        const faltando = required.filter(f => templateRequerArquivo(f) && !dropzoneFiles[f]);
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
        if (!basesCarregadas()) {
            const ok = window.confirm(
                'Atenção: as bases de Precificação/Descrição não estão carregadas.\n\n' +
                'A planilha será gerada com preços/descrições vazios.\n\n' +
                'Deseja prosseguir mesmo assim?');
            if (!ok) return;
        }
        const fd = new FormData();
        for (const [campo, field] of Object.entries(opts.camposArquivos)) {
            const f = dropzoneFiles[field];
            if (!f) {
                if (!templateRequerArquivo(field)) continue; // usa template pronto
                toast('Arquivo faltando: ' + campo, 'err'); return;
            }
            fd.append(campo, f);
        }
        aplicarFlagsTemplate(fd, 'template');

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

    // Classificação de sensibilidade do produto no catálogo BDAmazon.
    // Mapeia status_produto (LIVRE/SENSIVEL/PROIBIDO/INATIVO/null) -> badge.
    const STATUS_PRODUTO_META = {
        LIVRE:    { rotulo: 'Livre',    classe: 'badge--ok'   },
        SENSIVEL: { rotulo: 'Sensível', classe: 'badge--warn' },
        PROIBIDO: { rotulo: 'Proibido', classe: 'badge--off'  },
        INATIVO:  { rotulo: 'Inativo',  classe: 'badge'       },
    };

    function statusProdutoBadge(status) {
        if (!status) {
            // SKU raiz não consta no catálogo interno (produto novo/não cadastrado).
            return `<small class="status-produto status-produto--none" title="SKU raiz não consta no catálogo interno">não catalogado</small>`;
        }
        const meta = STATUS_PRODUTO_META[status]
            || { rotulo: status, classe: 'badge' };
        return `<span class="badge ${meta.classe} status-produto" title="Classificação no catálogo interno">${escape(meta.rotulo)}</span>`;
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
    // ENTRADA MANUAL (caixas de texto + API BDAmazon)
    // Compartilhado entre /sku (modo SKU) e /asin (modo ASIN com coluna extra)
    // ==========================================================
    function initEntradaManual(opts) {
        // opts: {
        //   endpointContas, endpointCriarSku, endpointProcessar,
        //   templateField,
        //   comAsin: bool (default false),
        //   comMarcaEan: bool (default true) — desligar para /asin, onde o
        //                processador só usa ASIN+SKU,
        //   tabSelector: '.modo-tabs__tab', cardPlanilhaId, cardManualId,
        //   tbodyId, btnProcessarId,
        // }
        if (opts.comMarcaEan === undefined) opts.comMarcaEan = true;
        const tabs = document.querySelectorAll(opts.tabSelector || '.modo-tabs__tab');
        const cardPlanilha = document.getElementById(opts.cardPlanilhaId || 'card-planilha');
        const cardManual = document.getElementById(opts.cardManualId || 'card-manual');
        if (!cardPlanilha || !cardManual) return;

        tabs.forEach(tab => tab.addEventListener('click', () => {
            tabs.forEach(t => {
                const ativa = t === tab;
                t.classList.toggle('is-active', ativa);
                t.setAttribute('aria-selected', ativa ? 'true' : 'false');
            });
            const modo = tab.getAttribute('data-modo');
            cardPlanilha.classList.toggle('hide', modo !== 'planilha');
            cardManual.classList.toggle('hide', modo !== 'manual');
            // Elementos que só fazem sentido no modo Planilha (steps, info-card).
            document.querySelectorAll('[data-so-planilha]').forEach(el =>
                el.classList.toggle('hide', modo !== 'planilha'));
        }));

        const tbody = document.getElementById(opts.tbodyId || 'tbl-manual-body');
        const selectDefault = document.getElementById('manual-conta-default');
        const marcaDefault = document.getElementById('manual-marca-default'); // pode não existir (modo ASIN)
        const btnProcessar = document.getElementById(opts.btnProcessarId || 'btn-processar-manual');
        let contas = [];
        const marcaDefaultValor = () => (marcaDefault && marcaDefault.value) || '';

        // ---- Carregamento / refresh de contas ----
        const btnRefreshContas = document.getElementById('btn-refresh-contas');

        function opcoesContasHTML(valorSel) {
            return `<option value="">— selecione —</option>` + contas.map(c =>
                `<option value="${escape(c.codigo)}"${c.codigo === valorSel ? ' selected' : ''}>${escape(c.nome)} (${escape(c.codigo)})</option>`
            ).join('');
        }

        function renderSelectContas(valorSelecionado) {
            if (!contas.length) return `<select data-field="conta_codigo" disabled><option value="">—</option></select>`;
            return `<select data-field="conta_codigo">${opcoesContasHTML(valorSelecionado)}</select>`;
        }

        // Re-popula o select padrão e os selects das linhas ainda não resolvidas,
        // preservando a seleção atual — assim contas novas aparecem sem perder dados.
        function repopularSelectsContas() {
            selectDefault.innerHTML = opcoesContasHTML(selectDefault.value);
            tbody.querySelectorAll('tr').forEach(tr => {
                if (tr.dataset.skuMarket) return; // resolvida: não mexe (select fica fixo)
                const sel = tr.querySelector('[data-field="conta_codigo"]');
                if (sel) { sel.innerHTML = opcoesContasHTML(sel.value); sel.disabled = false; }
            });
        }

        async function carregarContas({ refresh = false } = {}) {
            if (refresh && btnRefreshContas) {
                btnRefreshContas.disabled = true;
                btnRefreshContas.classList.add('is-loading');
            }
            try {
                const data = await fetch(opts.endpointContas).then(r => r.json());
                if (!data.sucesso) {
                    const det = data.detalhe ? ` (${data.detalhe})` : '';
                    const msg = data.mensagem || 'falha ao listar contas';
                    if (!contas.length) selectDefault.innerHTML = `<option value="">Erro: ${escape(msg)}</option>`;
                    toast(msg + det, 'err');
                    console.error('[BDAmazon /contas]', data);
                    return;
                }
                contas = data.contas || [];
                if (!contas.length) {
                    selectDefault.innerHTML = `<option value="">Nenhuma conta com codigo_externo cadastrada</option>`;
                    if (refresh) toast('Nenhuma conta cadastrada no BDAmazon.', 'err');
                    return;
                }
                repopularSelectsContas();
                if (refresh) toast(`${contas.length} conta(s) atualizadas.`, 'ok');
            } catch (e) {
                if (!contas.length) selectDefault.innerHTML = `<option value="">Erro de rede</option>`;
                toast('Falha ao carregar contas: ' + e, 'err');
            } finally {
                if (refresh && btnRefreshContas) {
                    btnRefreshContas.disabled = false;
                    btnRefreshContas.classList.remove('is-loading');
                }
            }
        }

        if (btnRefreshContas) {
            btnRefreshContas.addEventListener('click', () => carregarContas({ refresh: true }));
        }
        carregarContas();

        // ---- Validações de conferência (avisos antes de criar/gerar) ----
        // Kits usam prefixo "K-"; após removê-lo, qualquer letra restante é suspeita.
        const KIT_PREFIX_RE = /^\s*k-/i;
        function skuTemLetraSuspeita(sku) {
            return /[a-zA-Z]/.test((sku || '').replace(KIT_PREFIX_RE, ''));
        }
        function valorCampo(tr, campo) {
            const el = tr.querySelector(`[data-field="${campo}"]`);
            return (el && el.value || '').trim();
        }
        // Mostra um confirm listando os problemas; true = pode prosseguir.
        function confirmarAvisos(titulo, avisos) {
            if (!avisos.length) return true;
            const msg = titulo + '\n\n- ' + avisos.join('\n- ') +
                '\n\nRecomenda-se verificar se os dados foram preenchidos corretamente.' +
                '\n\nDeseja prosseguir mesmo assim?';
            return window.confirm(msg);
        }

        function novaLinha(skuRaiz, asin) {
            const tr = document.createElement('tr');
            const contaSel = selectDefault.value;
            const colAsin = opts.comAsin
                ? `<td><input data-field="asin" type="text" value="${escape(asin || '')}" placeholder="Ex.: B0XXXXXXXX"></td>`
                : '';
            const colsMarcaEan = opts.comMarcaEan
                ? `<td><input data-field="marca" type="text" value="${escape(marcaDefaultValor())}"></td>
                   <td><input data-field="ean" type="text" placeholder="Por linha"></td>`
                : '';
            tr.innerHTML = `
                <td class="manual-num"></td>
                ${colAsin}
                <td><input data-field="sku_raiz" type="text" value="${escape(skuRaiz || '')}" placeholder="Ex.: ABC123"></td>
                <td>${renderSelectContas(contaSel)}</td>
                ${colsMarcaEan}
                <td class="cell-sku-market">
                    <button type="button" class="btn btn--xs btn--dark" data-role="solicitar-sku-market" disabled>Solicitar</button>
                </td>
                <td><button type="button" class="tbl-manual__del" data-role="del-linha" title="Remover">✕</button></td>
            `;
            tbody.appendChild(tr);
            atualizarNumeracao();
            atualizarBotaoSolicitar(tr);
            atualizarBotaoProcessar();
            return tr;
        }

        function atualizarNumeracao() {
            tbody.querySelectorAll('tr').forEach((tr, i) => {
                const td = tr.querySelector('.manual-num');
                if (td) td.textContent = String(i + 1);
            });
        }

        function atualizarBotaoSolicitar(tr) {
            const btn = tr.querySelector('[data-role="solicitar-sku-market"]');
            if (!btn) return; // já resolvida
            const sku = (tr.querySelector('[data-field="sku_raiz"]').value || '').trim();
            const conta = (tr.querySelector('[data-field="conta_codigo"]').value || '').trim();
            const asinOk = !opts.comAsin || (tr.querySelector('[data-field="asin"]').value || '').trim();
            btn.disabled = !(sku && conta && asinOk);
            btn.title = btn.disabled
                ? (opts.comAsin
                    ? 'Preencha ASIN, SKU Raiz e Conta primeiro'
                    : 'Preencha SKU Raiz e Conta primeiro')
                : '';
        }

        function atualizarBotaoProcessar() {
            const linhas = Array.from(tbody.querySelectorAll('tr'));
            const temTemplate = !!dropzoneFiles[opts.templateField] ||
                !templateRequerArquivo(opts.templateField);
            const todasResolvidas = linhas.length > 0 &&
                linhas.every(tr => tr.dataset.skuMarket);
            btnProcessar.disabled = !(temTemplate && todasResolvidas);
            if (!temTemplate) btnProcessar.title = 'Envie o template .xlsm ou use o template pronto';
            else if (!todasResolvidas) btnProcessar.title = 'Solicite o SKU-Market de todas as linhas primeiro';
            else btnProcessar.title = '';
        }
        // Permite que a troca de modo do template (usar pronto x enviar)
        // recalcule o botão deste fluxo manual.
        window.__manualRecompute = atualizarBotaoProcessar;

        // ---- solicitar SKU-Market de UMA linha ----
        // Marca a linha como resolvida (preenche o sku_market, trava os campos).
        // Compartilhado pela solicitação individual e pela em lote.
        function marcarLinhaResolvida(tr, data) {
            tr.dataset.skuMarket = data.sku_market;
            tr.dataset.versao = String(data.versao || 1);
            tr.dataset.statusProduto = data.status_produto || '';
            const cell = tr.querySelector('.cell-sku-market');
            cell.innerHTML = `
                <code style="font-size:12px">${escape(data.sku_market)}</code>
                <small style="color:var(--text-muted);display:block">v${escape(String(data.versao))}</small>
                <span class="status-produto-wrap" style="display:block;margin-top:4px">${statusProdutoBadge(data.status_produto)}</span>
            `;
            const elSku = tr.querySelector('[data-field="sku_raiz"]');
            if (elSku) elSku.readOnly = true;
            const elConta = tr.querySelector('[data-field="conta_codigo"]');
            if (elConta) elConta.disabled = true;
            if (opts.comAsin) {
                const elAsin = tr.querySelector('[data-field="asin"]');
                if (elAsin) elAsin.readOnly = true;
            }
        }

        // Linha que falhou no lote: mostra o erro e restaura o botão "Solicitar"
        // para o usuário poder reenviar aquela linha individualmente.
        function marcarLinhaErro(tr, erro) {
            const cell = tr.querySelector('.cell-sku-market');
            const msg = (erro && erro.mensagem) || 'falha ao criar';
            cell.innerHTML = `
                <button type="button" class="btn btn--xs btn--dark" data-role="solicitar-sku-market">Solicitar</button>
                <small style="color:var(--danger);display:block;margin-top:4px">${escape(msg)}</small>
            `;
            atualizarBotaoSolicitar(tr);
        }

        // Retorna {ok:bool, msg?:string} para que o "solicitar todos" possa
        // decidir se aborta o lote ou continua.
        async function solicitarLinha(tr, {silentToast = false} = {}) {
            if (tr.dataset.skuMarket) return { ok: true, ja: true };
            const btn = tr.querySelector('[data-role="solicitar-sku-market"]');
            const sku = (tr.querySelector('[data-field="sku_raiz"]').value || '').trim();
            const conta = (tr.querySelector('[data-field="conta_codigo"]').value || '').trim();
            const asin = opts.comAsin
                ? (tr.querySelector('[data-field="asin"]').value || '').trim()
                : '';
            if (!sku || !conta || (opts.comAsin && !asin)) {
                return { ok: false, msg: 'campos obrigatórios faltando' };
            }
            if (btn) { btn.disabled = true; btn.textContent = '...'; }
            try {
                const r = await fetch(opts.endpointCriarSku, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf() },
                    body: JSON.stringify({ sku_raiz: sku, conta_codigo: conta, asin }),
                });
                const data = await r.json();
                if (!r.ok || !data.sucesso) {
                    const det = data.detalhe ? ` (${data.detalhe})` : '';
                    const msg = (data.mensagem || 'Falha BDAmazon') + det;
                    if (!silentToast) toast(msg, 'err');
                    if (btn) { btn.disabled = false; btn.textContent = 'Solicitar'; }
                    // 429 → sinaliza para parar o lote
                    return { ok: false, msg, status: r.status };
                }
                marcarLinhaResolvida(tr, data);
                if (!silentToast) {
                    toast(`SKU-Market criado: ${data.sku_market}`, 'ok');
                    // Alerta de risco do catálogo: laranja p/ SENSÍVEL, vermelho p/ PROIBIDO.
                    if (data.status_produto === 'PROIBIDO') {
                        toast(`⛔ ${data.sku_raiz}: produto PROIBIDO no catálogo — não deveria ser anunciado.`, 'err');
                    } else if (data.status_produto === 'SENSIVEL') {
                        toast(`⚠️ ${data.sku_raiz}: produto SENSÍVEL — revise antes de criar o anúncio.`, 'err');
                    }
                }
                atualizarBotaoProcessar();
                return { ok: true };
            } catch (err) {
                if (!silentToast) toast('Erro de rede: ' + err, 'err');
                if (btn) { btn.disabled = false; btn.textContent = 'Solicitar'; }
                return { ok: false, msg: String(err) };
            }
        }

        // Clique individual
        tbody.addEventListener('click', (e) => {
            const btn = e.target.closest('[data-role="solicitar-sku-market"]');
            if (!btn) return;
            solicitarLinha(btn.closest('tr'));
        });

        // ---- botão "Solicitar SKU-Market de todos" ----
        const btnTodos = document.getElementById('btn-solicitar-todos');
        if (btnTodos) {
            btnTodos.addEventListener('click', async () => {
                const linhas = Array.from(tbody.querySelectorAll('tr'))
                    .filter(tr => !tr.dataset.skuMarket);
                if (!linhas.length) {
                    toast('Nada para solicitar — todas as linhas já têm SKU-Market.', 'ok');
                    return;
                }

                // Confere os dados antes de disparar a criação em massa.
                const avisos = [];
                const semSku = linhas.filter(tr => !valorCampo(tr, 'sku_raiz')).length;
                const semConta = linhas.filter(tr => !valorCampo(tr, 'conta_codigo')).length;
                const comLetra = linhas.map(tr => valorCampo(tr, 'sku_raiz'))
                    .filter(s => s && skuTemLetraSuspeita(s));
                if (semSku) avisos.push(`${semSku} linha(s) sem SKU raiz`);
                if (opts.comAsin) {
                    const semAsin = linhas.filter(tr => !valorCampo(tr, 'asin')).length;
                    if (semAsin) avisos.push(`${semAsin} linha(s) sem ASIN`);
                }
                if (semConta) avisos.push(`${semConta} linha(s) sem conta selecionada`);
                if (comLetra.length) {
                    const amostra = comLetra.slice(0, 6).join(', ') + (comLetra.length > 6 ? '…' : '');
                    avisos.push(`${comLetra.length} SKU(s) com letras fora do padrão de kit "K-": ${amostra}`);
                }
                if (!confirmarAvisos('Atenção antes de criar os SKU-Market:', avisos)) return;

                btnTodos.disabled = true;
                const labelOriginal = btnTodos.textContent;
                // Endpoint de lote do BDAmazon aceita até 1000 itens/chamada;
                // fatiamos em blocos para ficar com folga e dar progresso visível.
                const CHUNK = 500;
                let ok = 0, falha = 0, proibidos = 0, sensiveis = 0, abortou = false;
                try {
                    for (let start = 0; start < linhas.length && !abortou; start += CHUNK) {
                        const slice = linhas.slice(start, start + CHUNK);
                        btnTodos.textContent = linhas.length > CHUNK
                            ? `Criando em lote ${start + 1}–${start + slice.length}/${linhas.length}...`
                            : `Criando ${slice.length} em lote...`;
                        const itens = slice.map(tr => ({
                            sku_raiz: valorCampo(tr, 'sku_raiz'),
                            conta_codigo: valorCampo(tr, 'conta_codigo'),
                            asin: opts.comAsin ? valorCampo(tr, 'asin') : '',
                        }));
                        let data;
                        try {
                            const r = await fetch(opts.endpointCriarLote, {
                                method: 'POST',
                                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf() },
                                body: JSON.stringify({ itens }),
                            });
                            data = await r.json();
                            if (!data || data.sucesso === false) {
                                const det = data && data.detalhe ? ` (${data.detalhe})` : '';
                                toast((data && data.mensagem || 'Falha no lote') + det, 'err');
                                abortou = true;
                                break;
                            }
                        } catch (err) {
                            toast('Erro de rede no lote: ' + err, 'err');
                            abortou = true;
                            break;
                        }
                        // Casa cada resultado com sua linha pelo índice (relativo ao bloco).
                        (data.resultados || []).forEach(res => {
                            const tr = slice[res.indice];
                            if (!tr) return;
                            if (res.ok) {
                                marcarLinhaResolvida(tr, res);
                                ok++;
                                if (res.status_produto === 'PROIBIDO') proibidos++;
                                else if (res.status_produto === 'SENSIVEL') sensiveis++;
                            } else {
                                marcarLinhaErro(tr, res.erro);
                                falha++;
                            }
                        });
                    }
                } finally {
                    btnTodos.textContent = labelOriginal;
                    btnTodos.disabled = false;
                    atualizarBotaoProcessar();
                }
                if (!abortou) {
                    if (falha === 0) toast(`${ok} SKU-Market(s) criados com sucesso.`, 'ok');
                    else toast(`Concluído: ${ok} criado(s), ${falha} falha(s). Reenvie as linhas em vermelho.`, falha > ok ? 'err' : 'ok');
                }
                // Alertas de risco do catálogo, agregados (evita 500 toasts).
                if (proibidos) toast(`⛔ ${proibidos} SKU(s) PROIBIDO(s) no catálogo — não deveriam ser anunciados.`, 'err');
                if (sensiveis) toast(`⚠️ ${sensiveis} SKU(s) SENSÍVEL(eis) — revise antes de criar os anúncios.`, 'err');
            });
        }

        // ---- inputs disparam atualização do botão "Solicitar" ----
        tbody.addEventListener('input', (e) => {
            const tr = e.target.closest('tr');
            if (tr) atualizarBotaoSolicitar(tr);
        });
        tbody.addEventListener('change', (e) => {
            const tr = e.target.closest('tr');
            if (tr) atualizarBotaoSolicitar(tr);
        });

        function lerTextarea(id) {
            const el = document.getElementById(id);
            if (!el) return [];
            return el.value.split(/\r?\n/)
                .map(l => l.trim())
                .filter(l => !l.startsWith('#'));
        }

        function limparTextarea(id) {
            const el = document.getElementById(id);
            if (el) el.value = '';
        }

        function removerLinhasVazias() {
            // Linhas onde SKU Raiz está vazio E que não têm sku_market resolvido
            tbody.querySelectorAll('tr').forEach(tr => {
                if (tr.dataset.skuMarket) return;
                const sku = (tr.querySelector('[data-field="sku_raiz"]').value || '').trim();
                if (!sku) tr.remove();
            });
        }

        document.getElementById('btn-add-linha').addEventListener('click', () => novaLinha(''));
        document.getElementById('btn-limpar-tabela').addEventListener('click', () => {
            if (!tbody.children.length) return;
            if (!confirm('Limpar todas as linhas?')) return;
            tbody.innerHTML = '';
            atualizarBotaoProcessar();
        });
        document.getElementById('btn-importar-lote').addEventListener('click', () => {
            // Pareia linha a linha entre os textareas. SKU Raiz é sempre presente;
            // EAN só existe quando comMarcaEan; ASIN só quando comAsin.
            const skus = lerTextarea('manual-lote');
            const eans = opts.comMarcaEan ? lerTextarea('manual-lote-ean') : [];
            const asins = opts.comAsin ? lerTextarea('manual-lote-asin') : [];
            const total = Math.max(skus.length, asins.length);
            if (!total) {
                toast('Nada para importar — preencha pelo menos a coluna de SKU Raiz.', 'err');
                return;
            }
            removerLinhasVazias();
            let importadas = 0;
            for (let i = 0; i < total; i++) {
                const sku = (skus[i] || '').trim();
                const asin = (asins[i] || '').trim();
                if (!sku && !asin) continue;
                const tr = novaLinha(sku, asin);
                if (opts.comMarcaEan && eans[i]) {
                    const inp = tr.querySelector('[data-field="ean"]');
                    if (inp) inp.value = eans[i].trim();
                }
                importadas++;
            }
            limparTextarea('manual-lote');
            if (opts.comMarcaEan) limparTextarea('manual-lote-ean');
            if (opts.comAsin) limparTextarea('manual-lote-asin');
            toast(`${importadas} linha(s) importada(s).`, 'ok');
        });

        tbody.addEventListener('click', (e) => {
            const btn = e.target.closest('[data-role="del-linha"]');
            if (!btn) return;
            btn.closest('tr').remove();
            atualizarNumeracao();
            atualizarBotaoProcessar();
        });

        document.querySelectorAll(`[data-field="${opts.templateField}"] input[data-role="dropzone-input"]`)
            .forEach(inp => inp.addEventListener('change', atualizarBotaoProcessar));
        document.querySelectorAll(`[data-field="${opts.templateField}"] [data-role="dropzone-clear"]`)
            .forEach(b => b.addEventListener('click', () => setTimeout(atualizarBotaoProcessar, 0)));

        btnProcessar.addEventListener('click', () => {
            const linhas = Array.from(tbody.querySelectorAll('tr'));
            if (!linhas.length) {
                toast('Adicione ao menos uma linha antes de gerar.', 'err');
                return;
            }

            // Avisos de conferência antes de gerar (não bloqueiam — pedem confirmação).
            const avisos = [];
            if (!basesCarregadas()) {
                avisos.push('as bases de Precificação/Descrição não estão carregadas (preços/descrições ficarão vazios)');
            }
            const comLetra = linhas.map(tr => valorCampo(tr, 'sku_raiz'))
                .filter(s => s && skuTemLetraSuspeita(s));
            if (comLetra.length) {
                avisos.push(`${comLetra.length} SKU(s) com letras fora do padrão de kit "K-"`);
            }
            if (!confirmarAvisos('Atenção antes de gerar a planilha:', avisos)) return;

            const entradas = [];
            for (const tr of linhas) {
                if (!tr.dataset.skuMarket) {
                    toast('Solicite o SKU-Market de todas as linhas antes.', 'err');
                    return;
                }
                const e = {
                    sku_raiz: (tr.querySelector('[data-field="sku_raiz"]').value || '').trim(),
                    conta_codigo: (tr.querySelector('[data-field="conta_codigo"]').value || '').trim(),
                    sku_market: tr.dataset.skuMarket,
                    versao: parseInt(tr.dataset.versao || '1', 10),
                };
                if (opts.comMarcaEan) {
                    const elMarca = tr.querySelector('[data-field="marca"]');
                    const elEan = tr.querySelector('[data-field="ean"]');
                    e.marca = (elMarca && elMarca.value || '').trim();
                    e.ean = (elEan && elEan.value || '').trim();
                }
                if (opts.comAsin) e.asin = (tr.querySelector('[data-field="asin"]').value || '').trim();
                entradas.push(e);
            }
            const template = dropzoneFiles[opts.templateField];
            if (!template && templateRequerArquivo(opts.templateField)) {
                toast('Envie o template .xlsm primeiro (ou use o template pronto).', 'err');
                return;
            }

            const fd = new FormData();
            fd.append('entradas', JSON.stringify(entradas));
            if (template) fd.append('arquivo_template', template);
            aplicarFlagsTemplate(fd, opts.templateField);

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
            statusEl.textContent = `Gerando planilha para ${entradas.length} item(ns)...`;
            badge.className = 'badge badge--info';
            badge.textContent = 'processando';
            btnProcessar.disabled = true;

            fetch(opts.endpointProcessar, {
                method: 'POST',
                headers: { 'X-CSRFToken': csrf() },
                body: fd,
            })
                .then(r => r.json())
                .then(data => {
                    if (data && data.sucesso === false) throw new Error(data.mensagem || 'Falha na rota');
                    if (!data.job_id) throw new Error('Resposta sem job_id');
                    streamLogs(data.job_id);
                })
                .catch(err => {
                    statusEl.textContent = 'Falha ao enviar';
                    badge.className = 'badge badge--off';
                    badge.textContent = 'erro';
                    appendLog({ tipo: 'error', mensagem: String(err.message || err), timestamp: agora() });
                    btnProcessar.disabled = false;
                });
        });

        // Inicia com uma linha vazia
        novaLinha('');
    }
    window.initEntradaManual = initEntradaManual;

    // Alias de compatibilidade (modo SKU)
    function initSkuManual(opts) {
        return initEntradaManual({
            endpointContas: opts.endpointContas,
            endpointCriarSku: opts.endpointCriarSku,
            endpointCriarLote: opts.endpointCriarLote,
            endpointProcessar: opts.endpointProcessar,
            templateField: opts.templateField,
            comAsin: false,
        });
    }
    window.initSkuManual = initSkuManual;

    // ==========================================================
    // BOOT
    // ==========================================================
    document.addEventListener('DOMContentLoaded', () => {
        setupDropzones();
        setupTemplateSources();
        setupSidebar();
        updateSteps();
    });
})();
