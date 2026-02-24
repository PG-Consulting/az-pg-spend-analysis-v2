"""TF-IDF cosine similarity retriever for few-shot examples from Knowledge Base."""
import logging
from typing import Optional
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

logger = logging.getLogger(__name__)


class KBRetriever:
    """Retrieves similar KB entries using TF-IDF cosine similarity for few-shot prompting."""

    def __init__(self, kb_entries: list):
        """
        Args:
            kb_entries: List of KB entry dicts with 'description_norm' field.
        """
        self.entries = kb_entries
        self.vectorizer = None
        self.matrix = None

        if kb_entries:
            try:
                descriptions = [
                    e.get("description_norm", e.get("description", "")).lower().strip()
                    for e in kb_entries
                ]
                self.vectorizer = TfidfVectorizer(
                    ngram_range=(1, 2),
                    max_features=5000,
                    min_df=1,
                    max_df=0.95,
                    sublinear_tf=True,
                    analyzer="word",
                )
                self.matrix = self.vectorizer.fit_transform(descriptions)
                logger.info(f"KBRetriever initialized with {len(kb_entries)} entries")
            except Exception as e:
                logger.warning(f"KBRetriever initialization failed: {e}")
                self.vectorizer = None
                self.matrix = None

    def _normalize(self, text: str) -> str:
        try:
            from src.preprocessing import normalize_text
            return normalize_text(text)
        except Exception:
            return str(text).lower().strip()

    def retrieve(self, description: str, top_k: int = 5) -> list:
        """Retrieve top-K similar KB entries for a given description."""
        if not self.vectorizer or self.matrix is None or len(self.entries) == 0:
            return []

        try:
            desc_norm = self._normalize(description)
            vec = self.vectorizer.transform([desc_norm])
            scores = cosine_similarity(vec, self.matrix)[0]
            top_indices = np.argsort(scores)[::-1][:top_k]

            results = []
            for idx in top_indices:
                if scores[idx] > 0.01:  # minimum similarity threshold
                    entry = dict(self.entries[idx])
                    entry["_similarity"] = float(scores[idx])
                    results.append(entry)
            return results
        except Exception as e:
            logger.warning(f"KBRetriever.retrieve failed: {e}")
            return []

    def retrieve_batch(self, descriptions: list, top_k: int = 5) -> list:
        """Efficient batch retrieval - one TF-IDF transform for all descriptions."""
        if not self.vectorizer or self.matrix is None or len(self.entries) == 0:
            return [[] for _ in descriptions]

        try:
            desc_norms = [self._normalize(d) for d in descriptions]
            vecs = self.vectorizer.transform(desc_norms)
            scores_matrix = cosine_similarity(vecs, self.matrix)

            results = []
            for scores in scores_matrix:
                top_indices = np.argsort(scores)[::-1][:top_k]
                item_results = []
                for idx in top_indices:
                    if scores[idx] > 0.01:
                        entry = dict(self.entries[idx])
                        entry["_similarity"] = float(scores[idx])
                        item_results.append(entry)
                results.append(item_results)
            return results
        except Exception as e:
            logger.warning(f"KBRetriever.retrieve_batch failed: {e}")
            return [[] for _ in descriptions]

    @staticmethod
    def select_representative_examples(kb_entries: list, max_k: int = 10) -> list:
        """Select diverse representative examples from KB for global few-shot prompting.
        Picks the highest-confidence entries, distributed across N4 categories."""
        if not kb_entries:
            return []

        # Group by N4, pick best per N4 (highest confidence first)
        by_n4 = {}
        for e in sorted(kb_entries, key=lambda x: x.get("confidence", 0), reverse=True):
            n4 = e.get("N4", "")
            if n4 not in by_n4:
                by_n4[n4] = e

        # Take top max_k by confidence, prioritising consultant corrections
        candidates = list(by_n4.values())
        candidates.sort(
            key=lambda x: (x.get("source") == "consultant_correction", x.get("confidence", 0)),
            reverse=True,
        )
        return candidates[:max_k]

    @staticmethod
    def select_enriched_examples(batch_retrieve_results: list, max_examples: int = 20) -> list:
        """Select enriched examples from per-item retrieval results for a batch.

        Aggregates all matches from all items, deduplicates by description_norm,
        and prioritizes: high similarity > consultant_correction > high confidence > N4 diversity.

        Args:
            batch_retrieve_results: List of lists (one per item) of match dicts with _similarity.
            max_examples: Maximum number of enriched examples to return.

        Returns:
            List of KB entry dicts (without _similarity key), ordered by relevance.
        """
        if not batch_retrieve_results:
            return []

        # Aggregate all matches, keeping the best similarity per description_norm
        seen = {}
        for item_matches in batch_retrieve_results:
            if not item_matches:
                continue
            for match in item_matches:
                key = match.get("description_norm", match.get("description", ""))
                if not key:
                    continue
                existing = seen.get(key)
                if existing is None or match.get("_similarity", 0) > existing.get("_similarity", 0):
                    seen[key] = dict(match)

        if not seen:
            return []

        # Sort by: consultant_correction first, then similarity desc, then confidence desc
        candidates = list(seen.values())
        candidates.sort(
            key=lambda x: (
                x.get("source") == "consultant_correction",
                x.get("_similarity", 0),
                x.get("confidence", 0),
            ),
            reverse=True,
        )

        # Ensure N4 diversity: limit to max 3 entries per N4
        result = []
        n4_counts = {}
        for c in candidates:
            if len(result) >= max_examples:
                break
            n4 = c.get("N4", "")
            count = n4_counts.get(n4, 0)
            if count >= 3:
                continue
            n4_counts[n4] = count + 1
            # Remove internal _similarity key before returning
            entry = {k: v for k, v in c.items() if k != "_similarity"}
            result.append(entry)

        return result
