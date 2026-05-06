# 📦 Guia Completo de Uso — Sistema de Planilhas Amazon

**Versão:** 6.1  
**Última Atualização:** Abril de 2026

---

## 📋 Índice

1. [O que é este sistema?](#o-que-é-este-sistema)
2. [Visão geral da interface](#visão-geral-da-interface)
3. [Bases de dados necessárias](#bases-de-dados-necessárias)
4. [Módulo 1 — Criar por SKU](#módulo-1--criar-por-sku)
5. [Módulo 2 — Criar por ASIN](#módulo-2--criar-por-asin)
6. [Módulo 3 — Limpeza](#módulo-3--limpeza)
7. [Como funcionam os Kits](#como-funcionam-os-kits)
8. [Configuração do OneDrive (.env)](#configuração-do-onedrive-env)
9. [Estrutura de pastas](#estrutura-de-pastas)
10. [Perguntas frequentes (FAQ)](#perguntas-frequentes-faq)
11. [Solução de problemas](#solução-de-problemas)

---

## O que é este sistema?

Este sistema é uma **aplicação web local** (roda no seu navegador) que automatiza a criação de planilhas para cadastro de produtos na Amazon. Ele:

- Lê suas planilhas de entrada (listas de SKUs ou ASINs)
- Busca automaticamente preços, descrições, medidas e pesos
- Preenche os templates oficiais da Amazon (.xlsm)
- Gera links de imagens automaticamente
- Limpa textos com termos indesejados

> **Em resumo:** Você sobe um arquivo com SKUs ou ASINs, e o sistema gera a planilha pronta para upload na Amazon.

---

## Visão geral da interface

A interface é dividida em duas áreas:

### 🔹 Barra Lateral (Sidebar - Esquerda)

| Seção | O que faz |
|-------|-----------|
| **💰 Precificação** | Mostra status da base de preços. Botão "Atualizar Precificação" busca do OneDrive |
| **📝 Descrição** | Mostra status da base de descrições. Permite upload manual do arquivo |
| **🔧 Módulo** | Permite alternar entre SKU, ASIN e Limpeza |
| **ℹ️ Informações** | Detalhes sobre a versão e módulos |

### 🔹 Área Principal (Centro)

Muda conforme o módulo selecionado. Sempre terá:
- Campos de upload de arquivo
- Status dos arquivos carregados
- Botão "PROCESSAR" para iniciar
- Logs em tempo real durante processamento
- Link de download do arquivo gerado

---

## Bases de dados necessárias

O sistema precisa de **duas bases de dados** para funcionar:

### 1. 💰 Precificação (`Precificacao.xlsx`)

| Campo | Descrição |
|-------|-----------|
| **O que contém** | Tabela com todos os SKUs e seus preços por conta (Nogora, Beta, Ativa, etc.) |
| **Como chega** | Sincronização automática via OneDrive (botão "Atualizar Precificação") |
| **Atualização** | Sempre que houver alteração de preços, clique em "Atualizar Precificação" |

**Colunas esperadas na planilha:**
- `SKU` — Código do produto (chave de busca)
- Uma coluna para cada conta (Nogora, Beta, Ativa, etc.) com o preço respectivo

### 2. 📝 Descrição (`DESCRIÇÃO.xlsx`)

| Campo | Descrição |
|-------|-----------|
| **O que contém** | Tabela com títulos, descrições, bullet points, EAN, modelo, medidas e peso |
| **Como chega** | Upload manual pela barra lateral |
| **Atualização** | Sempre que cadastrar novos produtos ou alterar descrições |

**Colunas esperadas na planilha:**

| Coluna | Exemplos de nomes aceitos |
|--------|--------------------------|
| SKU | `SKU`, `K2 - SKU`, `K3 - SKU` |
| Título | `TÍTULO AMAZON`, `Nome do Item`, `Nome do Produto` |
| Modelo | `MODELO REF.`, `REF-ASIN`, `Número da peça` |
| EAN | `EAN`, `GTIN`, `Código de Barras` |
| Peso | `PESO`, `Peso (kg)` |
| Comprimento | `COMP.`, `COMP`, `Comprimento`, `C` |
| Largura | `LARG.`, `LARG`, `Largura`, `L` |
| Altura | `ALT.`, `ALT`, `Altura`, `A` |
| Descrição | `DESCRIÇÃO`, `Descrição`, `Desc` |
| Bullets 1-5 | `1. Marcador`, `Marcador 1`, `Bullet 1` (até 5) |

> **💡 Dica:** O sistema reconhece automaticamente os nomes das colunas. Não precisa ser exatamente igual — ele ignora acentos, maiúsculas/minúsculas e espaços extras.

---

## Módulo 1 — Criar por SKU

### O que faz
Cria a planilha completa para upload na Amazon a partir de uma lista de SKUs. Preenche **todos os campos**: preço, título, descrição, bullets, EAN, modelo, medidas, peso, imagens, valores fixos, etc.

### Passo a passo

1. **Selecione "1. Criar por SKU"** na barra lateral
2. **Escolha a Categoria:**
   - `Criar Padrão` — Categoria AUDIO_OR_VIDEO (mais comum)
   - `Criar Brinquedos` — Categoria TOYS (em desenvolvimento)
   - `Criar Potes de Vidro` — Categoria HOME (em desenvolvimento)
   - `Criar Suplementos` — Categoria HEALTH (em desenvolvimento)
3. **Faça upload da Planilha de SKUs:**
   - Arquivo `.xlsx` com a lista de SKUs na primeira coluna
   - Os SKUs devem estar no formato: `PREFIXO-CODIGO` (ex: `NOGO-12345`)
4. **Faça upload do Template NOGORA:**
   - Arquivo `.xlsm` (template oficial da Amazon com macros)
   - Obtido na pasta `Templates de Criação/`
5. **Clique em "PROCESSAR SKUs"**
6. **Acompanhe os logs** em tempo real
7. **Baixe o arquivo** gerado quando aparecer o botão de download

### O que cada prefixo significa

O prefixo do SKU determina qual **coluna de preço** usar:

| Prefixo | Conta | Exemplo |
|---------|-------|---------|
| `NOGO-` | Nogora | `NOGO-12345` |
| `ATIV-` | Ativa | `ATIV-12345` |
| `BET-` | Beta | `BET-12345` |
| `BOX2-` | Box2Brasil | `BOX2-12345` |
| `EASYT-` | Easytech | `EASYT-12345` |
| `EVERG-` | Evergreen | `EVERG-12345` |
| `FINT-` | Fintech | `FINT-12345` |
| `FRIS-` | Frisco | `FRIS-12345` |
| `INFIN-` | Infinyshop | `INFIN-12345` |
| `JACI-` | Jacitara | `JACI-12345` |
| `MZIA-` | Manzia | `MZIA-12345` |
| `RAQ-` | Raquena | `RAQ-12345` |
| `TECH-` | Tech Place | `TECH-12345` |
| `VIANN-` | Vianeny | `VIANN-12345` |
| `VERD-` | Verdal | `VERD-12345` |
| `TACN-` | Tacnar | `TACN-12345` |
| `ATNC-` | ATN | `ATNC-12345` |

### Valores automáticos preenchidos

O sistema preenche automaticamente estes valores fixos no template:

- **Ação de oferta:** Criar ou substituir (atualização completa)
- **Tipo de ID:** EAN
- **Condição:** Novo
- **Quantidade:** 0
- **Grupo de envio:** FM Transportes Frete Grátis
- **País de origem:** Brasil
- **Garantia:** 90 Dias
- **Unidades de medida:** Centímetros / Quilogramas
- E muitos outros...

---

## Módulo 2 — Criar por ASIN

### O que faz
Processa listas de ASINs existentes, preenchendo campos essenciais como **preço, medidas e peso**. Ideal para vincular produtos a ASINs já cadastrados.

### Passo a passo

1. **Selecione "2. Criar por ASIN"** na barra lateral
2. **Faça upload da planilha CriarASIN:**
   - Coluna A = ASIN
   - Coluna B = SKU
3. **Faça upload do Template ListaASINS (.xlsm)**
4. **Clique em "PROCESSAR ASINs"**
5. **Acompanhe os logs** e baixe o arquivo gerado

### Formato da planilha de entrada

```
| Coluna A (ASIN)    | Coluna B (SKU)     |
|--------------------|---------------------|
| B0XXXXXXXXXX       | NOGO-12345          |
| B0YYYYYYYYYY       | BET-67890           |
| B0ZZZZZZZZZZ       | K2-12345            |
```

---

## Módulo 3 — Limpeza

### O que faz
Remove ou substitui termos indesejados em planilhas **já criadas**. Útil para corrigir textos em massa.

### Passo a passo

1. **Selecione "3. Limpeza"** na barra lateral
2. **Gerencie os termos:**
   - **Remover:** Termos que serão apagados (ex: "Frete Grátis", "Promoção")
   - **Substituir:** Pares de substituição (ex: "c/" → "com")
3. **Faça upload da planilha** para limpar (`.xlsx` ou `.xlsm`)
4. **Clique em "EXECUTAR LIMPEZA"**
5. **Baixe o arquivo** limpo

### Onde ficam os termos salvos

- **Termos a remover:** `termos_remover.txt` (um termo por linha)
- **Termos a substituir:** `termos_substituir.txt` (formato: `antigo=>novo`)

> **💡 Dica:** Os termos são mantidos entre sessões. Não precisa recadastrá-los toda vez.

---

## Como funcionam os Kits

O sistema reconhece automaticamente kits pelo formato do SKU:

### Kit com multiplicação (mesmo produto)

```
K2-2999 → 2 unidades do produto 2999
```
- Peso: multiplicado por 2
- Altura: multiplicada por 2
- Comprimento e largura: mantidos

### Kit com combinação (produtos diferentes)

```
K-2999-6392 → Kit com produto 2999 + produto 6392
```
- Peso: somado (peso 2999 + peso 6392)
- Altura: somada
- Comprimento: usa o maior valor
- Largura: usa o maior valor

### Kit combinado com multiplicação

```
K5-6384-6392 → 5 kits com produto 6384 + produto 6392
```
1. Primeiro soma as medidas (6384 + 6392)
2. Depois multiplica o resultado por 5

---

## Configuração do OneDrive (.env)

### O que é o arquivo `.env`?

O `.env` é um arquivo de configuração simples que fica na pasta raiz do sistema. Nele você define **caminhos de arquivos** e **configurações** sem precisar mexer no código Python.

### Onde está?

```
CriarPlanilhasAmazon/
├── .env           ← ESTE ARQUIVO (pode estar oculto)
├── app.py
├── core/
└── ...
```

> **⚠️ Não vê o arquivo?** No Explorador de Arquivos, vá em `Exibir > Itens ocultos` e marque a opção.

### Como editar

1. **Abra o arquivo `.env`** com o Bloco de Notas, Notepad++ ou VS Code
2. **Encontre a variável** que quer alterar
3. **Mude o valor** depois do `=`
4. **Salve** e reinicie o sistema

### Configuração do caminho do OneDrive

O sistema tenta encontrar o arquivo `Precificacao Amazon.xlsx` no OneDrive. Se o caminho no seu computador for diferente do padrão, edite o `.env`:

**Exemplo — Caminho relativo (recomendado):**
```env
ONEDRIVE_PRECIFICACAO_1=OneDrive - Top Shop\Criação de Anúncios - Documentos\Precificacao Amazon.xlsx
```

**Exemplo — Caminho absoluto (se o relativo não funcionar):**
```env
ONEDRIVE_PRECIFICACAO_1=C:\Users\Maria\OneDrive - Minha Empresa\Documentos\Precificacao Amazon.xlsx
```

> **💡 Dica:** Caminhos relativos começam a partir de `C:\Users\SeuUsuario\`. O sistema adiciona essa parte automaticamente.

### Como descobrir o caminho certo

1. Abra o **Explorador de Arquivos**
2. Navegue até a pasta do OneDrive
3. Encontre o arquivo `Precificacao Amazon.xlsx`
4. Clique com **botão direito** → **Propriedades**
5. Copie o campo **"Local"** e adicione `\Precificacao Amazon.xlsx` no final
6. Cole no `.env` depois do `=`

### Variáveis disponíveis

| Variável | Descrição | Padrão |
|----------|-----------|--------|
| `ARQUIVO_PRECIFICACAO` | Arquivo de preços local | `Precificacao.xlsx` |
| `ARQUIVO_DESCRICAO` | Arquivo de descrições local | `DESCRIÇÃO.xlsx` |
| `ARQUIVO_REMOVER` | Termos para remoção | `termos_remover.txt` |
| `ARQUIVO_SUBSTITUIR` | Pares de substituição | `termos_substituir.txt` |
| `URL_BASE_IMAGENS` | URL base para imagens | `https://topshop-tiny.com.br/...` |
| `ONEDRIVE_PRECIFICACAO_1` | 1º caminho OneDrive | (pré-configurado) |
| `ONEDRIVE_PRECIFICACAO_2` | 2º caminho OneDrive | (pré-configurado) |
| `ONEDRIVE_PRECIFICACAO_3` | 3º caminho (opcional) | (vazio) |
| `ONEDRIVE_PRECIFICACAO_4` | 4º caminho (opcional) | (vazio) |
| `ONEDRIVE_PRECIFICACAO_5` | 5º caminho (opcional) | (vazio) |

---

## Estrutura de pastas

```
CriarPlanilhasAmazon/
│
├── 📄 .env                          ← Configurações (EDITE AQUI)
├── 📄 app.py                        ← Arquivo principal
├── 📄 requirements.txt              ← Lista de dependências Python
├── 📄 Criar Planilhas Amazon.bat    ← Atalho para iniciar (duplo clique)
│
├── 📂 core/                         ← Lógica interna (NÃO MEXER)
│   ├── config.py                    ← Configurações do sistema
│   ├── utils.py                     ← Funções auxiliares
│   ├── 📂 carregadores/             ← Leitura de dados
│   ├── 📂 processadores/            ← Processamento de templates
│   └── 📂 mapeadores/               ← Mapeamento de colunas
│
├── 📂 ui/                           ← Interface (NÃO MEXER)
│   ├── componentes.py               ← Componentes visuais
│   └── sidebar.py                   ← Barra lateral
│
├── 📂 Templates de Criação/         ← Templates .xlsm da Amazon
│
├── 📄 Precificacao.xlsx             ← Base de preços (via OneDrive)
├── 📄 DESCRIÇÃO.xlsx                ← Base de descrições (via upload)
├── 📄 termos_remover.txt            ← Termos para limpeza
├── 📄 termos_substituir.txt         ← Substituições para limpeza
│
└── 📂 .venv/                        ← Ambiente virtual Python (NÃO MEXER)
```

---

## Perguntas frequentes (FAQ)

### ❓ Preciso instalar algo?
Sim, precisa do **Python 3.10+** e algumas bibliotecas. Veja o `GUIA_INSTALACAO.md`.

### ❓ Como inicio o sistema?
Dê **duplo clique** no arquivo `Criar Planilhas Amazon.bat`. Ele faz tudo automaticamente.

### ❓ O que é o arquivo `.bat`?
É um atalho que verifica se tudo está instalado, instala o que falta, e abre o sistema no navegador.

### ❓ Posso rodar em mais de um computador?
Sim! Copie toda a pasta `CriarPlanilhasAmazon` para o outro computador. Cada computador pode ter seu próprio `.env` com caminhos diferentes.

### ❓ Os dados são salvos onde?
- Dados processados: ficam no arquivo que você baixa
- Termos de limpeza: ficam nos arquivos `.txt` na pasta raiz
- Nenhum dado é enviado para a internet

### ❓ Posso usar o sistema offline?
Sim, após a primeira instalação. O sistema roda 100% local.

### ❓ O que é "Atualizar Precificação"?
Copia a versão mais recente do arquivo de preços do OneDrive para a pasta local do sistema.

### ❓ Preciso atualizar o sistema?
Quando houver uma nova versão, basta substituir os arquivos. O `.env` deve ser mantido com suas configurações.

---

## Solução de problemas

### Problemas com bases de dados

| Problema | Causa | Solução |
|----------|-------|---------|
| Precificação "Ausente" | Arquivo não encontrado | Clique em "Atualizar Precificação" ou verifique o caminho no `.env` |
| Descrição "Ausente" | Arquivo não foi enviado | Faça upload pela barra lateral |
| Preço aparece vazio | SKU não existe na base de preços | Verifique se o SKU está correto na planilha de precificação |
| Medidas em branco | SKU não encontrado na base de descrição | Verifique se o produto está cadastrado |
| Título muito longo | Mais de 200 caracteres | Reduza o título na base de descrição |

### Problemas técnicos

| Problema | Solução |
|----------|---------|
| `ModuleNotFoundError: No module named 'streamlit'` | Execute: `pip install streamlit` |
| `ModuleNotFoundError: No module named 'openpyxl'` | Execute: `pip install openpyxl` |
| `ModuleNotFoundError: No module named 'dotenv'` | Execute: `pip install python-dotenv` |
| Porta 8501 já em uso | Feche outras instâncias do Streamlit ou use: `python -m streamlit run app.py --server.port 8502` |
| Erro de permissão ao copiar arquivo | Feche o arquivo Excel e tente novamente |
| Arquivo `.env` não encontrado | Crie o arquivo na pasta raiz (veja `GUIA_INSTALACAO.md`) |
| Python não encontrado | Instale Python e marque "Add Python to PATH" |

### Como ler os logs

Durante o processamento, o sistema mostra logs em tempo real. Os ícones significam:

| Ícone | Significado |
|-------|-------------|
| ✅ | Sucesso — SKU processado corretamente |
| ⚠️ | Aviso — Algum dado está faltando, mas continuou |
| ❌ | Erro — SKU não pôde ser processado |
| 📋 | Informação — Dados encontrados e mapeados |

---

## Qualquer outro problema

> Senta na cadeira, respira fundo, pensa **"eu preciso mesmo resolver isso aqui?"**.
> Após refletir, chama o Gemini e manda ele arrumar. Se o Gemini não arrumar, aí chama o João (descubra qual).