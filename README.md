# Spend Analysis v3

Plataforma de classificação taxonômica de gastos corporativos com **loop de aprendizado humano**. Consultores revisam as classificações geradas pelo LLM antes da entrega. As correções alimentam uma Knowledge Base (KB) por projeto, que é usada como few-shot RAG nas classificações futuras.

## Funcionalidades

- **Projetos por empresa** — hierarquia Setor → Projeto, com taxonomia customizada por projeto
- **Classificação Two-Phase** — Phase 1: KB direct match (sim ≥ 0.90, sem LLM); Phase 2: LLM com exemplos enriched por similaridade (TF-IDF cosine)
- **KB por setor e projeto** — KB do setor é referência viva mesclada automaticamente; promoção seletiva de entradas do projeto para o setor
- **Tela de revisão humana** — aprovar, editar ou rejeitar itens; re-classificar com instrução
- **Knowledge Base versionada** — export/import XLSX, rollback, cobertura por N4, toggle `use_sector_kb` por projeto
- **Copilot integrado** — análise conversacional desbloqueada após revisão aprovada
- **Compatibilidade legada** — setores `varejo` e `educacional` com modelos ML continuam funcionando

## Quickstart

### Pré-requisitos

- Python 3.9+
- Node.js 18+
- [Azure Functions Core Tools v4](https://learn.microsoft.com/azure/azure-functions/functions-run-local)
- [Azurite](https://learn.microsoft.com/azure/storage/common/storage-use-azurite) (emulador de storage local)

### Backend

```bash
# Instalar dependências
pip install -r requirements.txt

# Configurar secrets
cp local.settings.json.example local.settings.json
# Editar: GROK_API_KEY, DIRECT_LINE_SECRET

# Iniciar Azurite (em um terminal separado)
azurite --location AzuriteConfig

# Rodar backend
func start
# Endpoints disponíveis em http://localhost:7071/api
```

### Frontend

```bash
cd frontend
npm install
cp .env.local.example .env.local
# Editar: NEXT_PUBLIC_API_URL=http://localhost:7071/api

npm run dev
# Aplicação disponível em http://localhost:3000
```

## Fluxo de Uso

1. **Selecionar projeto** — escolha ou crie um projeto (Setor → Empresa)
2. **Upload do arquivo** — CSV/XLSX com coluna de descrições
3. **Classificação** — pipeline LLM com few-shot da KB do projeto
4. **Revisão** — aba "Revisar" habilita após classificação; aprovar/editar/rejeitar
5. **KB alimentada** — itens aprovados enriquecem a Knowledge Base
6. **Download** — Excel com dados revisados; Copilot desbloqueado para análise

## Documentação

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — arquitetura detalhada e decisões técnicas
- [`docs/API.md`](docs/API.md) — referência completa de endpoints
- [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) — guia de deploy no Azure
- [`CLAUDE.md`](CLAUDE.md) — instruções para o Claude Code (desenvolvimento)

## Testes

```bash
# Backend — 148 testes (pytest, ~6s)
python3 -m pytest tests/ -v

# Frontend — 23 testes (Jest + React Testing Library, ~1.5s)
cd frontend && npx jest --verbose
```

## Estrutura

```
├── function_app.py      # Entry point (~33 linhas, registra blueprints)
├── blueprints/          # 7 módulos: classification, review, knowledge, projects, models, copilot, worker
├── src/                 # Módulos Python (16 arquivos)
├── models/              # Artefatos ML + KBs de setor/projeto + jobs
│   ├── sectors/         # Configs e KBs curadas por setor
│   ├── projects/        # Configs e KBs por projeto
│   ├── educacional/     # Modelo ML legado
│   └── varejo/          # Modelo ML legado
├── tests/               # 7 suites de testes backend (148 testes)
├── data/taxonomy/       # Dicionário Spend_Taxonomy.xlsx
└── frontend/            # Next.js 14 + TypeScript + design system
```

## Stack

| Camada | Tecnologia |
|--------|-----------|
| Backend | Azure Functions v2 (Python 3.9+) |
| Frontend | Next.js 14 + TypeScript + TailwindCSS 3.4 |
| LLM | Grok/xAI `grok-4-1-fast-reasoning` |
| Few-shot RAG | TF-IDF cosine similarity |
| ML legado | scikit-learn (TF-IDF + LogisticRegression) |
| Chat | Microsoft Copilot Studio (Direct Line API) |
| Storage | Azure File Share / IndexedDB |
