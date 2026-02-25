"""
Hierarchy Validator - Pós-processamento genérico de validação de hierarquia.

Valida e corrige resultados de classificação LLM contra a hierarquia customizada
do cliente. Usa cascata de estratégias: exact match → level shift detection →
partial fuzzy → N4 reverse lookup → no match (conservador).

100% genérico - nenhuma lógica específica de OEM ou qualquer categoria.
"""

import logging
from typing import Dict, List, Optional, Tuple, Set, Union
from collections import defaultdict
from difflib import get_close_matches


class HierarchyLookup:
    """Pré-computa lookups a partir da hierarquia (list of dicts) para validação O(1)."""

    def __init__(self, hierarchy: Union[List[Dict], Dict]):
        entries = hierarchy.values() if isinstance(hierarchy, dict) else hierarchy

        self.valid_paths: Set[Tuple[str, str, str, str]] = set()
        self.valid_n1s: Set[str] = set()
        self.valid_n2s: Set[str] = set()
        self.valid_n3s: Set[str] = set()
        self.valid_n4s: Set[str] = set()

        self.n2_to_n1: Dict[str, Set[str]] = defaultdict(set)
        self.n3_to_n1n2: Dict[str, Set[Tuple[str, str]]] = defaultdict(set)
        self.n4_to_paths: Dict[str, List[Tuple[str, str, str]]] = defaultdict(list)
        self.n1n2_to_n3s: Dict[Tuple[str, str], Set[str]] = defaultdict(set)
        self.n1n2n3_to_n4s: Dict[Tuple[str, str, str], Set[str]] = defaultdict(set)
        self.canonical_case: Dict[str, str] = {}

        for h in entries:
            n1 = (h.get('N1') or '').strip()
            n2 = (h.get('N2') or '').strip()
            n3 = (h.get('N3') or '').strip()
            n4 = (h.get('N4') or '').strip()
            if not n4:
                continue

            n1l, n2l, n3l, n4l = n1.lower(), n2.lower(), n3.lower(), n4.lower()

            self.valid_paths.add((n1l, n2l, n3l, n4l))
            self.valid_n1s.add(n1l)
            self.valid_n2s.add(n2l)
            self.valid_n3s.add(n3l)
            self.valid_n4s.add(n4l)

            self.n2_to_n1[n2l].add(n1l)
            self.n3_to_n1n2[n3l].add((n1l, n2l))
            self.n4_to_paths[n4l].append((n1l, n2l, n3l))
            self.n1n2_to_n3s[(n1l, n2l)].add(n3l)
            self.n1n2n3_to_n4s[(n1l, n2l, n3l)].add(n4l)

            for val in (n1, n2, n3, n4):
                self.canonical_case[val.lower()] = val

    def get_canonical(self, value: str) -> str:
        """Retorna o case original da hierarquia para um valor normalizado."""
        return self.canonical_case.get(value.lower().strip(), value)


def _fuzzy_match(value: str, candidates: Set[str], cutoff: float = 0.6, cache: Optional[Dict] = None) -> Optional[str]:
    """Fuzzy match de um valor contra candidatos. Usa cache se fornecido."""
    if cache is not None:
        cache_key = (value, frozenset(candidates))
        if cache_key in cache:
            return cache[cache_key]

    matches = get_close_matches(value, candidates, n=1, cutoff=cutoff)
    result = matches[0] if matches else None

    if cache is not None:
        cache[cache_key] = result
    return result


def validate_and_correct(
    chunk_results: List[Dict],
    hierarchy: Union[List[Dict], Dict],
    lookup: Optional[HierarchyLookup] = None
) -> Tuple[List[Dict], Dict[str, int]]:
    """
    Valida e corrige resultados de classificação contra a hierarquia customizada.

    Cascata de validação (ordem):
      A. Exact path match
      B. Level shift detection (genérico)
      C. Partial path + fuzzy matching (scoped)
      D. N4-based reverse lookup
      E. No match (conservador - mantém resultado do LLM)

    Args:
        chunk_results: Lista de dicts com N1, N2, N3, N4, status, source
        hierarchy: Hierarquia customizada (list of dicts ou dict)
        lookup: HierarchyLookup pré-construído (se None, constrói internamente)

    Returns:
        Tuple de (chunk_results corrigidos, stats dict)
    """
    if lookup is None:
        lookup = HierarchyLookup(hierarchy)

    stats = {
        "exact_match": 0,
        "level_shift": 0,
        "partial_fuzzy": 0,
        "n4_reverse": 0,
        "no_match": 0,
        "skipped": 0,
    }

    fuzzy_cache: Dict = {}

    for res in chunk_results:
        # Só validar itens classificados pelo LLM
        source = res.get("source", res.get("classification_source", ""))
        if "LLM" not in source:
            stats["skipped"] += 1
            continue

        n1 = (res.get("N1") or "").strip()
        n2 = (res.get("N2") or "").strip()
        n3 = (res.get("N3") or "").strip()
        n4 = (res.get("N4") or "").strip()

        # Pular itens não classificados
        if not n1 or n1.lower() in ("não identificado", "nao identificado"):
            stats["skipped"] += 1
            continue

        n1l, n2l, n3l, n4l = n1.lower(), n2.lower(), n3.lower(), n4.lower()

        # Step A: Exact path match
        if (n1l, n2l, n3l, n4l) in lookup.valid_paths:
            _apply_canonical(res, n1l, n2l, n3l, n4l, lookup)
            stats["exact_match"] += 1
            continue

        # Step B: Level shift detection
        # Se N1 retornado NÃO é N1 válido, MAS É um N2 válido → shift +1
        if n1l not in lookup.valid_n1s and n1l in lookup.valid_n2s:
            # Tentar shift: real_N1 = lookup(N2→N1), real_N2=returned_N1, real_N3=returned_N2, real_N4=returned_N3
            possible_n1s = lookup.n2_to_n1.get(n1l, set())
            shifted = False
            for real_n1 in possible_n1s:
                shifted_path = (real_n1, n1l, n2l, n3l)
                if shifted_path in lookup.valid_paths:
                    _apply_canonical(res, real_n1, n1l, n2l, n3l, lookup)
                    res["classification_source"] = source + " [shift-corrected]"
                    stats["level_shift"] += 1
                    shifted = True
                    break
                # Tentar fuzzy no N4 shifted (n3l como N4)
                valid_n4s = lookup.n1n2n3_to_n4s.get((real_n1, n1l, n2l), set())
                if valid_n4s:
                    fuzzy_n4 = _fuzzy_match(n3l, valid_n4s, cutoff=0.6, cache=fuzzy_cache)
                    if fuzzy_n4:
                        _apply_canonical(res, real_n1, n1l, n2l, fuzzy_n4, lookup)
                        res["classification_source"] = source + " [shift-corrected]"
                        stats["level_shift"] += 1
                        shifted = True
                        break
            if shifted:
                continue

        # Step C: Partial path + fuzzy matching (scoped)
        corrected_c = _try_partial_fuzzy(res, n1l, n2l, n3l, n4l, lookup, fuzzy_cache, source)
        if corrected_c:
            stats["partial_fuzzy"] += 1
            continue

        # Step D: N4-based reverse lookup
        corrected_d = _try_n4_reverse(res, n1l, n2l, n3l, n4l, lookup, fuzzy_cache, source)
        if corrected_d:
            stats["n4_reverse"] += 1
            continue

        # Step E: No match - zerar tudo para "Não Identificado" + status "Nenhum"
        res["N1"] = "Não Identificado"
        res["N2"] = "Não Identificado"
        res["N3"] = "Não Identificado"
        res["N4"] = "Não Identificado"
        res["status"] = "Nenhum"
        res["classification_source"] = source + " [no-match]"
        stats["no_match"] += 1

    return chunk_results, stats


def _apply_canonical(res: Dict, n1l: str, n2l: str, n3l: str, n4l: str, lookup: HierarchyLookup):
    """Aplica os valores com case canônico da hierarquia."""
    res["N1"] = lookup.get_canonical(n1l)
    res["N2"] = lookup.get_canonical(n2l)
    res["N3"] = lookup.get_canonical(n3l)
    res["N4"] = lookup.get_canonical(n4l)


def _try_partial_fuzzy(
    res: Dict, n1l: str, n2l: str, n3l: str, n4l: str,
    lookup: HierarchyLookup, cache: Dict, source: str
) -> bool:
    """Step C: N1 e N2 válidos, fuzzy match N3 e N4 dentro do branch correto."""
    if n1l not in lookup.valid_n1s or n2l not in lookup.valid_n2s:
        return False

    # Verificar se (N1,N2) é um par válido
    valid_n3s = lookup.n1n2_to_n3s.get((n1l, n2l))
    if not valid_n3s:
        return False

    # N3 exato?
    target_n3 = n3l if n3l in valid_n3s else None

    # Fuzzy N3 scoped
    if target_n3 is None:
        target_n3 = _fuzzy_match(n3l, valid_n3s, cutoff=0.6, cache=cache)
    if target_n3 is None:
        return False

    # N4 exato ou fuzzy dentro do branch (N1,N2,N3)
    valid_n4s = lookup.n1n2n3_to_n4s.get((n1l, n2l, target_n3), set())
    if not valid_n4s:
        return False

    target_n4 = n4l if n4l in valid_n4s else None
    if target_n4 is None:
        target_n4 = _fuzzy_match(n4l, valid_n4s, cutoff=0.6, cache=cache)
    if target_n4 is None:
        # Se só existe 1 N4 neste N3, usar automaticamente
        if len(valid_n4s) == 1:
            target_n4 = next(iter(valid_n4s))
        else:
            return False

    _apply_canonical(res, n1l, n2l, target_n3, target_n4, lookup)
    res["classification_source"] = source + " [fuzzy-corrected]"
    return True


def _try_n4_reverse(
    res: Dict, n1l: str, n2l: str, n3l: str, n4l: str,
    lookup: HierarchyLookup, cache: Dict, source: str
) -> bool:
    """Step D: Usa N4 para encontrar o path correto via reverse lookup."""
    # Tentar N4 exato
    paths = lookup.n4_to_paths.get(n4l)

    # Tentar fuzzy N4 global se exato falhou
    if not paths:
        fuzzy_n4 = _fuzzy_match(n4l, lookup.valid_n4s, cutoff=0.6, cache=cache)
        if fuzzy_n4:
            paths = lookup.n4_to_paths.get(fuzzy_n4)
            n4l = fuzzy_n4

    if not paths:
        return False

    if len(paths) == 1:
        # N4 único na hierarquia → usar diretamente
        p_n1, p_n2, p_n3 = paths[0]
        _apply_canonical(res, p_n1, p_n2, p_n3, n4l, lookup)
        res["classification_source"] = source + " [n4-reverse]"
        return True

    # Múltiplos paths → pontuar por overlap com N1/N2/N3 do LLM
    best_score = -1
    best_path = None
    tied = False
    for p_n1, p_n2, p_n3 in paths:
        score = 0
        if p_n1 == n1l:
            score += 3
        if p_n2 == n2l:
            score += 2
        if p_n3 == n3l:
            score += 1
        if score > best_score:
            best_score = score
            best_path = (p_n1, p_n2, p_n3)
            tied = False
        elif score == best_score:
            tied = True

    # Se houve empate, não temos info suficiente para desambiguar → rejeitar
    if tied or not best_path or best_score == 0:
        return False

    _apply_canonical(res, best_path[0], best_path[1], best_path[2], n4l, lookup)
    res["classification_source"] = source + " [n4-reverse]"
    return True
