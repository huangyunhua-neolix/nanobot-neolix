"""Shared spec-locked gate constants. Owner: M5 round-A Arch reviewer (RF-4)."""
# Derivation: ceil(TIER_C_FLOOR=5) × PER_RECORD_TIMEOUT_S=30 s × SLACK≈4
#   × 1000 ms/s = 600_000 ms.
GATE_TIMEOUT_MS_HARD: int = 600_000

# Gate 2 (§6.2.2)
SKILL_LINE_HARD_CAP: int = 400
SKILL_LINE_DELTA_CAP: int = 150

# Gate 1 (§6.1.1 / §6.1.2)
PER_RECORD_TIMEOUT_S: int = 30
TIER_A_PASS_RATE_FLOOR_BPS: int = 80   # 80/100 = 0.80
TIER_C_PASS_RATE_FLOOR_BPS: int = 100  # 100/100 = 1.00

# Judge rubric (§7.2, decision #124)
RUBRIC_PASS_THRESHOLD: float = 0.6
