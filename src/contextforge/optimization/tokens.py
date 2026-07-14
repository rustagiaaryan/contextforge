"""Deterministic token-cost estimation."""


def estimate_tokens(text: str) -> int:
    """Estimate code-oriented tokens conservatively without a model tokenizer.

    Four UTF-8-ish characters per token is a common approximation. Counting every
    four Unicode code points and rounding up is deterministic and deliberately avoids
    understating short metadata fields.
    """
    return max(1, (len(text) + 3) // 4)
