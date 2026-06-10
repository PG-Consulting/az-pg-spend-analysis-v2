# Postmortem — Esgotamento de créditos xAI + jobs grandes nunca completam

**Data do incidente:** 2026-06-09 → 2026-06-10
**Severidade:** Alta
**Autor:** Sessão de investigação 2026-06-10 (Claude Code + Victor Juliani)

## 1. O que quebrou

- A partir de ~00:55 UTC de 10/jun, **toda chamada à API xAI passou a retornar HTTP 403**
  ("used all available credits or reached its monthly spending limit") — nenhum job
  classificava; todos terminavam ERROR com 100% fallback em segundos.
- Janela de impacto: 10/jun ~01:00 até a recarga de créditos (pendente na data deste doc).
- Contexto agravante: a base Vitapro de **66.493 linhas foi submetida 10+ vezes** entre
  23:50 de 09/jun e a manhã de 10/jun, sem nunca completar — cada tentativa morria aos
  ~30 min e era re-submetida manualmente.

## 2. Por que quebrou

Três causas encadeadas:

1. **Retirement silencioso do modelo (custo 5–6×):** em 15/mai/2026 a xAI aposentou o
   `grok-4-1-fast-reasoning` (~$0.20/$0.50 por M tokens). O slug virou alias do
   `grok-4.3`, cobrado a **$1.25/$2.50** — todo o consumo desde então saiu 5–6× mais
   caro sem mudança alguma no nosso lado.
2. **Jobs grandes nunca completavam (bug arquitetural):** desde a migração timer→queue
   (11/mar), o job inteiro roda numa execução única capada pelo `functionTimeout` de
   30 min (~teto de 55k linhas a ~1.900 linhas/min). O retry da fila não retomava: o
   lease `processing_worker_id` ficava preso após a morte do worker e o job era
   abandonado órfão até o cleanup marcar "expired".
3. **Re-submissões pagavam tudo de novo:** sem resume, cada nova tentativa recomeçava
   do chunk zero — as chamadas individuais ao Grok eram cobradas normalmente, mas o
   resultado era descartado no minuto 30. O loop re-submissão × preço 5–6× drenou os
   créditos do time.

## 3. Detecção

- **Como:** usuária reportou modal "ERROR a 99%" (10/jun, ~12h BRT). Investigação
  sistemática na mesma hora: status.json dos jobs no file share → 100% fallback;
  probe ao vivo na API xAI → 403 de billing; histórico completo do file share →
  nenhum job >28.646 linhas jamais completou na era queue.
- **Tempo até detecção:** ~12h após o esgotamento (sem alerta automático de billing
  ou de fallback — o hardening fallback≥95%→ERROR, deployado em 09/jun, foi o que
  tornou a falha visível em vez de silenciosa).

## 4. Mitigação

- Diagnóstico comunicado ao time no mesmo dia (recarga de créditos é ação de negócio).
- Orientação operacional imediata: não re-submeter bases >50k linhas até o fix.
- O 403 não gera custo — as tentativas pós-esgotamento não queimaram crédito adicional.

## 5. Action items

| # | Ação | Owner | Status |
|---|------|-------|--------|
| 1 | Recarregar créditos / definir spending limit no console.x.ai (team `236bd80b-…`) | Victor/PG | Pendente |
| 2 | Fix de resume: deadline cooperativo + lease heartbeat + cleanup por progresso (branch `fix/job-resume-creditos`) | Claude Code | **Concluído** (este PR) |
| 3 | Billing fail-fast: pre-flight + abort no 1º 403 com mensagem explícita | Claude Code | **Concluído** (este PR) |
| 4 | Erro real visível no frontend (modal) | Claude Code | **Concluído** (este PR) |
| 5 | Telemetria de tokens por job no status.json | Claude Code | **Concluído** (este PR) |
| 6 | Benchmark de modelo/effort/cache pós-recarga (`scripts/benchmark_models.py`) e decisão de `GROK_MODEL_NAME` | Victor + Claude | Pendente |
| 7 | Dedup de descrições idênticas antes do LLM (corte estimado 30–60% das chamadas) | A planejar (/feature) | Pendente |
| 8 | Confirmação de upload acima de N linhas com custo estimado (UX) | Time PG | Pendente |

## Lições

- **Slug de modelo não é contrato de preço.** Alias/redirect de provedor pode
  multiplicar a fatura sem quebrar nada. Pinar modelo explícito + monitorar usage.
- **Falha silenciosa custa caro duas vezes**: o sistema "funcionava" (cobrava) sem
  entregar. Visibilidade de erro e de custo precisam ser parte do pipeline, não
  esforço forense posterior.
- **Workaround manual vira incidente**: re-submeter era a única ação disponível ao
  usuário — e era exatamente a mais cara. O sistema deve retomar sozinho.
