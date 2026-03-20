# Design — Toggle de Busca na Internet (Web Search)

**Data**: 2026-03-04
**Status**: Aprovado
**Abordagem**: Toggle por job no ClassifyTab (Abordagem A)

## Objetivo

Permitir que consultoras habilitem busca na internet durante a classificação, para que o Grok pesquise informações sobre fornecedores, produtos e materiais desconhecidos, enriquecendo a classificação com contexto real.

## Custo Estimado

| Linhas no arquivo | Custo adicional (busca web) |
|---|---|
| 500 | $0.03 |
| 1.000 | $0.05 |
| 5.000 | $0.25 |
| 10.000 | $0.50 |
| 20.000 | $1.00 |
| 50.000 | $2.50 |

Custo da tool `web_search` da xAI: $5 por 1.000 invocações. Adicional aos tokens normais.

## Fluxo de Dados

```
ClassifyTab (toggle "Busca na Internet")
  → submitClassificationJobRaw({ ..., useWebSearch: true })
    → POST /api/SubmitTaxonomyJob { ..., "useWebSearch": true }
      → status.json { ..., "use_web_search": true }
        → Worker (process_chunk) lê do status.json
          → _call_openai_api() adiciona tools ao payload:
             "tools": [{"type": "web_search"}]
```

Sem o toggle ativado → fluxo idêntico ao atual, zero impacto.

## UI — ClassifyTab

Toggle posicionado entre o upload de hierarquia e o botão de submissão:

- **Label**: "Busca na Internet"
- **Descrição auxiliar**: "O Grok pesquisa na web sobre cada item para classificar com mais contexto."
- **Default**: desligado (OFF)
- **Estado**: `useState<boolean>(false)` local no ClassifyTab

## Backend — LLM Classifier

Quando `use_web_search=True`:

1. Adiciona `"tools": [{"type": "web_search"}]` ao payload
2. Adiciona instrução ao system prompt:

```
BUSCA NA INTERNET (HABILITADA):
Você tem acesso à internet. Para itens com descrições ambíguas,
códigos, siglas, nomes de fornecedores, fabricantes ou marcas
que você não reconhece com certeza:
- Pesquise na web o que o fornecedor/fabricante produz
- Pesquise o que o produto/material/serviço é
- Use essa informação para escolher a categoria mais precisa

Mantenha o formato de saída JSON idêntico.
```

Abordagem genérica — o Grok decide autonomamente quando vale buscar. Itens óbvios não disparam busca desnecessária.

## Arquivos Modificados

| Arquivo | Mudança |
|---------|---------|
| `frontend/.../ClassifyTab.tsx` | Toggle na UI |
| `frontend/.../useTaxonomySession.ts` | Passa `useWebSearch` na chamada |
| `frontend/src/lib/api.ts` | Novo param em `submitClassificationJobRaw` |
| `blueprints/classification_bp.py` | Lê `useWebSearch` do body, salva no status.json |
| `src/worker_helpers.py` | Lê `use_web_search` do job, passa ao classificador |
| `src/llm_classifier.py` | Adiciona `tools` e instrução ao payload |

## Testes

| Teste | Valida |
|-------|--------|
| `test_web_search_adds_tools_to_payload` | Payload contém `tools` quando flag ativo |
| `test_web_search_adds_prompt_instruction` | System message contém instrução de busca |
| `test_no_web_search_by_default` | Sem flag, payload e prompt inalterados |
| `test_submit_job_saves_web_search_flag` | SubmitTaxonomyJob salva flag no status.json |
| `test_worker_passes_web_search_to_classifier` | Worker propaga flag ao classificador |
