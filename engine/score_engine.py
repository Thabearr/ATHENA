class ScoreEngine:
    """
    Collects weighted scores from every intelligence engine and
    produces one overall rating with a detailed explanation.
    """

    def __init__(self):
        self.scores = {}

    def add(self, category: str, value: float, reason: str = ""):
        self.scores[category] = {
            "value": value,
            "reason": reason
        }

    def get(self, category: str):
        return self.scores.get(category, {}).get("value", 0)

    def total(self):
        return sum(item["value"] for item in self.scores.values())

    def breakdown(self):
        return self.scores

    def clear(self):
        self.scores.clear()
