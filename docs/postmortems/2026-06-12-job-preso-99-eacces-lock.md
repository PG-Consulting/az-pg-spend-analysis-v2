# Postmortem — Job preso em 99% por PermissionError (EACCES) no file lock

**Data do incidente:** 2026-06-12
**Severidade:** Alta
**Autor:** Sessão de investigação 2026-06-12 (Claude Code + Victor Juliani)

## 1. O que quebrou

- Job `2fa71054-bbed-4927-9ad6-8aa4dbb37975` (projeto `teste`, `Base_Indiretos 1206.xlsx`,
  186 linhas, 1 chunk): **a classificação completou com sucesso** (186/186 itens via Grok
  em ~40s, 17.258 tokens cobrados), mas o worker morreu **entre o fim do chunk e a
  consolidação**. Status ficou `PROCESSING`; a UI mostrou "186 de 186 itens processados"
  com barra travada em 99%, **sem nenhum erro exibido**.
- A consultora aguardou ~6 min e cancelou (17:11 UTC) — o resultado pago foi descartado
  (`result_0.json` completo ainda existe no file share, mas o job é CANCELLED).
- Janela: crash às 17:05:38 UTC; sem o cancel, o retry da fila só chegaria às ~17:50
  (45 min depois). Impacto financeiro direto pequeno (~centavos), impacto de confiança
  alto — dois dias após o incidente de créditos, a plataforma "travou de novo" aos olhos
  do usuário.

## 2. Por que quebrou

Uma causa raiz com três agravantes empilhados:

1. **Causa raiz — EACCES no flock sobre CIFS:** o lock de `status.json` vive no Azure
   File Share montado via CIFS (`/mount/models`). Em contenção (a UI faz poll do status
   a cada 5s e pega o mesmo lock), o `fcntl.flock(LOCK_EX | LOCK_NB)` pode retornar
   **EACCES em vez de EWOULDBLOCK** (POSIX permite os dois). A lib `filelock` estava
   **sem pin** (`filelock>=3.12.0`) e o build remoto do deploy resolveu uma versão que
   propaga EACCES como `PermissionError` fatal em vez de tratar como "lock ocupado".
   O worker crashou no `read_status` entre batches (`worker_helpers.py:783`).
2. **Agravante — lease preso:** o caminho de exceção genérica mantém o job `PROCESSING`
   de propósito (para o retry da fila retomar), mas **não limpava o lease**
   (`processing_worker_id`) do worker que morreu. Um retry rápido (<10 min) seria
   engolido pelo guard de lease fresco sem retomar nada (bug latente).
3. **Agravante — retry em 45 min:** o `visibilityTimeout: 00:45:00` do host.json é
   também o delay de redelivery de mensagem falhada. O job ficou sem dono, a 99%, sem
   erro e sem retry por 45 minutos — janela mais que suficiente para o usuário cancelar.

## 3. Detecção

- **Como:** usuária reportou por mensagem ("parado há mais de 10 min na tela 99%",
  ~13:10 BRT). Investigação na mesma hora: status.json do job no file share +
  traceback completo no App Insights (PermissionError no flock) + probe na API xAI
  (200 — créditos OK) + inspeção das queues (vazias, sem poison).
- **Tempo até detecção:** ~5 min entre o crash e o report da usuária (poll da UI
  continuou funcionando — só não havia campo `error` para exibir). Nenhum alerta
  automático para "PROCESSING com processed==total e sem progresso".

## 4. Mitigação

- A usuária cancelou o job (ação dela, antes do diagnóstico) — parou o sintoma na UI.
- Confirmado que créditos xAI estão restaurados (200 no /v1/models) e que o sistema
  auto-curaria em 45 min via steal de lease stale — sem ação emergencial em produção.
- Orientação: re-submeter o arquivo após o deploy do fix (re-run custa ~17k tokens).

## 5. Action items

| # | Ação | Owner | Status |
|---|------|-------|--------|
| 1 | Tratar EACCES como "lock ocupado" com retry dentro do budget de 10s (`src/file_lock.py::_acquire_lock`) | Claude Code | **Concluído** (este PR) |
| 2 | Pinar `filelock==3.20.0` no requirements.txt (build remoto não drifta mais) | Claude Code | **Concluído** (este PR) |
| 3 | Crash path limpa o próprio lease antes do re-raise (retry re-claima imediato; fecha o bug latente do guard de lease fresco) | Claude Code | **Concluído** (este PR) |
| 4 | Deploy do backend com o fix (`func azure functionapp publish pg-ai-pi-spendai-api --python`) | Victor | Pendente (aprovação) |
| 5 | Re-submeter `Base_Indiretos 1206.xlsx` no projeto `teste` após deploy | Consultora | Pendente |
| 6 | Rotear locks de KB/config (`knowledge_base.py:24`, `project_manager.py:23`) pelo mesmo acquire tolerante a EACCES | Backlog (issue) | Pendente |
| 7 | Pinar/constranger demais deps `>=` do requirements.txt (PyJWT/cryptography primeiro) | Backlog (issue) | Pendente |
| 8 | UX: expor "retomada automática em andamento" no GetTaxonomyJobStatus quando PROCESSING com lease stale (ninguém mais encara 99% mudo) | Backlog (issue) | Pendente |

## Referências

- Postmortem anterior relacionado: `2026-06-10-creditos-xai-jobs-grandes.md` (créditos
  xAI + resume de jobs grandes — o fix de resume daquele incidente é o que torna o
  steal de lease stale o backstop deste aqui).
- Evidência: traceback App Insights 17:05:38 UTC (`PermissionError: [Errno 13]` em
  `filelock/_unix.py:76`), status.json do job (token_usage preenchido, CANCELLED),
  queues `taxonomy-jobs`/`taxonomy-jobs-poison` vazias.
