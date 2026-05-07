"""Testes do fluxo de download de jobs.

Foco no fallback de disco: quando o JOBS em memória não tem o job
(p.ex. requisição caiu num worker diferente do que processou, ou após
restart do container), o /download deve ler do volume persistente.
"""

from __future__ import annotations

import json
import os

import pytest

import web_app


@pytest.fixture
def jobs_dir(tmp_path, monkeypatch):
    """Aponta o storage de jobs para um diretório temporário do teste."""
    d = tmp_path / "jobs"
    d.mkdir()
    monkeypatch.setenv("JOBS_STORAGE_DIR", str(d))
    return d


def _gravar_job_em_disco(jobs_dir, job_id: str, conteudo: bytes,
                         nome_arquivo: str, owner_id):
    (jobs_dir / f"{job_id}.xlsm").write_bytes(conteudo)
    (jobs_dir / f"{job_id}.json").write_text(
        json.dumps({
            "nome_arquivo": nome_arquivo,
            "owner_id": owner_id,
            "tipo": "sku",
            "criado_em": "2026-05-07T00:00:00",
        }),
        encoding="utf-8",
    )


class TestDownloadFallbackDisco:
    def test_baixa_do_disco_quando_jobs_em_memoria_vazio(
        self, client, login_usuario, usuario, jobs_dir
    ):
        """Simula download caindo num worker que não tem o job na memória."""
        # Garante que JOBS está vazio (worker "novo" sem o job)
        web_app.JOBS.clear()
        job_id = "abc123fallback"
        conteudo = b"PK\x03\x04fake-xlsm-bytes-for-test"
        _gravar_job_em_disco(
            jobs_dir, job_id, conteudo,
            nome_arquivo="planilha_teste.xlsm",
            owner_id=usuario,
        )

        r = client.get(f"/api/jobs/{job_id}/download")
        assert r.status_code == 200
        assert r.data == conteudo
        assert "planilha_teste.xlsm" in r.headers.get("Content-Disposition", "")

    def test_404_quando_nao_existe_em_memoria_nem_disco(
        self, client, login_usuario, jobs_dir
    ):
        web_app.JOBS.clear()
        r = client.get("/api/jobs/inexistente999/download")
        assert r.status_code == 404

    def test_403_quando_outro_dono_tenta_baixar_do_disco(
        self, client, login_usuario, jobs_dir
    ):
        """Owner gravado no sidecar é um terceiro — usuário logado não pode baixar."""
        web_app.JOBS.clear()
        job_id = "outroOwnerJob"
        _gravar_job_em_disco(
            jobs_dir, job_id, b"conteudo",
            nome_arquivo="alheio.xlsm",
            owner_id="outro-uuid-qualquer",
        )

        r = client.get(f"/api/jobs/{job_id}/download")
        assert r.status_code == 403

    def test_admin_baixa_arquivo_de_outro_usuario(
        self, client, login_admin, jobs_dir
    ):
        """Admin pode baixar mesmo sem ser o dono."""
        web_app.JOBS.clear()
        job_id = "jobDeOutro"
        _gravar_job_em_disco(
            jobs_dir, job_id, b"bytes-admin",
            nome_arquivo="qualquer.xlsm",
            owner_id="usuario-comum-uuid",
        )

        r = client.get(f"/api/jobs/{job_id}/download")
        assert r.status_code == 200
        assert r.data == b"bytes-admin"


class TestPersistenciaEmDisco:
    def test_jobs_storage_dir_default_usa_data_dir(self, monkeypatch, tmp_path):
        monkeypatch.delenv("JOBS_STORAGE_DIR", raising=False)
        monkeypatch.setenv("DATA_DIR", str(tmp_path))
        d = web_app._jobs_storage_dir()
        assert d == os.path.join(str(tmp_path), "jobs")
        assert os.path.isdir(d)

    def test_jobs_storage_dir_respeita_override(self, monkeypatch, tmp_path):
        custom = tmp_path / "custom_jobs"
        monkeypatch.setenv("JOBS_STORAGE_DIR", str(custom))
        d = web_app._jobs_storage_dir()
        assert d == str(custom)
        assert os.path.isdir(d)

    def test_persistir_resultado_grava_arquivo_e_sidecar(
        self, monkeypatch, tmp_path
    ):
        import io
        from core.processadores.base import ResultadoProcessamento

        monkeypatch.setenv("JOBS_STORAGE_DIR", str(tmp_path))
        resultado = ResultadoProcessamento(
            sucesso=True,
            arquivo_saida=io.BytesIO(b"dummy-bytes"),
            nome_arquivo="saida.xlsm",
        )
        web_app._persistir_resultado_em_disco(
            "job-xyz", resultado, owner_id="user-1", tipo="sku"
        )
        assert (tmp_path / "job-xyz.xlsm").read_bytes() == b"dummy-bytes"
        meta = json.loads((tmp_path / "job-xyz.json").read_text(encoding="utf-8"))
        assert meta["nome_arquivo"] == "saida.xlsm"
        assert meta["owner_id"] == "user-1"
        assert meta["tipo"] == "sku"
        # Stream rebobinado para reuso pelo /download in-memory
        assert resultado.arquivo_saida.tell() == 0

    def test_persistir_resultado_ignora_falha(self, monkeypatch, tmp_path):
        """Não deve levantar exceção se não conseguir gravar."""
        import io
        from core.processadores.base import ResultadoProcessamento

        monkeypatch.setenv("JOBS_STORAGE_DIR", str(tmp_path))

        # Simula falha de IO no momento da escrita
        def _falha(*a, **kw):
            raise OSError("disco cheio")

        monkeypatch.setattr("builtins.open", _falha)
        resultado = ResultadoProcessamento(
            sucesso=True,
            arquivo_saida=io.BytesIO(b"x"),
            nome_arquivo="x.xlsm",
        )
        # Não deve raise
        web_app._persistir_resultado_em_disco("j", resultado, "u", "sku")
