# Deploy no Railway

Guia passo-a-passo para subir o **Topshop Amazon System (Web)** no Railway com Postgres, Redis e Volume persistente.

Repositório: <https://github.com/automacoesTopshop2/CriarPlanilhasAmazon>

---

## 1. Arquitetura no Railway

Um projeto com **3 serviços**:

| Serviço      | Tipo                  | Volume                                        |
| ------------ | --------------------- | --------------------------------------------- |
| `web`        | App (este repositório)| `app-data` -> `/data` (planilhas, configs)    |
| `postgres`   | Plugin Postgres       | `postgres-data` -> `/var/lib/postgresql/data` (gerenciado pelo plugin) |
| `redis`      | Plugin Redis          | `redis-data` -> `/data` (gerenciado pelo plugin)                       |

Os volumes do Postgres e do Redis são criados **automaticamente** pelos plugins. O volume da aplicação web é criado manualmente (passo 4).

---

## 2. Criar projeto e adicionar plugins

1. Acesse <https://railway.com> e clique em **New Project**.
2. Escolha **Deploy from GitHub repo** -> selecione `automacoesTopshop2/CriarPlanilhasAmazon`.
3. No projeto criado, clique em **+ New** -> **Database** -> **Add PostgreSQL**.
4. Clique novamente em **+ New** -> **Database** -> **Add Redis**.

Ao final, o projeto deve ter três serviços: `web`, `Postgres` e `Redis`.

---

## 3. Configurar variáveis de ambiente do serviço `web`

No painel do serviço **web**, aba **Variables**, cole:

```env
ENV=production
SECRET_KEY=<gere com: python -c "import secrets; print(secrets.token_hex(32))">
SESSION_COOKIE_SECURE=1

DATABASE_URL=${{Postgres.DATABASE_URL}}
REDIS_URL=${{Redis.REDIS_URL}}

DATA_DIR=/data
APP_CONFIG_PATH=/data/app_config.json
ARQUIVO_PRECIFICACAO=/data/Precificacao.xlsx
ARQUIVO_DESCRICAO=/data/DESCRICAO.xlsx
ARQUIVO_REMOVER=/data/termos_remover.txt
ARQUIVO_SUBSTITUIR=/data/termos_substituir.txt

URL_BASE_IMAGENS=https://topshop-tiny.com.br/wp-content/uploads/tiny

# Opcional — só se for usar a sincronização do SharePoint
SHAREPOINT_TENANT_ID=
SHAREPOINT_CLIENT_ID=
SHAREPOINT_CLIENT_SECRET=
```

> As referências `${{Postgres.DATABASE_URL}}` e `${{Redis.REDIS_URL}}` são **substituídas em runtime** pelo Railway com os valores reais dos plugins. Não copie a URL "crua" — use a referência.

---

## 4. Criar o Volume persistente do `web`

No painel do serviço **web**:

1. Aba **Settings** -> seção **Volumes** -> **+ New Volume**.
2. Nome: `app-data`.
3. Mount path: `/data`.
4. Salvar. O volume sobrevive a redeploys e contém:
   - `Precificacao.xlsx` / `DESCRICAO.xlsx` (enviadas via UI ou SharePoint sync)
   - `termos_remover.txt` / `termos_substituir.txt` (editáveis via UI)
   - `app_config.json` (mapeamentos customizados)

> O Postgres e o Redis **já vêm com volume nativo do plugin** — não precisa criar manualmente.

---

## 5. Expor domínio público

No serviço **web** -> aba **Settings** -> **Networking** -> **Generate Domain**.

O Railway gera uma URL `*.up.railway.app`. O healthcheck `/healthz` valida que o serviço subiu.

---

## 6. Bootstrap do usuário admin

Na primeira vez, é preciso criar o usuário master. Pelo painel do Railway:

1. Serviço `web` -> aba **Settings** -> **Custom Start Command** (temporário) ou abra um **Shell** via Railway CLI.
2. Rode dentro do container:
   ```bash
   python -m auth.bootstrap_master
   ```
3. Siga o prompt para definir e-mail/senha. Depois reverta o start command (se alterou).

Alternativa via Railway CLI local:
```bash
railway run python -m auth.bootstrap_master --service web
```

---

## 7. Subir os arquivos da Precificação

Duas opções:

- **Upload via UI**: faça login -> Configurações -> envie `Precificacao.xlsx` e `DESCRIÇÃO.xlsx`. Os arquivos são gravados no Volume (`/data`).
- **Sync SharePoint**: configure as três variáveis `SHAREPOINT_*` e o link no painel admin. O serviço baixa automaticamente no startup.

---

## 8. Comandos úteis

```bash
# Logs em tempo real
railway logs --service web

# Rodar Alembic manualmente (já roda automático no start.sh)
railway run alembic upgrade head --service web

# Conectar ao Postgres
railway connect Postgres

# Conectar ao Redis
railway connect Redis
```

---

## 9. Arquivos da configuração

- `Dockerfile`         -> imagem da aplicação (Python 3.11-slim + libpq + locales pt_BR)
- `start.sh`           -> entrypoint: cria `DATA_DIR`, roda `alembic upgrade head`, exec `gunicorn`
- `railway.json`       -> instrui o Railway a usar o Dockerfile e `/healthz`
- `.dockerignore`      -> exclui `.venv`, `.git`, planilhas locais, `instance/`, etc.

---

## 10. Troubleshooting

| Sintoma                                    | Causa provável                                                                 |
| ------------------------------------------ | ------------------------------------------------------------------------------ |
| `psycopg.OperationalError`                 | `DATABASE_URL` não setado ou plugin Postgres ainda subindo. Aguarde 30s e re-deploy. |
| Login falha com `5 per 15 minutes` cedo    | Workers de `gunicorn` rodando sem `REDIS_URL`. Confira a variável.             |
| `Precificacao.xlsx` some entre redeploys   | Volume `/data` não foi criado. Refaça o passo 4.                               |
| `403 CSRF token missing` no upload         | `SESSION_COOKIE_SECURE=1` exige HTTPS — Railway entrega HTTPS por padrão; verifique se está acessando via `https://`. |
