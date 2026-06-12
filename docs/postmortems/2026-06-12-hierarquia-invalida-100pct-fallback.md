# Postmortem — Hierarquia inválida engolida em silêncio → job sem taxonomia (100% fallback)

**Data do incidente:** 2026-06-12
**Severidade:** Alta
**Autor:** Sessão de investigação 2026-06-12 (Claude Code + Victor Juliani)

## 1. O que quebrou

- Consultora criou o projeto `teste` (setor industrial) enviando hierarquia própria
  ("Versao Revisada Taxonomia 12Jun26.xlsx"). O parser não encontrou as colunas
  N1–N4, **a falha foi engolida** e o projeto foi salvo no estado inconsistente
  `hierarchy_source="own"` + `custom_hierarchy=null`.
- Os dois jobs de classificação do dia (186 linhas, "Base_Indiretos 1206.xlsx")
  rodaram **sem taxonomia nenhuma**: todos os 186 itens voltaram "Não Identificado"
  com confidence 0.0 (job `2fa71054` 17:04 UTC, cancelado; job `0b88e97e` 19:30 UTC,
  ERROR).
- A consultora viu o modal **"Classificação falhou: 100.0% dos itens não foram
  classificados (provável erro de API)"** — mensagem enganosa: a API xAI estava
  saudável (probe 200 em `/v1/models` e `chat/completions`).
- Custo real: ~17,4k tokens cobrados **duas vezes** por classificações que nunca
  poderiam dar certo.
- Bug satélite encontrado nos mesmos logs: o retention (`cleanup_old_jobs`) falhava
  **em todos os jobs legados** com `can't subtract offset-naive and offset-aware
  datetimes` (spam horário no App Insights desde a migração de timezone) — nenhum
  job terminal antigo era deletado.

## 2. Por que quebrou

Cadeia de três falhas silenciosas:

1. **Parse engolido no CreateProject** — `resolve_hierarchy_from_body()`
   (`src/project_manager.py`) só logava `warning` quando `parse_hierarchy_from_b64()`
   retornava `None`; o `body.setdefault("hierarchy_source", "padrao")` seguinte era
   no-op porque o frontend já envia `hierarchy_source="own"` explicitamente. Projeto
   persistido com intenção "own" e hierarquia nenhuma — HTTP 200, zero sinal à usuária.
2. **Nenhum guard no submit/worker** — `SubmitTaxonomyJob` resolvia a hierarquia do
   projeto (`None`) e enfileirava mesmo assim; o worker tratou `None` como
   "classificação aberta" (prompt genérico UNSPSC) em vez de erro.
3. **Mensagem de erro culpava a API** — o hardening `FALLBACK_ERROR_THRESHOLD` (≥95%
   fallback → ERROR, criado no incidente do web search) disparou corretamente, mas o
   texto fixo "provável erro de API" apontava para a causa errada; e o log final do
   consolidate imprimia "CLASSIFIED" mesmo após gravar ERROR, confundindo a forense.

O bug satélite do retention: `datetime.fromisoformat()` devolve datetime naive para
`created_at` de jobs criados na era `datetime.utcnow()`; subtração contra
`datetime.now(timezone.utc)` levanta `TypeError`, capturado por um `except` largo que
só loga e pula o job.

## 3. Detecção

- **Como:** usuária reportou o modal de erro via screenshot (12/jun ~17:05 BRT).
  Investigação na mesma hora: status.json do job no file share (100% fallback,
  `custom_hierarchy_list=null`) → App Insights da janela do job ("Hierarchy file:
  headers N1/N4 not found" + "hierarchy_file_base64 provided but parsing failed" na
  criação do projeto, 19:30:07 UTC) → project_config.json (`own` + `null`) → probe da
  API xAI (saudável, descartando billing).
- **Tempo até detecção:** ~3h30 entre o primeiro job ruim (17:04 UTC) e o report; root
  cause confirmada em ~30 min de forense.

## 4. Mitigação

- Não houve sangramento contínuo a estancar: o job falhava rápido (≈60s) e o custo por
  tentativa era pequeno (~17k tokens). A "mitigação" foi a própria investigação
  imediata + fix permanente no mesmo dia (branch `fix/hierarchy-parse-silent-swallow`).
- Recuperação da usuária: recriar o projeto re-enviando a planilha com cabeçalhos
  N1–N4 (após o deploy, o erro 400 explica exatamente isso).

## 5. Action items

- [x] CreateProject/UpdateProject: parse de hierarquia falhou → `ValidationError`
      (HTTP 400) com mensagem clara em português — fix neste branch
- [x] SubmitTaxonomyJob: guard `hierarchy_source=="own"` + hierarquia vazia → 400
      antes de criar o job — fix neste branch
- [x] UpdateProject parcial não rebaixa mais `own`→`padrao` (flip que desarmaria o
      guard) — fix neste branch
- [x] Log final do consolidate reflete o status real (ERROR vs CLASSIFIED) — fix
      neste branch
- [x] Modais Create/Edit exibem a mensagem real do backend (antes: genérico do axios) —
      fix neste branch
- [x] Retention: timestamps naive legados assumidos UTC — fix neste branch
- [ ] Deploy backend (manual, aprovação Victor) + frontend (push main) — owner: Victor
- [ ] Recriar projeto `teste` em produção com planilha corrigida — owner: consultora
      (orientar sobre cabeçalhos N1–N4)
- [ ] Worker `parse_custom_hierarchy` (b64 per-job inválido) ainda degrada em silêncio
      para classificação aberta — marcar job ERROR — owner: backlog
- [ ] Replicar `e.response?.data?.error` nos 5 catch sites restantes do frontend
      (KnowledgeTab ×2, SectorKnowledgeTab ×2, useProjects) — owner: backlog
- [ ] Avaliar tolerância do parser a cabeçalhos "Nível 1..4" (a planilha da consultora
      provavelmente usa esse formato) — owner: backlog
- [ ] `dictionary_content_b64` é campo morto no payload do job (sem consumidor) —
      remover ou implementar — owner: backlog
