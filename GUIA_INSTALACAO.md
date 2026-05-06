# 🚀 Guia de Instalação — Sistema de Planilhas Amazon

**Versão:** 6.1  
**Última Atualização:** Abril de 2026  
**Sistema Operacional:** Windows 10 / 11

---

## 📋 Índice

1. [Requisitos do sistema](#1-requisitos-do-sistema)
2. [Instalar o Python](#2-instalar-o-python)
3. [Baixar o projeto](#3-baixar-o-projeto)
4. [Instalar dependências](#4-instalar-dependências)
5. [Configurar o arquivo .env](#5-configurar-o-arquivo-env)
6. [Primeiro teste](#6-primeiro-teste)
7. [Criar atalho na área de trabalho](#7-criar-atalho-na-área-de-trabalho)
8. [Atualização do sistema](#8-atualização-do-sistema)
9. [Desinstalação](#9-desinstalação)
10. [Solução de problemas na instalação](#10-solução-de-problemas-na-instalação)

---

## 1. Requisitos do sistema

Antes de começar, verifique se seu computador atende a esses requisitos:

| Requisito | Mínimo | Recomendado |
|-----------|--------|-------------|
| **Sistema Operacional** | Windows 10 | Windows 11 |
| **Memória RAM** | 4 GB | 8 GB |
| **Espaço em disco** | 1 GB | 2 GB |
| **Python** | 3.10 | 3.12+ |
| **Navegador** | Chrome, Edge ou Firefox | Chrome |
| **Rede** | Necessária para instalação | - |

### Programas necessários

| Programa | Para que serve | Link |
|----------|---------------|------|
| **Python** | Linguagem que roda o sistema | [python.org/downloads](https://www.python.org/downloads/) |
| **Navegador Web** | Onde o sistema abre a interface | Já vem instalado no Windows |

---

## 2. Instalar o Python

> ⚠️ **Se já tem Python instalado**, pule para o [passo 3](#3-baixar-o-projeto). Para verificar, abra o Prompt de Comando e digite: `python --version`

### Passo a passo

1. Acesse: **https://www.python.org/downloads/**

2. Clique no botão amarelo **"Download Python 3.x.x"**

3. Execute o instalador baixado (`.exe`)

4. **⚠️ ATENÇÃO — Marque estas duas opções na primeira tela:**

   ```
   ☑ Install launcher for all users
   ☑ Add Python to PATH          ← OBRIGATÓRIO!
   ```

   > ❌ Se você NÃO marcar "Add Python to PATH", o sistema NÃO vai funcionar.

5. Clique em **"Install Now"**

6. Aguarde a instalação finalizar

7. Clique em **"Close"**

### Verificar a instalação

Abra o **Prompt de Comando** (pesquise "cmd" no menu iniciar) e digite:

```
python --version
```

Resultado esperado:
```
Python 3.12.x    (ou versão similar)
```

Se aparecer `'python' não é reconhecido como um comando interno`, a instalação falhou. Repita o passo 2 marcando "Add Python to PATH".

### Verificar o pip

O `pip` é o gerenciador de pacotes do Python. Verifique se está instalado:

```
pip --version
```

Resultado esperado:
```
pip 24.x.x from ...
```

---

## 3. Baixar o projeto

### Opção A: Receber a pasta (mais fácil)

Se você recebeu a pasta `CriarPlanilhasAmazon` de um colega:

1. Copie toda a pasta para o seu computador (ex: `C:\Users\SeuNome\Desktop\CriarPlanilhasAmazon`)
2. Pule para o [passo 4](#4-instalar-dependências)

### Opção B: Baixar via Git

```bash
git clone <url-do-repositorio>
cd CriarPlanilhasAmazon
```

### Opção C: Baixar como ZIP

1. Baixe o arquivo `.zip` do repositório
2. Extraia para uma pasta (ex: `Desktop\CriarPlanilhasAmazon`)

---

## 4. Instalar dependências

O sistema precisa de 4 bibliotecas Python. Há duas formas de instalá-las:

### Método 1: Automático (recomendado)

Dê **duplo clique** no arquivo `Criar Planilhas Amazon.bat`. Ele verifica e instala tudo automaticamente.

### Método 2: Manual (pelo terminal)

1. Abra o **Prompt de Comando** ou **PowerShell**

2. Navegue até a pasta do projeto:
   ```
   cd C:\Users\SeuNome\Desktop\CriarPlanilhasAmazon
   ```

3. Instale todas as dependências de uma vez:
   ```
   pip install -r requirements.txt
   ```

   Ou instale uma por uma:
   ```
   pip install streamlit
   pip install openpyxl
   pip install pandas
   pip install python-dotenv
   ```

### O que cada biblioteca faz

| Biblioteca | Função | Tamanho |
|------------|--------|---------|
| `streamlit` | Cria a interface web (a tela do navegador) | ~200 MB |
| `openpyxl` | Lê e escreve arquivos Excel (.xlsx / .xlsm) | ~5 MB |
| `pandas` | Manipula tabelas e dados | ~50 MB |
| `python-dotenv` | Lê configurações do arquivo `.env` | ~0.1 MB |

### Verificar se instalou corretamente

```
python -c "import streamlit; print('streamlit OK')"
python -c "import openpyxl; print('openpyxl OK')"
python -c "import pandas; print('pandas OK')"
python -c "import dotenv; print('python-dotenv OK')"
```

Se todos mostrarem "OK", está tudo certo!

---

## 5. Configurar o arquivo .env

O arquivo `.env` contém todas as configurações do sistema. Ele já vem pré-configurado, mas pode precisar de ajustes.

### 5.1 Localizar o arquivo

O arquivo `.env` está na pasta raiz do projeto:

```
CriarPlanilhasAmazon/
├── .env           ← ESTE ARQUIVO
├── app.py
├── core/
└── ...
```

> **Não vê o arquivo?** Ele pode estar oculto. No Explorador de Arquivos:
> - Windows 10: `Exibir` (na barra superior) → marque `Itens ocultos`
> - Windows 11: `Exibir` → `Mostrar` → `Itens ocultos`

### 5.2 Abrir para edição

Clique com **botão direito** no `.env` → **Abrir com** → **Bloco de Notas** (ou VS Code)

### 5.3 Configurações principais

#### Arquivos de base de dados

```env
# Nomes dos arquivos na pasta local
ARQUIVO_PRECIFICACAO=Precificacao.xlsx
ARQUIVO_DESCRICAO=DESCRIÇÃO.xlsx
ARQUIVO_REMOVER=termos_remover.txt
ARQUIVO_SUBSTITUIR=termos_substituir.txt
```

> **Na maioria dos casos, não precisa alterar estas linhas.** Só mude se seus arquivos estiverem em outro local ou tiverem outro nome.

#### URL de imagens

```env
URL_BASE_IMAGENS=https://topshop-tiny.com.br/wp-content/uploads/tiny
```

#### Caminhos do OneDrive (⚠️ pode precisar alterar)

```env
# Caminho 1 - Padrão Top Shop
ONEDRIVE_PRECIFICACAO_1=OneDrive - Top Shop\Criação de Anúncios - Documentos\Precificacao Amazon.xlsx

# Caminho 2 - Alternativo
ONEDRIVE_PRECIFICACAO_2=OneDrive\Criação de Anúncios - Documentos\Precificacao Amazon.xlsx

# Caminhos extras (adicione se precisar)
ONEDRIVE_PRECIFICACAO_3=
ONEDRIVE_PRECIFICACAO_4=
ONEDRIVE_PRECIFICACAO_5=
```

### 5.4 Como descobrir o caminho do OneDrive

1. Abra o **Explorador de Arquivos** (Windows + E)
2. No painel esquerdo, clique na pasta do **OneDrive**
3. Navegue até encontrar o arquivo **`Precificacao Amazon.xlsx`**
4. Clique com **botão direito** no arquivo → **Propriedades**
5. No campo **"Local"**, você verá algo como:
   ```
   C:\Users\Maria\OneDrive - Top Shop\Criação de Anúncios - Documentos
   ```
6. Copie esse caminho e adicione `\Precificacao Amazon.xlsx` no final
7. Cole no `.env`:

**Usando caminho relativo (tira o `C:\Users\Maria\`):**
```env
ONEDRIVE_PRECIFICACAO_1=OneDrive - Top Shop\Criação de Anúncios - Documentos\Precificacao Amazon.xlsx
```

**Usando caminho absoluto (caminho completo):**
```env
ONEDRIVE_PRECIFICACAO_1=C:\Users\Maria\OneDrive - Top Shop\Criação de Anúncios - Documentos\Precificacao Amazon.xlsx
```

> **💡 Dica:** O caminho **relativo** é preferível porque funciona mesmo se você trocar de computador (desde que a pasta do OneDrive tenha o mesmo nome). O sistema adiciona `C:\Users\SeuUsuario\` automaticamente.

### 5.5 Regras do arquivo .env

| Regra | Correto ✅ | Errado ❌ |
|-------|-----------|----------|
| Sem espaços ao redor do `=` | `ARQUIVO=teste.xlsx` | `ARQUIVO = teste.xlsx` |
| Sem aspas | `ARQUIVO=teste.xlsx` | `ARQUIVO="teste.xlsx"` |
| Uma variável por linha | (cada uma em sua linha) | (duas na mesma linha) |
| Comentários com `#` | `# isto é um comentário` | |
| Linhas vazias são ignoradas | | |

---

## 6. Primeiro teste

Depois de instalar tudo, vamos testar:

### 6.1 Iniciar o sistema

**Opção 1 — Duplo clique no .bat (mais fácil):**
- Dê duplo clique em `Criar Planilhas Amazon.bat`
- Uma janela preta vai aparecer mostrando o progresso
- O navegador vai abrir automaticamente

**Opção 2 — Pelo terminal:**
```
cd C:\Users\SeuNome\Desktop\CriarPlanilhasAmazon
python -m streamlit run app.py
```

### 6.2 Verificar a interface

O navegador deve abrir em: **http://localhost:8501**

Você deve ver:
- ✅ Título "📦 Sistema de Planilhas Amazon"
- ✅ Barra lateral com status das bases
- ✅ Menu de módulos (SKU, ASIN, Limpeza)

### 6.3 Testar a precificação

1. Na barra lateral, clique em **"🔄 Atualizar Precificação"**
2. Se aparecer ✅, o caminho do OneDrive está correto
3. Se aparecer ❌, edite o `.env` com o caminho correto (veja seção 5.4)

### 6.4 Encerrar o sistema

- **Se usou o .bat:** Feche a janela preta
- **Se usou o terminal:** Pressione `Ctrl + C`

---

## 7. Criar atalho na área de trabalho

Para facilitar o acesso, crie um atalho:

1. Navegue até a pasta `CriarPlanilhasAmazon`
2. Clique com **botão direito** em `Criar Planilhas Amazon.bat`
3. Selecione **"Criar atalho"**
4. Mova o atalho para a **Área de Trabalho**
5. (Opcional) Renomeie para "Planilhas Amazon"

---

## 8. Atualização do sistema

Quando receber uma versão nova:

### O que substituir

- ✅ `app.py` — Substituir
- ✅ `core/` — Substituir toda a pasta
- ✅ `ui/` — Substituir toda a pasta
- ✅ `Criar Planilhas Amazon.bat` — Substituir
- ✅ `requirements.txt` — Substituir

### O que NÃO substituir

- ❌ `.env` — Manter o seu (tem suas configurações pessoais)
- ❌ `termos_remover.txt` — Manter o seu
- ❌ `termos_substituir.txt` — Manter o seu
- ❌ `Precificacao.xlsx` — Será atualizado pelo OneDrive
- ❌ `DESCRIÇÃO.xlsx` — Será atualizado pelo upload

### Após atualizar

Execute novamente:
```
pip install -r requirements.txt
```

Isso garante que novas dependências sejam instaladas.

---

## 9. Desinstalação

Se precisar remover o sistema:

1. **Delete a pasta** `CriarPlanilhasAmazon`
2. **(Opcional) Remova as bibliotecas Python:**
   ```
   pip uninstall streamlit openpyxl pandas python-dotenv
   ```
3. **(Opcional) Desinstale o Python** pelo Painel de Controle

---

## 10. Solução de problemas na instalação

### ❌ "python não é reconhecido como comando"

**Causa:** Python não foi adicionado ao PATH durante a instalação.

**Solução 1 — Reinstalar:**
1. Desinstale o Python pelo Painel de Controle
2. Reinstale marcando ☑️ "Add Python to PATH"

**Solução 2 — Adicionar manualmente:**
1. Pesquise "Variáveis de Ambiente" no menu iniciar
2. Clique em "Editar variáveis de ambiente do sistema"
3. Clique em "Variáveis de Ambiente..."
4. Em "Path" (do usuário), adicione:
   ```
   C:\Users\SeuNome\AppData\Local\Programs\Python\Python312
   C:\Users\SeuNome\AppData\Local\Programs\Python\Python312\Scripts
   ```
5. Feche e abra um novo Prompt de Comando

### ❌ "pip não é reconhecido como comando"

**Solução:**
```
python -m ensurepip --upgrade
python -m pip install --upgrade pip
```

### ❌ Erro de permissão ao instalar pacotes

**Solução:**
```
pip install --user streamlit openpyxl pandas python-dotenv
```

### ❌ "ImportError: No module named 'dotenv'"

**Causa:** `python-dotenv` não foi instalado.

**Solução:**
```
pip install python-dotenv
```

> ⚠️ O pacote se chama `python-dotenv` (com hífen), mas no código é importado como `dotenv`.

### ❌ O .bat fecha imediatamente

**Causa:** Pode ser um erro de Python ou de dependência.

**Solução:**
1. Abra o Prompt de Comando manualmente
2. Navegue até a pasta:
   ```
   cd C:\Users\SeuNome\Desktop\CriarPlanilhasAmazon
   ```
3. Execute:
   ```
   python -m streamlit run app.py
   ```
4. Leia a mensagem de erro que aparecer

### ❌ Navegador não abre automaticamente

**Solução:**
- Abra manualmente: **http://localhost:8501**
- Se ainda não funcionar, verifique se o Streamlit está rodando no terminal

### ❌ "Address already in use"

**Causa:** Outra instância do Streamlit está rodando.

**Solução 1:** Feche todas as janelas de terminal e tente novamente

**Solução 2:** Use uma porta diferente:
```
python -m streamlit run app.py --server.port 8502
```

---

## 📝 Checklist de instalação

Use esta lista para verificar se tudo foi feito:

- [ ] Python 3.10+ instalado com "Add to PATH"
- [ ] `python --version` funciona no terminal
- [ ] `pip --version` funciona no terminal
- [ ] Pasta `CriarPlanilhasAmazon` no computador
- [ ] Dependências instaladas (`pip install -r requirements.txt`)
- [ ] Arquivo `.env` configurado com caminhos do OneDrive
- [ ] Sistema abre no navegador (http://localhost:8501)
- [ ] Precificação atualiza com sucesso (botão na sidebar)

---

**Instalação concluída! 🎉**

Para aprender a usar o sistema, consulte o [GUIA_INICIANTES.md](GUIA_INICIANTES.md).
