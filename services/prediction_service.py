from engine.analyzer import Analyzer
from engine.probability_engine import ProbabilityEngine
from engine.risk_engine import RiskEngine
from engine.reliability_engine import ReliabilityEngine
from engine.market_selector import MarketSelector


class PredictionService:

    def __init__(self):

        self.analyzer = Analyzer()
        self.probability = ProbabilityEngine()
        self.risk = RiskEngine()
        self.reliability = ReliabilityEngine()
        self.market = MarketSelector()

    def predict(self, fixture):

        prediction = self.analyzer.analyze(fixture)

        prediction = self.probability.calculate(prediction)

        prediction = self.risk.evaluate(prediction)

        prediction = self.reliability.evaluate(prediction)

        prediction = self.market.select(prediction)

        return prediction
