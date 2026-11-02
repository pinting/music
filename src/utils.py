import os
import sys

def require_env(*names: str) -> list[str]:
    values = [os.getenv(name) for name in names]
    missing = [name for name, value in zip(names, values) if not value]

    if missing:
        sys.exit(f"Error: {', '.join(missing)} must be configured in .env")

    return values

def barcode_variants(barcode: str | None) -> list[str]:
    """Spotify pads some barcodes with zeros to 14 digits, while Tidal has them as EAN or UPC."""
    if not barcode:
        return []

    digits = barcode.lstrip("0")

    return list(dict.fromkeys((barcode, digits.zfill(13), digits.zfill(12))))

def is_progress(index: int, total: int, every: int) -> bool:
    return index % every == 0 or index == total

def merge_distinct(existing: list[str], new: list[str]) -> list[str]:
    """Appends the new items missing from existing, comparing them case-insensitively."""
    result = list(existing)
    seen = {item.strip().lower() for item in existing}

    for item in new:
        cleaned = item.strip()

        if cleaned and cleaned.lower() not in seen:
            seen.add(cleaned.lower())
            result.append(cleaned)

    return result
