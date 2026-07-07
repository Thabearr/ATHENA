import logging

logger = logging.getLogger("athena.weather_engine")

class WeatherEngine:
    def __init__(self):
        pass

    def assess_tactical_weather_impact(self, weather_data: dict, home_style: str = "neutral", away_style: str = "neutral") -> dict:
        """
        Analyzes fixture climate metrics (rain, snow, high winds) and evaluates 
        how severely they degrade specific team playing styles.
        Returns performance modifiers where 1.0 represents nominal conditions.
        """
        home_modifier = 1.0
        away_modifier = 1.0
        
        condition = weather_data.get("condition", "clear").lower()
        wind_speed = weather_data.get("wind_speed", 0.0)  # Measured in km/h
        temp = weather_data.get("temp", 20.0)             # Measured in Celsius

        # 1. Precipitation Interception (Slick/Waterlogged Turf)
        if any(keyword in condition for keyword in ["rain", "shower", "snow", "storm"]):
            if home_style == "passing":
                home_modifier -= 0.10  # Disrupts intricate build-up combinations
            if away_style == "passing":
                away_modifier -= 0.10

        # 2. Extreme Wind Velocity (Unpredictable Ball Trajectories)
        if wind_speed > 25.0:
            if home_style == "long_ball":
                home_modifier -= 0.15  # Degrades direct aerial channels
            if away_style == "long_ball":
                away_modifier -= 0.15

        # 3. Severe Thermal Stress (Accelerated Stamina Depletion)
        if temp > 32.0 or temp < 0.0:
            # Impacts high-pressing defensive or offensive setups
            if home_style == "pressing":
                home_modifier -= 0.08
            if away_style == "pressing":
                away_modifier -= 0.08

        return {
            "condition": condition,
            "temp": temp,
            "wind_speed": wind_speed,
            "home_weather_modifier": round(home_modifier, 2),
            "away_weather_modifier": round(away_modifier, 2),
            "environmental_hazard_detected": home_modifier < 1.0 or away_modifier < 1.0
        }
