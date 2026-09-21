from engine.analyzer import Analyzer
from engine.probability_engine import ProbabilityEngine
from engine.risk_engine import RiskEngine
from engine.reliability_engine import ReliabilityEngine
from services import main_canonical_prediction_adapter as _canonical_presentation


class PredictionService:

    def __init__(self):

        self.analyzer = Analyzer()
        self.probability = ProbabilityEngine()
        self.risk = RiskEngine()
        self.reliability = ReliabilityEngine()

    def predict(self, fixture, *, router_decision=None):

        prediction = self.analyzer.analyze(fixture)

        prediction = self.probability.calculate(prediction)

        prediction = self.risk.evaluate(prediction)

        prediction = self.reliability.evaluate(prediction)

        return _canonical_presentation.project_canonical_router_decision(
            prediction,
            router_decision,
        )
