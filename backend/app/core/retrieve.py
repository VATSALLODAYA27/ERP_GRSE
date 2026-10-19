"""Text search for Navik: finds the few passages that answer a question, so the model reads a page, not the book.

Plain keyword scoring (BM25, the method most search engines started from): a passage scores higher when it
shares more of the question's words, when those words are rare across all passages, and when the passage is
short. No embeddings and no extra libraries, so it runs instantly on any machine.
"""
import math
import re
from collections import Counter

# Drawing and work-order numbers such as GRSE-H-102 and WO-24018 stay one word.
WORD = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
STOP = set("a an and are as at be by can do does for from has have how i in is it its me my of on or the this to was what when where which who why will with you your".split())


def words(text: str) -> list:
    found = (w for w in WORD.findall(text.lower()) if w not in STOP)
    return [w[:-1] if len(w) > 3 and w.endswith("s") and not w.endswith("ss") else w for w in found]  # "orders" finds "order"


class Index:
    def __init__(self, passages: list):
        self.passages = passages
        self.counts = [Counter(words(p)) for p in passages]
        self.lengths = [sum(c.values()) for c in self.counts]
        self.average = sum(self.lengths) / len(passages) if passages else 1
        holding = Counter(w for c in self.counts for w in c)
        n = len(passages)
        self.idf = {w: math.log(1 + (n - k + 0.5) / (k + 0.5)) for w, k in holding.items()}

    def search(self, query: str, k: int, ranked: bool = False) -> list:
        """The k passages that best match, best first if `ranked`, else in their original order (so a list keeps
        its sequence). A passage that shares no word with the query is never returned."""
        terms = set(words(query))
        scores = []
        for i, (counts, length) in enumerate(zip(self.counts, self.lengths)):
            score = sum(self.idf[t] * counts[t] * 2.5 / (counts[t] + 1.5 * (0.25 + 0.75 * length / self.average)) for t in terms if t in counts)
            if score > 0:
                scores.append((score, i))
        best = [i for _, i in sorted(scores, reverse=True)[:k]]
        return [self.passages[i] for i in (best if ranked else sorted(best))]


def passages(text: str) -> list:
    """One passage per line, each carrying the heading it sits under, so "Warn" under RELEASE GATE stays findable by "gate"."""
    heading, found = "", []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.isupper() or line.endswith(")") and line.split("(")[0].strip().isupper():
            heading = line
            continue
        found.append(f"{heading}: {line}" if heading else line)
    return found
