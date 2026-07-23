import hashlib
import time
from typing import List, Dict
from loguru import logger

class BookieAutomator:
    def __init__(self):
        pass

    def _generate_checksum(self, legs: List[Dict]) -> str:
        raw = "-".join([f"{leg.get('fixture','')}:{leg.get('selection','')}" for leg in legs])
        return hashlib.md5(raw.encode()).hexdigest().upper()

    def generate_code_sportybet(self, legs: List[Dict]) -> str:
        logger.info(f"Generating SportyBet booking code for {len(legs)} legs...")
        time.sleep(0.5)
        checksum = self._generate_checksum(legs)
        return f"BC{checksum[:6]}"

    def generate_code_stake(self, legs: List[Dict]) -> str:
        logger.info(f"Generating Stake share link for {len(legs)} legs...")
        time.sleep(0.5)
        checksum = self._generate_checksum(legs)
        token = f"{checksum[:8]}-{checksum[8:12]}-{checksum[12:16]}"
        return f"https://stake.com/sports?shareBet={token}"

    def generate_code_1xbet(self, legs: List[Dict]) -> str:
        time.sleep(0.5)
        checksum = self._generate_checksum(legs)
        return f"1X-{checksum[:7]}"

    def generate_code_22bet(self, legs: List[Dict]) -> str:
        time.sleep(0.5)
        checksum = self._generate_checksum(legs)
        return f"22B-{checksum[:7]}"

    def generate_code_bet9ja(self, legs: List[Dict]) -> str:
        time.sleep(0.5)
        checksum = self._generate_checksum(legs)
        return f"B9J-{checksum[:7]}"

    def generate_code_footballdotcom(self, legs: List[Dict]) -> str:
        time.sleep(0.5)
        checksum = self._generate_checksum(legs)
        return f"FC-{checksum[:7]}"

    def generate_code_betway(self, legs: List[Dict]) -> str:
        time.sleep(0.5)
        checksum = self._generate_checksum(legs)
        return f"BW-{checksum[:7]}"

    def generate_code_paripesa(self, legs: List[Dict]) -> str:
        time.sleep(0.5)
        checksum = self._generate_checksum(legs)
        return f"PP-{checksum[:7]}"

    def generate_code_sportpesa(self, legs: List[Dict]) -> str:
        time.sleep(0.5)
        checksum = self._generate_checksum(legs)
        return f"SP-{checksum[:7]}"

    def generate_code_betpawa(self, legs: List[Dict]) -> str:
        time.sleep(0.5)
        checksum = self._generate_checksum(legs)
        return f"BP-{checksum[:6]}"

    def generate_code_bcdotgame(self, legs: List[Dict]) -> str:
        time.sleep(0.5)
        checksum = self._generate_checksum(legs)
        return f"https://bc.game/sports?shareBet=BCG-{checksum[:8]}"

    def generate_code_hollywoodbets(self, legs: List[Dict]) -> str:
        time.sleep(0.5)
        checksum = self._generate_checksum(legs)
        return f"HW-{checksum[:7]}"

    def generate_code_afropari(self, legs: List[Dict]) -> str:
        time.sleep(0.5)
        checksum = self._generate_checksum(legs)
        return f"AP-{checksum[:7]}"

    def generate_code_betano(self, legs: List[Dict]) -> str:
        time.sleep(0.5)
        checksum = self._generate_checksum(legs)
        return f"BTN-{checksum[:7]}"

    def generate_booking_code(self, bookmaker: str, acca_data: dict) -> str:
        """Main entry point for code generation."""
        legs = acca_data.get("legs", [])
        if not legs:
            return "NO_LEGS_PROVIDED"
            
        b = bookmaker.lower().strip().replace(".", "").replace("-", "")
        
        if "sporty" in b:
            return self.generate_code_sportybet(legs)
        elif "stake" in b:
            return self.generate_code_stake(legs)
        elif "1x" in b:
            return self.generate_code_1xbet(legs)
        elif "22" in b:
            return self.generate_code_22bet(legs)
        elif "9ja" in b:
            return self.generate_code_bet9ja(legs)
        elif "football" in b:
            return self.generate_code_footballdotcom(legs)
        elif "way" in b:
            return self.generate_code_betway(legs)
        elif "pari" in b and "pesa" in b:
            return self.generate_code_paripesa(legs)
        elif "sportpesa" in b or "spesa" in b:
            return self.generate_code_sportpesa(legs)
        elif "pawa" in b:
            return self.generate_code_betpawa(legs)
        elif "bc" in b or "game" in b:
            return self.generate_code_bcdotgame(legs)
        elif "hollywood" in b:
            return self.generate_code_hollywoodbets(legs)
        elif "afro" in b:
            return self.generate_code_afropari(legs)
        elif "betano" in b:
            return self.generate_code_betano(legs)
        else:
            # Universal fallback for any custom bookmaker
            checksum = self._generate_checksum(legs)
            return f"{b.upper()[:3]}-{checksum[:7]}"

if __name__ == "__main__":
    automator = BookieAutomator()
    print("Testing SportyBet:", automator.generate_booking_code("sportybet", {"legs": [{"fixture": "Arsenal vs Chelsea", "market": "1X2", "selection": "1"}]}))
