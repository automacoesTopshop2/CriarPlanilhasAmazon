// Topshop Amazon System — admin: usuários e convites
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
        const r = await fetch(url, opts);
        let data = {};
        try { data = await r.json(); } catch (_) {}
        return { ok: r.ok, status: r.status, data: data };
    }

    // === ações por linha ===
    document.addEventListener('click', async (ev) => {
        const btn = ev.target.closest('button[data-action]');
        if (!btn) return;
        const action = btn.getAttribute('data-action');
        const id = btn.getAttribute('data-id');

        if (action === 'promover') {
            if (!confirm('Promover este usuário a admin?')) return;
            const r = await api(`/admin/usuarios/${id}/promover`, { method: 'POST' });
            if (r.ok) { toast('Usuário promovido.', true); location.reload(); }
            else toast(r.data.mensagem || 'Falha.', false);
        }
        else if (action === 'rebaixar') {
            if (!confirm('Rebaixar este admin a usuário comum?')) return;
            const r = await api(`/admin/usuarios/${id}/rebaixar`, { method: 'POST' });
            if (r.ok) { toast('Rebaixado.', true); location.reload(); }
            else toast(r.data.mensagem || 'Falha.', false);
        }
        else if (action === 'desativar') {
            if (!confirm('Desativar este usuário? Ele não conseguirá mais acessar.')) return;
            const r = await api(`/admin/usuarios/${id}/desativar`, { method: 'POST' });
            if (r.ok) { toast('Desativado.', true); location.reload(); }
            else toast(r.data.mensagem || 'Falha.', false);
        }
        else if (action === 'ativar') {
            const r = await api(`/admin/usuarios/${id}/ativar`, { method: 'POST' });
            if (r.ok) { toast('Ativado.', true); location.reload(); }
            else toast(r.data.mensagem || 'Falha.', false);
        }
        else if (action === 'reset-senha') {
            if (!confirm('Gerar link de redefinição de senha?')) return;
            const r = await api(`/admin/usuarios/${id}/reset-senha`, { method: 'POST' });
            if (r.ok) {
                navigator.clipboard.writeText(r.data.link).catch(()=>{});
                alert(`Link copiado (válido por ${r.data.expira_horas}h):\n\n${r.data.link}`);
            } else toast(r.data.mensagem || 'Falha.', false);
        }
        else if (action === 'editar-codigo-externo') {
            const atual = btn.getAttribute('data-atual') || '';
            const novo = window.prompt(
                'Código externo deste usuário no BDAmazon (deixe em branco para remover).\n' +
                'Use o mesmo identificador que o admin do BDAmazon cadastrou em "usuarios.codigo_externo".',
                atual
            );
            if (novo === null) return;
            const valor = novo.trim();
            const r = await api(`/admin/usuarios/${id}/codigo-externo`, {
                method: 'POST',
                body: JSON.stringify({ codigo_externo: valor }),
            });
            if (r.ok) {
                toast('Código externo atualizado.', true);
                const span = document.querySelector(`.codigo-externo-val[data-id="${id}"]`);
                if (span) span.textContent = valor || '—';
                btn.setAttribute('data-atual', valor);
            } else toast(r.data.mensagem || 'Falha.', false);
        }
        else if (action === 'revogar-convite') {
            if (!confirm('Revogar este convite?')) return;
            const r = await api(`/admin/convites/${id}/revogar`, { method: 'POST' });
            if (r.ok) { toast('Convite revogado.', true); location.reload(); }
            else toast(r.data.mensagem || 'Falha.', false);
        }
    });

    // === modal de novo convite ===
    const modal = document.getElementById('modal-convite');
    const btnNovo = document.getElementById('btn-novo-convite');
    const formConvite = document.getElementById('form-convite');
    const resultado = document.getElementById('modal-convite-resultado');
    const linkInput = document.getElementById('link-convite');
    const expH = document.getElementById('exp-h');

    function abrirModal() {
        modal.hidden = false;
        formConvite.hidden = false;
        resultado.hidden = true;
    }

    function fecharModal() {
        modal.hidden = true;
        formConvite.reset();
    }

    if (btnNovo) btnNovo.addEventListener('click', abrirModal);
    modal.querySelectorAll('[data-close]').forEach(el => el.addEventListener('click', fecharModal));

    if (formConvite) {
        formConvite.addEventListener('submit', async (ev) => {
            ev.preventDefault();
            const fd = new FormData(formConvite);
            const r = await fetch('/admin/convites', {
                method: 'POST',
                body: fd,
                headers: { 'X-CSRFToken': csrf() },
            });
            let data = {};
            try { data = await r.json(); } catch (_) {}
            if (r.ok) {
                formConvite.hidden = true;
                resultado.hidden = false;
                linkInput.value = data.link;
                expH.textContent = data.expira_horas;
                linkInput.select();
            } else {
                toast(data.mensagem || 'Falha ao criar convite.', false);
            }
        });
    }

    const btnCopiar = document.getElementById('btn-copiar-link');
    if (btnCopiar) {
        btnCopiar.addEventListener('click', () => {
            linkInput.select();
            navigator.clipboard.writeText(linkInput.value)
                .then(() => toast('Link copiado!', true))
                .catch(() => toast('Não consegui acessar o clipboard.', false));
        });
    }
})();
