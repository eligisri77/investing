"""Generate installer/assets/TradingPulse.ico (standalone — no win_app import)."""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw


def create_app_icon(size: int = 64) -> Image.Image:
    """Keep visually in sync with trading_pulse.desktop.win_app.create_app_icon."""
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    margin = size // 8
    draw.rounded_rectangle(
        (margin, margin, size - margin, size - margin),
        radius=size // 5,
        fill=(10, 10, 24, 255),
        outline=(0, 240, 255, 255),
        width=max(2, size // 24),
    )
    bolt = [
        (size * 0.52, size * 0.22),
        (size * 0.38, size * 0.52),
        (size * 0.48, size * 0.52),
        (size * 0.42, size * 0.78),
        (size * 0.66, size * 0.42),
        (size * 0.52, size * 0.42),
    ]
    draw.polygon(bolt, fill=(255, 45, 149, 255))
    return image


def main() -> Path:
    out = Path(__file__).resolve().parent / "TradingPulse.ico"
    out.parent.mkdir(parents=True, exist_ok=True)
    img = create_app_icon(256)
    img.save(
        out,
        format="ICO",
        sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    return out


if __name__ == "__main__":
    path = main()
    print(f"OK: {path} ({path.stat().st_size} bytes)")
