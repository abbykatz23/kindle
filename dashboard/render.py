from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from config import Config

_FONTS_DIR = Path(__file__).parent / "assets" / "fonts"


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    try:
        name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
        return ImageFont.truetype(str(_FONTS_DIR / name), size)
    except OSError:
        return ImageFont.load_default()


def render_dashboard(
    interview_task: dict | None,
    interview_completed: bool,
    run: dict | None,
    run_completed: bool,
    birthdays: list[dict],
    today_label: str,
) -> Image.Image:
    img = Image.new("L", (Config.DASHBOARD_WIDTH, Config.DASHBOARD_HEIGHT), color=255)
    draw = ImageDraw.Draw(img)

    # TODO: implement full layout — sections: header, interview prep, running plan, birthdays
    # Placeholder so the push pipeline can be tested before the layout is designed
    draw.text((20, 20), today_label, font=_font(22, bold=True), fill=0)
    draw.text((20, 60), "[render_dashboard not yet implemented]", font=_font(14), fill=80)

    return img


def save_dashboard(img: Image.Image) -> Path:
    out = Config.OUTPUT_IMAGE_PATH
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(out))
    return out
