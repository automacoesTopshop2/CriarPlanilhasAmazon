# Prompt para o time/IA do BDAmazon — criação de SKUs em lote

> ✅ **ENTREGUE (2026-06-17).** O BDAmazon implementou `POST /api/v1/skus/lote`
> (até 1000 itens/chamada, sucesso parcial 200/207, lote conta como 1 requisição
> no rate-limit). Já está integrado no CriarPlanilhasAmazon:
> `core/bdamazon_client.py::criar_skus_lote`, proxy
> `POST /api/bdamazon/criar-sku-lote` e o botão "Solicitar SKU-Market de todos".
> O texto abaixo é o pedido original, mantido como referência do contrato.

> **Contexto para colar no BDAmazon.** Hoje o sistema CriarPlanilhasAmazon
> (cliente da API BDAmazon) cria SKUs **um a um** via `POST /api/v1/skus`.
> Quando o operador solicita 500 SKUs de uma vez, são 500 requisições
> sequenciais, limitadas pelo rate-limit (60 req/min ≈ 1/s), levando ~8+ min.
> Precisamos de um endpoint que aceite um **lote** de SKUs numa única chamada.

---

## O que precisamos

Criar um endpoint de criação em lote que receba uma lista de itens e devolva,
para cada item, o resultado (sucesso com `sku_market` gerado, ou erro), sem
abortar o lote inteiro quando um item falha (**sucesso parcial**).

### Endpoint sugerido

```
POST /api/v1/skus/lote
Headers:
  X-API-Key: <chave>
  Content-Type: application/json
```

### Corpo da requisição

Os campos por item são os mesmos do `POST /api/v1/skus` atual
(`conta_codigo`, `sku_raiz`, `usuario_codigo`, e opcionais `asin`, `titulo`,
`tipo_anuncio_id`, `obs`, `data_lancamento`):

```json
{
  "itens": [
    { "conta_codigo": "BOX2", "sku_raiz": "ABC123", "usuario_codigo": "joao.silva", "asin": null },
    { "conta_codigo": "BOX2", "sku_raiz": "K-998",  "usuario_codigo": "joao.silva" },
    { "conta_codigo": "VERD-CLA", "sku_raiz": "XYZ987", "usuario_codigo": "joao.silva" }
  ]
}
```

### Resposta esperada (sucesso parcial, HTTP 207 ou 200)

Para **cada** item de entrada, na **mesma ordem**, devolver um resultado.
Incluir o índice (`indice`) para casar com a entrada mesmo se a ordem mudar:

```json
{
  "total": 3,
  "criados": 2,
  "falhas": 1,
  "resultados": [
    {
      "indice": 0,
      "ok": true,
      "sku_market": "BOX2-ABC123",
      "sku_raiz": "ABC123",
      "versao": 1,
      "conta_codigo": "BOX2",
      "status_produto": "LIVRE"
    },
    {
      "indice": 1,
      "ok": true,
      "sku_market": "BOX2-K-998",
      "sku_raiz": "K-998",
      "versao": 1,
      "conta_codigo": "BOX2",
      "status_produto": null
    },
    {
      "indice": 2,
      "ok": false,
      "sku_raiz": "XYZ987",
      "conta_codigo": "VERD-CLA",
      "erro": { "codigo": "CONTA_NAO_ENCONTRADA", "mensagem": "conta_codigo inválido" }
    }
  ]
}
```

## Requisitos / regras

1. **Sucesso parcial**: um item inválido **não** deve derrubar os demais.
   Cada item tem seu próprio `ok: true|false`.
2. **Mesma semântica do unitário**: cada item gera `sku_market` exatamente como
   `POST /skus` faz hoje (mesma versão, mesmo prefixo de conta, mesmo
   `status_produto` do catálogo quando disponível).
3. **Idempotência / duplicados**: se o `sku_raiz`+`conta` já existir, devolver o
   `sku_market` existente com um aviso (ex.: `"ja_existia": true`) em vez de erro,
   ou um erro claro — definam o comportamento e documentem.
4. **Limite de tamanho do lote**: aceitar pelo menos **500 itens** por chamada.
   Se houver teto, devolver 413/400 com mensagem clara informando o máximo.
5. **Rate-limit**: o lote deve contar como **1 requisição** (ou poucas) no
   rate-limit, não 500 — esse é o ponto central do pedido.
6. **Validação de entrada**: 400 com detalhe por item quando o corpo for inválido
   (ex.: `itens` ausente/vazio, item sem `conta_codigo`/`sku_raiz`).
7. **Autenticação**: mesmo `X-API-Key` do endpoint atual.
8. **Timeout**: processar 500 itens pode demorar — garantir timeout do servidor
   compatível, ou processar de forma síncrona com resposta única (preferível para
   o nosso uso atual). Se optarem por assíncrono (job + polling), descrevam o
   contrato (`job_id` + `GET /skus/lote/{job_id}`).

## Por favor, ao implementar, nos enviem

- O **path** e **método** finais (caso difiram de `POST /api/v1/skus/lote`).
- O **schema** exato de request e response (campos, tipos, opcionais).
- O **HTTP status** usado em sucesso total / parcial / erro de validação.
- Como ficam **duplicados** e **rate-limit** com o lote.

---

### Notas de integração (lado CriarPlanilhasAmazon)

Quando o endpoint existir, ligaremos no cliente `core/bdamazon_client.py` uma
função `criar_skus_lote(itens) -> list[ResultadoSku]` e trocaremos o laço
sequencial do "Solicitar SKU-Market de todos" (`site/static/js/app.js`) por uma
única chamada via novo proxy `POST /api/bdamazon/criar-sku-lote` em
`site/web_app.py`. Até lá, seguimos com a criação unitária sequencial.
