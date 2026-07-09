// Topshop Amazon System — admin: configurações
(function () {
    'use strict';

    function csrf() {
        const m = document.querySelector('meta[name="csrf-token"]');
        return m ? m.getAttribute('content') : '';
    }

    function toast(msg, ok) {
        const host = document.getElementById('toast-host');
        if (!host) { alert(msg); return; }
        const el = document.createElement('div');
        el.className = 'toast ' + (ok ? 'toast--ok' : 'toast--err');
        el.textContent = msg;
        host.appendChild(el);
        setTimeout(() => el.remove(), 3500);
    }

    async function api(url, opts) {
        opts = opts || {};
        opts.headers = Object.assign({
            'X-CSRFToken': csrf(),
            'Content-Type': 'application/json',
        }, opts.headers || {});
        if (opts.body && typeof opts.body !== 'string') {
            opts.body = JSON.stringify(opts.body);
        }
        const r = await fetch(url, opts);
        let data = {};
        try { data = await r.json(); } catch (_) {}
        return { ok: r.ok, status: r.status, data: data };
    }

    // === tabs ===
    const tabs = document.querySelectorAll('#config-tabs .tab');
    tabs.forEach(t => t.addEventListener('click', () => {
        tabs.forEach(x => x.classList.remove('is-active'));
        t.classList.add('is-active');
        const alvo = t.getAttribute('data-tab');
        document.querySelectorAll('.tab-panel').forEach(p => {
            p.classList.toggle('is-active', p.getAttribute('data-panel') === alvo);
        });
    }));

    // === arquivos ===
    const formArquivos = document.getElementById('form-arquivos');
    if (formArquivos) {
        formArquivos.addEventListener('submit', async (ev) => {
            ev.preventDefault();
            const fd = new FormData(formArquivos);
            const obj = {};
            fd.forEach((v, k) => obj[k] = v);
            const r = await api('/api/config/arquivos', { method: 'PUT', body: obj });
            if (r.ok) toast('Arquivos salvos.', true);
            else toast(r.data.mensagem || 'Falha.', false);
        });
    }

    // === valores fixos: modal ===
    const modal = document.getElementById('modal-valor');
    const formValor = document.getElementById('form-valor');
    const inputNome = document.getElementById('valor-nome');
    const inputValor = document.getElementById('valor-valor');
    const inputNomeOriginal = document.getElementById('valor-nome-original');
    const titulo = document.getElementById('modal-valor-titulo');

    function abrirModalValor(nome, valor) {
        modal.hidden = false;
        if (nome) {
            titulo.textContent = 'Editar valor fixo';
            inputNome.value = nome;
            inputValor.value = valor || '';
            inputNomeOriginal.value = nome;
        } else {
            titulo.textContent = 'Novo valor fixo';
            inputNome.value = '';
            inputValor.value = '';
            inputNomeOriginal.value = '';
        }
    }

    function fecharModal() { modal.hidden = true; }
    modal.querySelectorAll('[data-close]').forEach(el => el.addEventListener('click', fecharModal));

    // === modal: editar prefixo ===
    const modalPrefixo = document.getElementById('modal-prefixo');
    const formEditarPrefixo = document.getElementById('form-editar-prefixo');
    const inputPrefixoEditNome = document.getElementById('prefixo-edit-nome');
    const inputPrefixoEditConta = document.getElementById('prefixo-edit-conta');
    const inputPrefixoEditOriginal = document.getElementById('prefixo-edit-original');
    const inputPrefixoEditMapa = document.getElementById('prefixo-edit-mapa');
    const lblPrefixoModalidade = document.getElementById('prefixo-edit-modalidade-lbl');

    // Endpoint por modalidade: 'normal' -> /prefixos ; 'full' -> /prefixos-full
    function endpointPrefixo(mapa) {
        return mapa === 'full' ? '/api/config/prefixos-full' : '/api/config/prefixos';
    }

    function abrirModalPrefixo(prefixo, conta, mapa) {
        mapa = mapa === 'full' ? 'full' : 'normal';
        modalPrefixo.hidden = false;
        inputPrefixoEditNome.value = prefixo || '';
        inputPrefixoEditConta.value = conta || '';
        inputPrefixoEditOriginal.value = prefixo || '';
        if (inputPrefixoEditMapa) inputPrefixoEditMapa.value = mapa;
        if (lblPrefixoModalidade) lblPrefixoModalidade.textContent =
            mapa === 'full' ? '— Modalidade FULL (CLA)' : '— Modelo Normal';
    }

    function fecharModalPrefixo() { modalPrefixo.hidden = true; }
    modalPrefixo.querySelectorAll('[data-close]').forEach(el => el.addEventListener('click', fecharModalPrefixo));

    formEditarPrefixo.addEventListener('submit', async (ev) => {
        ev.preventDefault();
        const prefixoOriginal = inputPrefixoEditOriginal.value;
        const prefixoNovo = inputPrefixoEditNome.value.trim().toUpperCase();
        const conta = inputPrefixoEditConta.value.trim();
        const mapa = inputPrefixoEditMapa ? inputPrefixoEditMapa.value : 'normal';
        if (!prefixoNovo || !conta) { toast('Prefixo e coluna são obrigatórios.', false); return; }
        const r = await api(endpointPrefixo(mapa) + '/' + encodeURIComponent(prefixoOriginal), {
            method: 'PUT',
            body: { prefixo_novo: prefixoNovo, conta },
        });
        if (r.ok) { toast('Salvo.', true); location.reload(); }
        else toast(r.data.mensagem || 'Falha.', false);
    });

    document.getElementById('btn-novo-valor-fixo')?.addEventListener('click', () => abrirModalValor());

    formValor.addEventListener('submit', async (ev) => {
        ev.preventDefault();
        const nomeAntigo = inputNomeOriginal.value;
        const corpo = { coluna: inputNome.value.trim(), valor: inputValor.value, nome_novo: inputNome.value.trim() };
        let r;
        if (nomeAntigo) {
            r = await api('/api/config/valores-fixos/' + encodeURIComponent(nomeAntigo), { method: 'PUT', body: corpo });
        } else {
            r = await api('/api/config/valores-fixos', { method: 'POST', body: corpo });
        }
        if (r.ok) { toast('Salvo.', true); location.reload(); }
        else toast(r.data.mensagem || 'Falha.', false);
    });

    // mapa lógico → endpoint base
    const ENDPOINTS_MAPA = {
        descricao:    '/api/config/mapa-colunas',
        precificacao: '/api/config/mapa-precificacao',
    };
    function endpointMapa(nome) {
        return ENDPOINTS_MAPA[nome] || ENDPOINTS_MAPA.descricao;
    }

    // === ações em valores fixos / mapas / prefixos ===
    document.addEventListener('click', async (ev) => {
        const btn = ev.target.closest('[data-action]');
        if (!btn) return;
        const action = btn.getAttribute('data-action');

        if (action === 'editar-valor') {
            const tr = btn.closest('tr');
            const nome = tr.getAttribute('data-nome');
            const valor = tr.children[1].textContent.trim();
            abrirModalValor(nome, valor);
        }
        else if (action === 'remover-valor') {
            const tr = btn.closest('tr');
            const nome = tr.getAttribute('data-nome');
            if (!confirm(`Remover "${nome}"?`)) return;
            const r = await api('/api/config/valores-fixos/' + encodeURIComponent(nome), { method: 'DELETE' });
            if (r.ok) { toast('Removido.', true); location.reload(); }
            else toast(r.data.mensagem || 'Falha.', false);
        }
        else if (action === 'remover-sinonimo') {
            const chip = btn.closest('.chip');
            const block = btn.closest('.map-block');
            const chave = block.getAttribute('data-chave');
            const mapa = block.getAttribute('data-mapa') || 'descricao';
            const sinonimo = chip.getAttribute('data-sinonimo');
            if (!confirm(`Remover sinônimo "${sinonimo}" de "${chave}"?`)) return;
            const base = endpointMapa(mapa);
            const r = await api(`${base}/${encodeURIComponent(chave)}/${encodeURIComponent(sinonimo)}`, { method: 'DELETE' });
            if (r.ok) { toast('Removido.', true); location.reload(); }
            else toast(r.data.mensagem || 'Falha.', false);
        }
        else if (action === 'remover-chave-coluna') {
            const block = btn.closest('.map-block');
            const chave = block.getAttribute('data-chave');
            const mapa = block.getAttribute('data-mapa') || 'descricao';
            if (!confirm(`Remover o campo "${chave}" e todos os seus sinônimos?`)) return;
            const r = await api(endpointMapa(mapa) + '/' + encodeURIComponent(chave), { method: 'DELETE' });
            if (r.ok) { toast('Removido.', true); location.reload(); }
            else toast(r.data.mensagem || 'Falha.', false);
        }
        else if (action === 'editar-prefixo' || action === 'editar-prefixo-full') {
            const tr = btn.closest('tr');
            const pref = tr.getAttribute('data-prefixo');
            const conta = tr.getAttribute('data-conta');
            const mapa = tr.getAttribute('data-mapa') || 'normal';
            abrirModalPrefixo(pref, conta, mapa);
        }
        else if (action === 'remover-prefixo' || action === 'remover-prefixo-full') {
            const tr = btn.closest('tr');
            const pref = tr.getAttribute('data-prefixo');
            const mapa = tr.getAttribute('data-mapa') || 'normal';
            const rotulo = mapa === 'full' ? ' (FULL)' : '';
            if (!confirm(`Remover prefixo "${pref}"${rotulo}?`)) return;
            const r = await api(endpointPrefixo(mapa) + '/' + encodeURIComponent(pref), { method: 'DELETE' });
            if (r.ok) { toast('Removido.', true); location.reload(); }
            else toast(r.data.mensagem || 'Falha.', false);
        }
        else if (action === 'remover-onedrive') {
            btn.closest('.form-row').remove();
        }
    });

    // === adicionar sinônimo via chip-form ===
    document.querySelectorAll('.chip-form').forEach(f => {
        f.addEventListener('submit', async (ev) => {
            ev.preventDefault();
            const chave = f.getAttribute('data-chave');
            const mapa = f.getAttribute('data-mapa') || 'descricao';
            const inp = f.querySelector('input');
            const sinonimo = inp.value.trim();
            if (!sinonimo) return;
            const r = await api(endpointMapa(mapa) + '/' + encodeURIComponent(chave), {
                method: 'POST',
                body: { sinonimo },
            });
            if (r.ok) { toast('Adicionado.', true); location.reload(); }
            else toast(r.data.mensagem || 'Falha.', false);
        });
    });

    // === nova chave (campo lógico) — DESCRIÇÃO ===
    document.getElementById('form-nova-chave-coluna')?.addEventListener('submit', async (ev) => {
        ev.preventDefault();
        const chave = document.getElementById('nova-chave-coluna').value.trim();
        const sinonimo = document.getElementById('primeiro-sinonimo').value.trim();
        if (!chave || !sinonimo) { toast('Preencha campo e sinônimo.', false); return; }
        const r = await api('/api/config/mapa-colunas/' + encodeURIComponent(chave), {
            method: 'POST',
            body: { sinonimo },
        });
        if (r.ok) { toast('Campo adicionado.', true); location.reload(); }
        else toast(r.data.mensagem || 'Falha.', false);
    });

    // === nova chave (campo lógico) — PRECIFICAÇÃO ===
    document.getElementById('form-nova-chave-precificacao')?.addEventListener('submit', async (ev) => {
        ev.preventDefault();
        const chave = document.getElementById('nova-chave-precificacao').value.trim();
        const sinonimo = document.getElementById('primeiro-sinonimo-precificacao').value.trim();
        if (!chave || !sinonimo) { toast('Preencha campo e sinônimo.', false); return; }
        const r = await api('/api/config/mapa-precificacao/' + encodeURIComponent(chave), {
            method: 'POST',
            body: { sinonimo },
        });
        if (r.ok) { toast('Campo adicionado.', true); location.reload(); }
        else toast(r.data.mensagem || 'Falha.', false);
    });

    // === novo prefixo ===
    document.getElementById('form-novo-prefixo')?.addEventListener('submit', async (ev) => {
        ev.preventDefault();
        const prefixo = document.getElementById('input-prefixo').value.trim().toUpperCase();
        const conta = document.getElementById('input-conta').value.trim();
        if (!prefixo || !conta) { toast('Prefixo e conta são obrigatórios.', false); return; }
        const r = await api('/api/config/prefixos', { method: 'POST', body: { prefixo, conta } });
        if (r.ok) { toast('Prefixo adicionado (Normal).', true); location.reload(); }
        else toast(r.data.mensagem || 'Falha.', false);
    });

    document.getElementById('form-novo-prefixo-full')?.addEventListener('submit', async (ev) => {
        ev.preventDefault();
        const prefixo = document.getElementById('input-prefixo-full').value.trim().toUpperCase();
        const conta = document.getElementById('input-conta-full').value.trim();
        if (!prefixo || !conta) { toast('Prefixo e coluna são obrigatórios.', false); return; }
        const r = await api('/api/config/prefixos-full', { method: 'POST', body: { prefixo, conta } });
        if (r.ok) { toast('Prefixo adicionado (FULL).', true); location.reload(); }
        else toast(r.data.mensagem || 'Falha.', false);
    });

    // === onedrive: salvar lista ===
    document.getElementById('btn-add-onedrive')?.addEventListener('click', () => {
        const host = document.getElementById('onedrive-list');
        const div = document.createElement('div');
        div.className = 'form-row';
        div.innerHTML = '<input class="field__input" placeholder="caminho do OneDrive..."> <button class="btn btn--xs btn--danger" data-action="remover-onedrive">×</button>';
        host.appendChild(div);
    });

    document.getElementById('btn-salvar-onedrive')?.addEventListener('click', async () => {
        const inputs = document.querySelectorAll('#onedrive-list input');
        const caminhos = Array.from(inputs).map(i => i.value).filter(s => s.trim());
        const r = await api('/api/config/onedrive', { method: 'PUT', body: { caminhos } });
        if (r.ok) toast('OneDrive salvo.', true);
        else toast(r.data.mensagem || 'Falha.', false);
    });

    // === SharePoint ===
    function spResultado(msg, ok) {
        const box = document.getElementById('sharepoint-resultado');
        if (!box) return;
        box.classList.remove('hide', 'alert--success', 'alert--danger');
        box.classList.add(ok ? 'alert--success' : 'alert--danger');
        box.textContent = msg;
    }

    // Lê os 3 links do form + a flag e salva no config. Retorna o resultado da API.
    async function salvarLinksSharepoint() {
        const form = document.getElementById('form-sharepoint');
        const fd = new FormData(form);
        const body = {
            link_precificacao: fd.get('link_precificacao') || '',
            link_precificacao_full: fd.get('link_precificacao_full') || '',
            link_drop_estoque: fd.get('link_drop_estoque') || '',
            sync_no_startup: fd.get('sync_no_startup') === 'on',
        };
        return api('/api/config/sharepoint', { method: 'PUT', body });
    }

    document.getElementById('form-sharepoint')?.addEventListener('submit', async (ev) => {
        ev.preventDefault();
        const r = await salvarLinksSharepoint();
        if (r.ok) toast('Links do SharePoint salvos.', true);
        else toast(r.data.mensagem || 'Falha ao salvar.', false);
    });

    // Testar / Sincronizar por planilha (data-chave). Salva os links antes,
    // garantindo que a ação use exatamente o que está no form.
    document.querySelectorAll('.js-sp-testar').forEach((btn) => {
        btn.addEventListener('click', async () => {
            const chave = btn.getAttribute('data-chave');
            spResultado('Testando...', true);
            await salvarLinksSharepoint();
            const r = await api('/api/config/sharepoint/testar', { method: 'POST', body: { chave } });
            if (r.ok && r.data.ok) {
                const sizeKb = r.data.size ? Math.round(r.data.size / 1024) : '?';
                spResultado(`✓ Acesso OK — "${r.data.name}" (${sizeKb} KB)`, true);
            } else {
                spResultado('✗ ' + (r.data.mensagem || 'Falha desconhecida.'), false);
            }
        });
    });

    document.querySelectorAll('.js-sp-sincronizar').forEach((btn) => {
        btn.addEventListener('click', async () => {
            const chave = btn.getAttribute('data-chave');
            spResultado('Sincronizando...', true);
            await salvarLinksSharepoint();
            const r = await api('/api/config/sharepoint/sincronizar', { method: 'POST', body: { chave } });
            if (r.ok && r.data.sucesso) {
                spResultado('✓ ' + r.data.mensagem, true);
                toast('Planilha sincronizada do SharePoint.', true);
            } else {
                spResultado('✗ ' + (r.data.mensagem || 'Falha desconhecida.'), false);
                toast('Falha ao sincronizar.', false);
            }
        });
    });
})();
