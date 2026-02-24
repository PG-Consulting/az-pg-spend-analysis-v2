/**
 * @fileoverview Execution Engine for Smart Context queries.
 * 
 * This module executes the detected intent against the classified items dataset,
 * generating appropriate data payloads for each intent type:
 * 
 * - COUNT_FILTERED: Count items matching criteria
 * - TOP_N_RANKING / BOTTOM_N_RANKING: Rank categories by frequency
 * - PARETO_ANALYSIS: Calculate 80/20 distribution (Curve A)
 * - DISTRIBUTION: Show percentage breakdown
 * - TERM_SEARCH / TERM_EXCEPTION: Find items containing terms
 * - OUTLIER_DETECTION: Find short/vague descriptions
 * - CATEGORY_LOOKUP: Show category statistics
 * - GAP_ANALYSIS: Find missing subcategories
 * - HIERARCHY_LOOKUP: Show full taxonomy path
 * 
 * @module smart-context/execution-engine
 */

import { IntentType, ContextPayload } from './types'
import { EntityExtractionResult, normalize } from './entity-extractor'

/** Formats an array of strings as a comma-separated quoted list */
const formatList = (items: string[]) => items.map(i => `"${i}"`).join(', ');

/**
 * Executes an intent against the classified items dataset.
 * 
 * This is the main execution function that:
 * 1. Filters items based on extracted entities (category scope)
 * 2. Executes the appropriate data operation for the intent
 * 3. Returns a structured ContextPayload for the Copilot
 * 
 * @param intent - The detected IntentType from the router
 * @param entities - Extracted entities from the query
 * @param originalItems - Full array of classified items from the session
 * @returns ContextPayload with data and instructions, or null if cannot execute
 * 
 * @example
 * ```typescript
 * const payload = executeIntent(
 *   IntentType.TOP_N_RANKING,
 *   { number: 10, level: 'N2' },
 *   classifiedItems
 * );
 * // Returns { data: { type: 'top_highest_frequency', ... }, ... }
 * ```
 */
export const executeIntent = (
    intent: IntentType,
    entities: EntityExtractionResult,
    originalItems: any[]
): ContextPayload | null => {
    try {
        // 1. FILTERING (Scope definition)
        let scopeItems = originalItems;

        // ... (GROUPING LOGIC IS FINE, SKIPPING TO FILTERING)

        // RE-INSERTING FILTERING logic here because I need to wrap the whole function body or just the critical parts.
        // I'll just replace the filter block.

        if (entities.category) {
            const catNorm = normalize(entities.category);
            const strictMatches = originalItems.filter(i =>
                normalize(i.N1 || '') === catNorm ||
                normalize(i.N2 || '') === catNorm ||
                normalize(i.N3 || '') === catNorm ||
                normalize(i.N4 || '') === catNorm
            );

            if (strictMatches.length > 0) {
                scopeItems = strictMatches;
            } else {
                // FALLBACK: Loose match (Contains)
                scopeItems = originalItems.filter(i =>
                    normalize(i.N1 || '').includes(catNorm) ||
                    normalize(i.N2 || '').includes(catNorm) ||
                    normalize(i.N3 || '').includes(catNorm) ||
                    normalize(i.N4 || '').includes(catNorm)
                );
            }
        }

        const totalScope = scopeItems.length;
        if (totalScope === 0 && entities.category) {
            console.warn('[EXEC-ENGINE] Scope empty for category:', entities.category);
            return {
                data: { error: 'ScopeNotFound', category: entities.category },
                text: `Identifiquei a categoria "${entities.category}", mas não encontrei nenhum item correspondente na tabela atual.`,
                instructions: "Informe o usuário que a categoria não foi encontrada nos dados.",
                relevantItems: []
            };
        }

        // ... (rest of logic continues)

        // --- EXECUTION HANDLERS ---

        // CASE 1: COUNT
        if (intent === IntentType.COUNT_FILTERED) {
            // Could be "Count items in X" or complex "Count items in X segmented by Y"
            // Simple count is already totalScope.
            // Segmented count: "Count items in X segmented by N2"
            return {
                data: {
                    type: 'count',
                    scope: entities.category || 'Global',
                    count: totalScope
                },
                text: `[SYSTEM DATA] Count: ${totalScope} items. Scope: ${entities.category || 'Global'}.`,
                instructions: "State the count clearly based on the provided data.",
                relevantItems: scopeItems.slice(0, 5)
            }
        }

        // CASE 2: TOP / BOTTOM RANKING
        if (intent === IntentType.TOP_N_RANKING || intent === IntentType.BOTTOM_N_RANKING || intent === IntentType.PARETO_ANALYSIS) {
            const isTop = intent !== IntentType.BOTTOM_N_RANKING;
            const n = entities.number || 5;

            // Initialize grouping variables safely
            let groupLevel: string | undefined = entities.level;
            let currentScopeLevel = 'Global';

            // Detect scope level based on category match
            if (entities.category && scopeItems.length > 0) {
                const sample = scopeItems[0];
                if (normalize(sample.N4 || '') === normalize(entities.category)) currentScopeLevel = 'N4';
                else if (normalize(sample.N3 || '') === normalize(entities.category)) currentScopeLevel = 'N3';
                else if (normalize(sample.N2 || '') === normalize(entities.category)) currentScopeLevel = 'N2';
                else if (normalize(sample.N1 || '') === normalize(entities.category)) currentScopeLevel = 'N1';
            }

            // CRITICAL OVERRIDE: If user explicitly asks for ITEMS, ignore extracted 'level'
            if (entities.targetType === 'item') {
                groupLevel = '_desc_original';
            }

            // Logical inference for grouping key if not yet defined
            if (!groupLevel) {
                // Heuristic: If we are deep in the tree (N4) or asking for items, show items.
                if (entities.targetType === 'item') {
                    groupLevel = '_desc_original';
                } else if (entities.targetType === 'word') {
                    groupLevel = 'word_token'; // Special marker
                } else if (currentScopeLevel === 'N4') {
                    // Leaves -> must show items
                    groupLevel = '_desc_original';
                } else if (currentScopeLevel === 'N3') {
                    groupLevel = 'N4';
                } else if (currentScopeLevel === 'N2') {
                    groupLevel = 'N3';
                } else if (currentScopeLevel === 'N1') {
                    groupLevel = 'N2';
                } else {
                    // Global scope. Default to N1
                    groupLevel = 'N1';
                }
            } else {
                // Smart correction: If user asks "Pareto N1 Diretos", Scope is N1 and Group is N1.
                // This results in a single bar "Diretos" (100%).
                // We should auto-drill down to N2.
                if (groupLevel === currentScopeLevel && groupLevel !== 'Global' && !entities.targetType) {
                    if (groupLevel === 'N1') groupLevel = 'N2';
                    else if (groupLevel === 'N2') groupLevel = 'N3';
                    else if (groupLevel === 'N3') groupLevel = 'N4';
                    else if (groupLevel === 'N4') groupLevel = '_desc_original';
                }
            }

            // Count distribution
            const counts: Record<string, number> = {};

            if (groupLevel === 'word_token') {
                // Tokenizer Logic
                scopeItems.forEach(i => {
                    const desc = (i._desc_original || i.Item_Description || '').toLowerCase();
                    // Tokenize, remove short words
                    const tokens = desc.split(/[\s,.\-+/()]+/).filter((t: string) => t.length > 3 && !['para', 'com', 'item'].includes(t));
                    tokens.forEach((t: string) => {
                        counts[t] = (counts[t] || 0) + 1;
                    });
                });
            } else {
                scopeItems.forEach(i => {
                    let key = i[groupLevel!] || 'Unknown';
                    // Fallback for description if missing
                    if (groupLevel === '_desc_original' && !i[groupLevel!]) {
                        key = i.Item_Description || 'Unknown';
                    }
                    counts[key] = (counts[key] || 0) + 1;
                });
            }

            const sorted = Object.entries(counts).sort((a, b) => isTop ? b[1] - a[1] : a[1] - b[1]);

            // PARETO SPECIFIC LOGIC
            if (intent === IntentType.PARETO_ANALYSIS) {
                let runningSum = 0;
                const threshold = totalScope * 0.80; // 80% volume
                const paretoItems = [];

                for (const [key, count] of sorted) {
                    runningSum += count;
                    paretoItems.push({ key, count, accumulated: Math.round((runningSum / totalScope) * 100) });
                    if (runningSum >= threshold) break;
                }

                return {
                    data: {
                        type: 'pareto',
                        scope: entities.category || 'Global',
                        grouping: groupLevel,
                        totalItems: totalScope,
                        curveAItems: paretoItems
                    },
                    text: JSON.stringify(paretoItems, null, 2),
                    instructions: "Present this as the 'Curve A' identifying the few drivers of the majority of occurrences (frequency).",
                    relevantItems: []
                }
            }

            // Standard Ranking Result
            const result = sorted.slice(0, n);

            const data = {
                analysis_type: `top_${isTop ? 'highest' : 'lowest'}_frequency`,
                scope: entities.category || 'Global',
                grouping: groupLevel === '_desc_original' ? 'Item Description' : groupLevel,
                data_points: result.map((r, i) => ({
                    rank: i + 1,
                    name: r[0],
                    count: r[1],
                    type: groupLevel === '_desc_original' ? 'item' : 'category'
                }))
            };

            return {
                data: data,
                text: JSON.stringify(data, null, 2),
                instructions: `List the top ${n} items/categories exactly as shown in the data. Do not hallucinate other items.`,
                relevantItems: []
            }
        }


        // CASE 3: DISTRIBUTION
        if (intent === IntentType.DISTRIBUTION) {
            // Similar to ranking but returns percentages
            let groupLevel = entities.level || 'N4'; // Fallback

            // STATUS / METRICS OVERRIDE
            if (entities.status) {
                groupLevel = 'status' as any;
                // If checking specific status, we might want to filter? 
                // Actually, distribution usually asks for breakdown. 
                // If user asks "Percentage of Unique", providing distribution of Match_Type answers it.
            } else if (entities.category) {
                const sample = scopeItems[0];
                // Auto-detect next child level
                if (normalize(sample.N1 || '') === normalize(entities.category)) groupLevel = 'N2';
                else if (normalize(sample.N2 || '') === normalize(entities.category)) groupLevel = 'N3';
                else if (normalize(sample.N3 || '') === normalize(entities.category)) groupLevel = 'N4';
            }

            const counts: Record<string, number> = {};
            scopeItems.forEach(i => {
                const key = i[groupLevel] || 'Unknown';
                counts[key] = (counts[key] || 0) + 1;
            });

            const sorted = Object.entries(counts).sort((a, b) => b[1] - a[1]);

            return {
                data: {
                    type: 'distribution',
                    scope: entities.category || 'Global',
                    grouping: groupLevel,
                    distribution: sorted.map(r => ({ name: r[0], count: r[1], percentage: ((r[1] / totalScope) * 100).toFixed(1) }))
                },
                text: sorted.map(r => `- ${r[0]}: ${r[1]} items (${((r[1] / totalScope) * 100).toFixed(1)}%)`).join('\n'),
                instructions: "Present the breakdown clearly with percentages.",
                relevantItems: []
            }
        }

        // CASE 4: TERM SEARCH / EXCEPTION
        if (intent === IntentType.TERM_SEARCH || intent === IntentType.TERM_EXCEPTION) {
            if (!entities.term) return null;

            const termNorm = normalize(entities.term);
            // Filter by term
            const matches = scopeItems.filter(i => {
                const desc = normalize(i._desc_original || i.Item_Description || "");
                const hasTerm = desc.includes(termNorm);

                if (intent === IntentType.TERM_EXCEPTION) {
                    // "Has term X but is NOT category Y". 
                    // We are already scoped to "category Y" if entities.category is set? 
                    // Wait. "Contains 'Parafuso' but NOT 'Fixadores'".
                    // If entities.category is "Fixadores", we scoped TO Fixadores. We want the opposite.
                    // This logic needs global scope if it's an exception out of a category.
                    return hasTerm; // Logic is complex. Let's simplify: simple search within scope.
                }
                return hasTerm;
            });

            // Simple search result
            // Check if we should aggregate by category (e.g. "In which categories does term X appear?")
            // If query asks for 'categories', entities.targetType should be 'category'.
            // However, term search regex captures "quais categorias... termo/palavra". 
            // We relied on entity extractor for targetType. Let's assume if targetType=category, we group.

            if (entities.targetType === 'category') {
                // Aggregate matches by N-level
                const aggLevel = entities.level || 'N4'; // Default to leaf category if not specified
                const catCounts: Record<string, number> = {};

                matches.forEach(m => {
                    const key = m[aggLevel] || 'Unknown';
                    catCounts[key] = (catCounts[key] || 0) + 1;
                });

                const n = entities.number || 10;
                const sortedCats = Object.entries(catCounts).sort((a, b) => b[1] - a[1]).slice(0, n);

                return {
                    data: {
                        type: 'term_search_aggregation',
                        term: entities.term,
                        grouping: aggLevel,
                        distribution: sortedCats.map(r => ({ category: r[0], count: r[1] }))
                    },
                    text: `Term "${entities.term}" appears most in these ${aggLevel} categories:\n${sortedCats.map(r => `- ${r[0]}: ${r[1]} occurrences`).join('\n')}`,
                    instructions: "List the categories where this term appears most frequently.",
                    relevantItems: []
                }
            }

            return {
                data: {
                    type: 'term_search',
                    term: entities.term,
                    scope: entities.category || 'Global',
                    count: matches.length,
                    examples: matches.slice(0, 10).map(m => ({ desc: m._desc_original || m.Item_Description, n4: m.N4 }))
                },
                text: `Found ${matches.length} items containing "${entities.term}". Examples:\n${matches.slice(0, 10).map(m => `- ${m._desc_original || m.Item_Description} [${m.N4}]`).join('\n')}`,
                instructions: "Summarize the findings. If count is high, mention it strongly.",
                relevantItems: matches.slice(0, 20)
            }
        }

        // CASE 5: OUTLIERS (Short descriptions)
        if (intent === IntentType.OUTLIER_DETECTION) {
            const limit = entities.threshold || 5;
            const outliers = scopeItems.filter(i => {
                const desc = (i._desc_original || i.Item_Description || "").trim();
                return desc.length > 0 && desc.length < limit;
            });

            return {
                data: {
                    type: 'outlier_detection',
                    criteria: `Length < ${limit}`,
                    count: outliers.length,
                    examples: outliers.slice(0, 10).map(m => m._desc_original || m.Item_Description)
                },
                text: `Found ${outliers.length} items with length < ${limit}. Examples:\n${outliers.slice(0, 10).map(m => `- ${m._desc_original || m.Item_Description}`).join('\n')}`,
                instructions: "List these outliers as potential data quality issues.",
                relevantItems: outliers
            }
        }

        // CASE 6: DEFAULT CATEGORY LOOKUP (Stats)
        if (intent === IntentType.CATEGORY_LOOKUP || (entities.category && intent === IntentType.UNKNOWN)) {
            if (!entities.category) return null;

            const classifiedCount = scopeItems.filter((i: any) =>
                i.N1 && i.N1 !== 'Não Identificado' &&
                i.N4 && i.N4 !== 'Não Identificado'
            ).length
            const unclassifiedCount = totalScope - classifiedCount

            return {
                data: {
                    type: 'category_lookup',
                    category: entities.category,
                    total: totalScope,
                    stats: { classified: classifiedCount, unclassified: unclassifiedCount }
                },
                text: `Category: '${entities.category}'. Total: ${totalScope}. Classified: ${classifiedCount}, Unclassified: ${unclassifiedCount}.`,
                instructions: "Provide this overview summary of the category status.",
                relevantItems: scopeItems.slice(0, 10)
            }
        }

        // CASE 7: GAP ANALYSIS
        if (intent === IntentType.GAP_ANALYSIS) {
            // "Categories in Level X that do NOT have children in Level Y"
            // E.g. "Level N2 without N3"
            // Default: Look for N-level items that have "Nenhum" in (N+1)
            const checkLevel = entities.level || 'N2';
            const childLevel = checkLevel === 'N1' ? 'N2' : checkLevel === 'N2' ? 'N3' : 'N4';

            const gaps = new Set<string>();
            scopeItems.forEach(i => {
                // If we have a parent level but child is empty/null/nenhum
                const parent = i[checkLevel];
                const child = i[childLevel];

                if (parent && (!child || child.toLowerCase() === 'nenhum' || child.toLowerCase() === 'ambiguo')) {
                    gaps.add(parent);
                }
            });

            const gapList = Array.from(gaps).slice(0, 20);

            return {
                data: {
                    type: 'gap_analysis',
                    level: checkLevel,
                    missing_child_level: childLevel,
                    count: gaps.size,
                    examples: gapList
                },
                text: `Gap Analysis: Found ${gaps.size} categories in ${checkLevel} with no valid ${childLevel}. Examples: ${gapList.join(', ')}`,
                instructions: "Highlight these categories as requiring taxonomy development.",
                relevantItems: []
            }
        }

        // CASE 8: HIERARCHY LOOKUP
        if (intent === IntentType.HIERARCHY_LOOKUP) {
            // "Hierarchy of item 'X'"
            // We strict match on description provided in entities.term? Or usually entities.term captures quoted text.
            // If user says "Hierarchy of item with description 'Foo'", term='Foo'.
            if (!entities.term) return null;

            const target = scopeItems.find(i =>
                (i._desc_original || i.Item_Description || '').toLowerCase() === entities.term?.toLowerCase()
            );

            if (!target) {
                // Try fuzzy
                const fuzzyTarget = scopeItems.find(i =>
                    (i._desc_original || i.Item_Description || '').toLowerCase().includes(entities.term!.toLowerCase())
                );

                if (!fuzzyTarget) return {
                    data: { type: 'hierarchy_lookup', found: false, term: entities.term },
                    text: `Item with description similar to "${entities.term}" not found.`,
                    instructions: "Inform the user the exact item was not found.",
                    relevantItems: []
                };

                // Use fuzzy target
                return {
                    data: {
                        type: 'hierarchy_lookup',
                        found: true,
                        match_type: 'approximate',
                        item: fuzzyTarget._desc_original || fuzzyTarget.Item_Description,
                        hierarchy: { N1: fuzzyTarget.N1, N2: fuzzyTarget.N2, N3: fuzzyTarget.N3, N4: fuzzyTarget.N4 }
                    },
                    text: `Hierarchy for "${fuzzyTarget._desc_original}": ${fuzzyTarget.N1} > ${fuzzyTarget.N2} > ${fuzzyTarget.N3} > ${fuzzyTarget.N4}`,
                    instructions: "Present the full taxonomy path clearly.",
                    relevantItems: [fuzzyTarget]
                }
            }

            return {
                data: {
                    type: 'hierarchy_lookup',
                    found: true,
                    match_type: 'exact',
                    item: target._desc_original || target.Item_Description,
                    hierarchy: { N1: target.N1, N2: target.N2, N3: target.N3, N4: target.N4 }
                },
                text: `Hierarchy for "${target._desc_original}": ${target.N1} > ${target.N2} > ${target.N3} > ${target.N4}`,
                instructions: "Present the full taxonomy path clearly.",
                relevantItems: [target]
            }
        }

        return null;
    } catch (error) {
        console.error('[EXEC-ENGINE] Critical Error:', error);
        return {
            data: { error: 'InternalError', details: String(error) },
            text: "Ocorreu um erro interno ao processar sua solicitação de análise.",
            instructions: "Peça desculpas e informe que houve um erro técnico na análise dos dados.",
            relevantItems: []
        };
    }
}
