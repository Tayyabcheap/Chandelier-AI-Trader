"""
strategy/gemini_advisor.py
================================================================
Gemini AI Trade Advisor — The "Senior Risk Manager"

Re-purposed for the Chandelier Exit + ADX strategy.
Gemini's job is NOT to find the "perfect" setup (that causes
analysis paralysis). Its job is to:
1. Check for extreme macro/news risks (Veto Power).
2. If no extreme risk, it MUST approve and rate the setup (1-10)
   for dynamic position sizing.
================================================================
"""

import json
import re
import time
from typing import Optional, Tuple, Dict
from core.logger import get_logger

logger = get_logger("GeminiAdvisor")

try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    logger.warning(
        "google-generativeai not installed.\n"
        "  Run:  pip install google-generativeai\n"
        "  Gemini AI advisor will be disabled."
    )

_last_call_time = 0
MIN_CALL_INTERVAL = 5  # seconds between API calls


SYSTEM_PROMPT = """You are the Senior Risk Manager for an automated forex fund.
The algorithmic bot (Chandelier Exit + ADX) has just signaled a trade.

Your job is NOT to find a perfect technical setup. All setups have flaws. 
Your job is to protect against extreme macroeconomic risks, and otherwise rate the momentum.

RULES:
1. EXTREME RISK CHECK (Veto Power): You may ONLY veto the trade if there is an extreme, imminent macroeconomic event (e.g., massive central bank rate surprise, major geopolitical shock) or if buying directly into an undeniable, massive multi-year resistance wall.
2. DEFAULT TO APPROVAL: If there is no catastrophic macro risk, you MUST NOT veto the trade. 
3. DYNAMIC RATING: If you do not veto, rate the setup from 1 to 10. We will use this rating strictly for position sizing. 
   - 1-3: Weak setup, but we still take it with minimal size.
   - 4-7: Standard trend-following setup.
   - 8-10: Exceptional momentum and macro alignment.

You MUST respond in EXACTLY this JSON format with no additional text:
{
    "veto": false,
    "rating": 7,
    "reasoning": "Brief explanation",
    "risk_notes": "Optional"
}
"""


class GeminiAdvisor:
    """
    AI-powered macro risk manager.
    """

    def __init__(self, api_key: Optional[str] = None,
                 model_name: str = "gemini-2.0-flash"):
        self.enabled = False
        self.model = None
        self.model_name = model_name
        self._stats = {"total": 0, "vetoes": 0, "approved": 0, "errors": 0}
        self.veto_cache = {}  # {symbol: expiration_timestamp}

        if not GEMINI_AVAILABLE:
            return
        if not api_key:
            return

        try:
            genai.configure(api_key=api_key)
            # Setting safety settings to BLOCK_NONE to prevent financial advice filters from triggering
            safety_settings = [
                {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"}
            ]

            self.model = genai.GenerativeModel(
                model_name=model_name,
                system_instruction=SYSTEM_PROMPT,
                generation_config=genai.GenerationConfig(
                    temperature=0.2
                ),
                safety_settings=safety_settings
            )
            self.enabled = True
            logger.info(f"Gemini AI Risk Manager ACTIVE (model: {model_name})")
        except Exception as e:
            logger.error(f"Gemini init failed: {e}")

    def review_trade(self, trade_context: Dict) -> Tuple[bool, int, str]:
        """
        Ask Gemini to review a proposed trade.
        Returns:
            (veto: bool, rating: int, reasoning: str)
        """
        if not self.enabled:
            return False, 5, "Gemini disabled — auto-approving (Rating 5/10)"

        symbol = trade_context.get("symbol", "UNKNOWN")

        # Check 30-minute cooldown
        if symbol in self.veto_cache:
            if time.time() < self.veto_cache[symbol]:
                remaining = int((self.veto_cache[symbol] - time.time()) / 60)
                logger.info(f"[{symbol}] Gemini on 30-min cooldown ({remaining}m left) from previous VETO.")
                return True, 1, f"Cooldown active from previous VETO. Try again in {remaining} minutes."
            else:
                del self.veto_cache[symbol]

        global _last_call_time
        elapsed = time.time() - _last_call_time
        if elapsed < MIN_CALL_INTERVAL:
            time.sleep(MIN_CALL_INTERVAL - elapsed)

        self._stats["total"] += 1

        try:
            prompt = self._build_prompt(trade_context)
            response = self.model.generate_content(prompt)
            _last_call_time = time.time()

            text = response.text.strip()
            if text.startswith("```json"): text = text[7:]
            elif text.startswith("```"): text = text[3:]
            if text.endswith("```"): text = text[:-3]
            text = text.strip()

            if not text:
                logger.error(f"Gemini returned empty text! Finish reason: {response.candidates[0].finish_reason if response.candidates else 'Unknown'}")
                raise ValueError("Empty response from Gemini")

            try:
                result = json.loads(text)
            except json.JSONDecodeError as je:
                # Fallback to regex if Gemini returns slightly malformed JSON (like missing quotes)
                logger.warning(f"Malformed JSON from AI. Attempting regex parse. Error: {je}")
                
                veto_match = re.search(r'[\'"]?veto[\'"]?\s*:\s*(true|false)', text, re.IGNORECASE)
                rating_match = re.search(r'[\'"]?rating[\'"]?\s*:\s*(\d+)', text, re.IGNORECASE)
                reasoning_match = re.search(r'[\'"]?reasoning[\'"]?\s*:\s*[\'"]([^\'"]+)[\'"]', text, re.IGNORECASE)
                
                result = {
                    "veto": veto_match.group(1).lower() == 'true' if veto_match else False,
                    "rating": int(rating_match.group(1)) if rating_match else 5,
                    "reasoning": reasoning_match.group(1) if reasoning_match else "Regex fallback logic used.",
                    "risk_notes": ""
                }

            veto = bool(result.get("veto", False))
            rating = int(result.get("rating", 5))
            reasoning = result.get("reasoning", "No reasoning provided")
            risk_notes = result.get("risk_notes", "")

            # Apply cooldown if vetoed
            if veto:
                self.veto_cache[symbol] = time.time() + (30 * 60)

            # Failsafe bounds
            rating = max(1, min(rating, 10))
            if veto:
                rating = 0

            # Stats
            if veto:
                self._stats["vetoes"] += 1
            else:
                self._stats["approved"] += 1

            full_reasoning = reasoning
            if risk_notes:
                full_reasoning += f" | Risks: {risk_notes}"

            sep = "\u2501" * 54
            verdict_str = "\u274c VETOED" if veto else f"\u2705 APPROVED ({rating}/10)"
            logger.info(
                f"\n{sep}\n"
                f"  \U0001f916 GEMINI AI VERDICT: {verdict_str}\n"
                f"  {reasoning}\n"
                + (f"  Risk: {risk_notes}\n" if risk_notes else "")
                + f"{sep}"
            )

            return veto, rating, full_reasoning

        except json.JSONDecodeError as e:
            logger.error(f"Gemini parse error: {e}")
            self._stats["errors"] += 1
            return False, 5, f"AI parse error (fail-open 5/10): {e}"
        except Exception as e:
            logger.error(f"Gemini API error: {e}")
            self._stats["errors"] += 1
            return False, 5, f"AI unavailable (fail-open 5/10): {e}"

    def _build_prompt(self, ctx: Dict) -> str:
        return (
            f"Review this proposed forex trade:\n"
            f"\n"
            f"## Trade Setup\n"
            f"- Symbol: {ctx.get('symbol', 'Unknown')}\n"
            f"- Direction: {ctx.get('direction', 'Unknown')}\n"
            f"- Entry: {ctx.get('entry', 0):.5f}\n"
            f"- Stop Loss: {ctx.get('stop_loss', 0):.5f}\n"
            f"- Take Profit: {ctx.get('take_profit', 0):.5f}\n"
            f"\n"
            f"## Technical Indicators (Chandelier Exit + ADX)\n"
            f"- Chandelier Trend: {'Bullish' if ctx.get('chandelier_trend') == 1 else 'Bearish'}\n"
            f"- Chandelier Cross: {'Bullish' if ctx.get('chandelier_cross') == 1 else 'Bearish' if ctx.get('chandelier_cross') == -1 else 'None'}\n"
            f"- ADX (Regime): {ctx.get('adx', 0):.1f} (Must be > 20 for strong trend)\n"
            f"- RSI: {ctx.get('rsi', 50):.1f}\n"
            f"- ATR: {ctx.get('atr', 0):.6f}\n"
            f"\n"
            f"## Context\n"
            f"- Session: {ctx.get('session', 'Unknown')}\n"
            f"- Daily P&L: {ctx.get('daily_pnl', 0):+.2f}%\n"
            f"\n"
            f"Remember your system instructions. Evaluate macro risks and rate 1-10. Respond in JSON."
        )

    def get_stats(self) -> Dict:
        total = self._stats["total"]
        return {
            "enabled": self.enabled,
            "total_reviews": total,
            "approved": self._stats["approved"],
            "vetoes": self._stats["vetoes"],
            "errors": self._stats["errors"],
            "approval_rate": round(self._stats["approved"] / max(total, 1) * 100, 1),
            "model": self.model_name if self.enabled else "disabled",
        }
