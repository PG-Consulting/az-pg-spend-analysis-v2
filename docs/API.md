# Referência de API — Spend Analysis v3

Base URL (local): `http://localhost:7071/api`

Todos os endpoints usam `AuthLevel.ANONYMOUS`. Respostas em JSON (`application/json`).

---

## Projetos e Setores

### `GET /api/ListSectors`

Lista todos os setores criados.

**Response 200**
```json
[
  {
    "name": "naval",
    "display_name": "Naval",
    "custom_hierarchy": null,
    "created_at": "2026-02-18T12:00:00Z"
  }
]
```

---

### `POST /api/CreateSector`

Cria um novo setor.

**Body**
```json
{
  "name": "naval",
  "display_name": "Naval",
  "custom_hierarchy_b64": "<base64 do XLSX opcional>"
}
```

**Response 200**
```json
{ "sector": { "name": "naval", "display_name": "Naval", ... } }
```

---

### `PUT /api/UpdateSector`

Atualiza nome ou hierarquia de um setor existente.

**Body**
```json
{
  "name": "naval",
  "display_name": "Naval Offshore",
  "custom_hierarchy_b64": "<base64 opcional>"
}
```

---

### `GET /api/ListProjects`

Lista todos os projetos, com opção de filtrar por setor.

**Query params**: `sector` (opcional)

**Response 200**
```json
[
  {
    "project_id": "naval-wartsila",
    "display_name": "Naval - WÄRTSILÄ",
    "sector": "naval",
    "client_context": "...",
    "hierarchy_source": "own",
    "use_sector_kb": true,
    "created_at": "..."
  }
]
```

---

### `POST /api/CreateProject`

Cria um novo projeto.

**Body**
```json
{
  "display_name": "Naval - WÄRTSILÄ",
  "sector": "naval",
  "client_context": "Contexto da empresa para o LLM",
  "custom_hierarchy_b64": "<base64 do XLSX opcional>",
  "hierarchy_filename": "hierarquia_naval.xlsx",
  "use_sector_kb": true,
  "few_shot_max_examples": 5
}
```

**Response 200**
```json
{
  "project": {
    "project_id": "naval-wartsila",
    "display_name": "Naval - WÄRTSILÄ",
    ...
  }
}
```

---

### `PUT /api/UpdateProject`

Atualiza configurações de um projeto.

**Body**
```json
{
  "project_id": "naval-wartsila",
  "display_name": "...",
  "client_context": "...",
  "custom_hierarchy_b64": "...",
  "use_sector_kb": false,
  "few_shot_max_examples": 10
}
```

---

### `DELETE /api/DeleteProject`

Remove um projeto e seus artefatos.

**Query params**: `projectId`

**Response 200**
```json
{ "success": true, "project_id": "naval-wartsila" }
```

---

### `GET /api/GetProjectHierarchy`

Retorna a hierarquia resolvida do projeto (projeto → setor → padrão).

**Query params**: `projectId`

**Response 200**
```json
{
  "hierarchy": [
    { "N1": "Materiais", "N2": "OEM WARTSILA", "N3": "Peças de Motor", "N4": "Materiais OEM" }
  ],
  "source": "own",
  "project_id": "naval-wartsila"
}
```

`source` pode ser `"own"`, `"inherited"` ou `"padrao"`.

> **Nota**: O endpoint `CheckCompatibility` foi removido. A compatibilidade entre projetos é gerida automaticamente pela KB do setor (referência viva) + promoção seletiva.

---

## Classificação

### `POST /api/SubmitTaxonomyJob`

Submete um arquivo para classificação assíncrona.

**Body** (multipart/form-data ou JSON com base64)
```json
{
  "file_b64": "<base64 do arquivo>",
  "filename": "compras_q1.xlsx",
  "projectId": "naval-wartsila",
  "descColumn": "Descrição",
  "custom_hierarchy_b64": "<base64 opcional — override da hierarquia do projeto>"
}
```

Suporta também path legado com `sector` em vez de `projectId`.

**Response 200**
```json
{
  "jobId": "550e8400-e29b-41d4-a716-446655440000",
  "status": "PENDING",
  "totalChunks": 3
}
```

---

### `GET /api/GetTaxonomyJobStatus`

Retorna o status atual do job (para polling).

**Query params**: `jobId`

**Response 200**
```json
{
  "jobId": "550e8400...",
  "status": "PROCESSING",
  "progress": {
    "processed_chunks": 2,
    "total_chunks": 3,
    "pct": 66.7
  },
  "error": null
}
```

`status`: `PENDING` | `PROCESSING` | `CLASSIFIED` | `APPROVED` | `COMPLETED` | `ERROR`

---

### `GET /api/GetJobResults`

Retorna os itens classificados de um job (status `CLASSIFIED` ou posterior).

**Query params**: `jobId`, `page` (default 1), `pageSize` (default 200, max 500)

**Response 200**
```json
{
  "jobId": "550e8400...",
  "total": 1500,
  "page": 1,
  "page_size": 200,
  "items": [
    {
      "index": 0,
      "description": "Válvula esfera DN50",
      "N1": "Materiais",
      "N2": "Tubulação",
      "N3": "Válvulas",
      "N4": "Válvulas de Esfera",
      "confidence": 0.92,
      "source": "LLM (Batch)",
      "status": "Unico"
    }
  ]
}
```

---

## Revisão Humana

### `POST /api/ReclassifyItems`

Re-classifica itens rejeitados usando instrução do consultor.

**Body**
```json
{
  "jobId": "550e8400...",
  "projectId": "naval-wartsila",
  "items": [
    { "index": 42, "description": "Filtro de óleo" },
    { "index": 87, "description": "Bomba centrífuga 3\" " }
  ],
  "instruction": "Itens de manutenção preventiva devem ir em MRO > Manutenção"
}
```

**Response 200**
```json
{
  "results": [
    {
      "index": 42,
      "N1": "MRO",
      "N2": "Manutenção",
      "N3": "Filtros",
      "N4": "Filtros de Óleo",
      "confidence": 0.88,
      "source": "LLM (Reclassified)"
    }
  ]
}
```

---

### `POST /api/ApproveClassifications`

Finaliza a revisão: salva decisões, alimenta KB, gera Excel.

**Body**
```json
{
  "jobId": "550e8400...",
  "projectId": "naval-wartsila",
  "decisions": [
    {
      "index": 0,
      "decision": "approved",
      "N1": "Materiais", "N2": "Tubulação", "N3": "Válvulas", "N4": "Válvulas de Esfera",
      "contributeToKB": true
    },
    {
      "index": 1,
      "decision": "edited",
      "N1": "MRO", "N2": "Manutenção", "N3": "Filtros", "N4": "Filtros de Óleo",
      "contributeToKB": true
    },
    {
      "index": 2,
      "decision": "rejected",
      "contributeToKB": false
    }
  ]
}
```

`decision`: `"approved"` | `"edited"` | `"rejected"`

**Response 200**
```json
{
  "success": true,
  "summary": {
    "total": 1500,
    "approved": 1350,
    "edited": 100,
    "rejected": 50,
    "kb_entries_added": 1450
  },
  "download_filename": "classificado_compras_q1.xlsx",
  "file_content_b64": "<base64 do Excel gerado>"
}
```

---

## Knowledge Base

### `GET /api/GetKnowledgeBase`

Retorna entradas da KB com paginação e filtros.

**Query params**:
- `projectId` (obrigatório)
- `page` (default 1)
- `pageSize` (default 50, max 200)
- `source` — filtrar por fonte (`llm_approved`, `consultant_correction`, `reclassified_with_guidance`)
- `n4` — filtrar por N4
- `search` — busca textual na descrição

**Response 200**
```json
{
  "entries": [...],
  "total": 3420,
  "page": 1,
  "page_size": 50,
  "total_pages": 69
}
```

---

### `POST /api/AddKBEntry`

Adiciona entrada manual à KB.

**Body**
```json
{
  "projectId": "naval-wartsila",
  "description": "Bomba de água salgada",
  "N1": "Equipamentos",
  "N2": "Bombas",
  "N3": "Bombas Centrífugas",
  "N4": "Bombas de Água Salgada",
  "source": "consultant_correction",
  "confidence": 1.0
}
```

**Response 200**
```json
{ "success": true, "entry_count": 3421 }
```

---

### `PUT /api/UpdateKBEntry`

Edita uma entrada existente.

**Body**
```json
{
  "projectId": "naval-wartsila",
  "entryId": "uuid",
  "N1": "...", "N2": "...", "N3": "...", "N4": "..."
}
```

---

### `DELETE /api/DeleteKBEntry`

Remove uma entrada da KB.

**Query params**: `projectId`, `entryId`

**Response 200**
```json
{ "success": true }
```

---

### `GET /api/GetKBCoverage`

Retorna cobertura da KB em relação à hierarquia do projeto.

**Query params**: `projectId`

**Response 200**
```json
{
  "total_n4s": 120,
  "covered_n4s": 87,
  "coverage_pct": 72.5,
  "underserved": [
    { "N4": "Válvulas de Retenção", "count": 0 },
    { "N4": "Compressores de Parafuso", "count": 1 }
  ]
}
```

---

### `GET /api/GetKBVersions`

Lista versões (snapshots) disponíveis da KB.

**Query params**: `projectId`

**Response 200**
```json
{
  "versions": [
    { "version_id": "v2_2026-02-18", "created_at": "...", "entry_count": 3421 },
    { "version_id": "v1_2026-02-17", "created_at": "...", "entry_count": 1200 }
  ]
}
```

---

### `POST /api/RollbackKB`

Restaura a KB para uma versão anterior.

**Body**
```json
{
  "projectId": "naval-wartsila",
  "versionId": "v1_2026-02-17"
}
```

**Response 200**
```json
{ "success": true, "entry_count": 1200 }
```

---

### `GET /api/ExportKB`

Exporta a KB como arquivo XLSX (base64).

**Query params**: `projectId`

**Response 200**
```json
{
  "filename": "kb_naval-wartsila_2026-02-18.xlsx",
  "file_b64": "<base64>"
}
```

---

### `POST /api/ImportKB`

Importa entradas de um XLSX para a KB (merge, não substituição).

**Body**
```json
{
  "projectId": "naval-wartsila",
  "file_b64": "<base64 do XLSX>",
  "filename": "kb_import.xlsx"
}
```

**Response 200**
```json
{
  "success": true,
  "added": 150,
  "updated": 30,
  "skipped": 10,
  "total": 3571
}
```

---

## Knowledge Base do Setor

### `GET /api/GetSectorKB`

Retorna entradas da KB do setor com paginação e filtros.

**Query params**:
- `sectorName` (obrigatório)
- `page` (default 1)
- `pageSize` (default 50, max 200)
- `source` — filtrar por fonte
- `n4` — filtrar por N4
- `search` — busca textual na descrição

**Response 200**
```json
{
  "entries": [...],
  "total": 500,
  "page": 1,
  "page_size": 50,
  "total_pages": 10
}
```

---

### `POST /api/AddSectorKBEntry`

Adiciona entrada manual à KB do setor.

**Body**
```json
{
  "sectorName": "naval",
  "description": "Bomba de água salgada",
  "N1": "Equipamentos",
  "N2": "Bombas",
  "N3": "Bombas Centrífugas",
  "N4": "Bombas de Água Salgada",
  "source": "consultant_correction",
  "confidence": 1.0
}
```

**Response 200**
```json
{ "success": true, "entry_count": 501 }
```

---

### `PUT /api/UpdateSectorKBEntry`

Edita uma entrada existente da KB do setor.

**Body**
```json
{
  "sectorName": "naval",
  "entryId": "uuid",
  "N1": "...", "N2": "...", "N3": "...", "N4": "..."
}
```

---

### `DELETE /api/DeleteSectorKBEntry`

Remove uma entrada da KB do setor.

**Query params**: `sectorName`, `entryId`

**Response 200**
```json
{ "success": true }
```

---

### `GET /api/GetSectorKBCoverage`

Retorna cobertura da KB do setor em relação à hierarquia.

**Query params**: `sectorName`

**Response 200**
```json
{
  "total_n4s": 120,
  "covered_n4s": 95,
  "coverage_pct": 79.2,
  "underserved": [...]
}
```

---

### `GET /api/GetSectorKBVersions`

Lista versões (snapshots) disponíveis da KB do setor.

**Query params**: `sectorName`

**Response 200**
```json
{
  "versions": [
    { "version_id": "v2_2026-02-20", "created_at": "...", "entry_count": 500 }
  ]
}
```

---

### `POST /api/RollbackSectorKB`

Restaura a KB do setor para uma versão anterior.

**Body**
```json
{
  "sectorName": "naval",
  "versionId": "v1_2026-02-18"
}
```

**Response 200**
```json
{ "success": true, "entry_count": 300 }
```

---

### `GET /api/ExportSectorKB`

Exporta a KB do setor como arquivo XLSX (base64).

**Query params**: `sectorName`

**Response 200**
```json
{
  "filename": "kb_sector_naval_2026-02-20.xlsx",
  "file_b64": "<base64>"
}
```

---

### `POST /api/ImportSectorKB`

Importa entradas de um XLSX para a KB do setor (merge, não substituição).

**Body**
```json
{
  "sectorName": "naval",
  "file_b64": "<base64 do XLSX>",
  "filename": "kb_import.xlsx"
}
```

**Response 200**
```json
{
  "success": true,
  "added": 50,
  "updated": 10,
  "skipped": 5,
  "total": 565
}
```

---

### `POST /api/PromoteToSectorKB`

Promove entradas selecionadas da KB de um projeto para a KB do setor.

**Body**
```json
{
  "projectId": "naval-wartsila",
  "sectorName": "naval",
  "entryIds": ["uuid1", "uuid2", "uuid3"]
}
```

**Response 200**
```json
{
  "success": true,
  "promoted": 3,
  "skipped": 0,
  "sector_total": 568
}
```

---

## ML Legado

### `POST /api/TrainModel`

Treina um novo modelo ML para um setor.

**Body**: `{ "sector": "varejo", "training_data_b64": "..." }`

### `GET /api/GetModelHistory`

**Query params**: `sector`

### `POST /api/SetActiveModel`

**Body**: `{ "sector": "varejo", "version": "v2" }`

### `GET /api/GetModelInfo`

**Query params**: `sector`

### `GET /api/GetTrainingData`

**Query params**: `sector`, `page`, `pageSize`

### `POST /api/DeleteTrainingData`

**Body**: `{ "sector": "varejo" }`

---

## Copilot (Legacy)

### `GET /api/get-token`

Retorna token Direct Line para o Copilot Studio.

**Response 200**
```json
{ "token": "...", "conversationId": "..." }
```

### `GET /api/SearchMemory`

**Query params**: `sector`, `query`

### `DELETE /api/DeleteMemoryRule`

**Query params**: `sector`, `ruleId`

---

## Códigos de Erro

| Código | Significado |
|--------|-------------|
| 400 | Parâmetro ausente ou inválido |
| 404 | Recurso não encontrado (job, projeto, versão KB) |
| 409 | Conflito (ex: nome de projeto já existe) |
| 500 | Erro interno (detalhes no body `{"error": "..."}`) |

Jobs com erro retornam `status: "ERROR"` via `GetTaxonomyJobStatus` com campo `error` preenchido.
