from core.moviepy_compat import patch_moviepy

patch_moviepy()


def make_floating_text_overlay(text: str, duration: float, size: tuple, style: dict | None = None):
    import textwrap

    from moviepy import ColorClip, CompositeVideoClip, TextClip

    style = dict(style or {})
    animation = style.get("animation", "slide_up")
    font_name = style.get("font")
    font_size = max(20, int(style.get("font_size", 58) or 58))
    position = style.get("position", "upper_third")

    width, height = size
    wrap_width = max(18, min(34, int((width - 140) / max(font_size * 0.54, 1))))
    wrapped = "\n".join(textwrap.wrap((text or "").strip(), width=wrap_width))

    text_clip = _create_text_clip(TextClip, wrapped, duration, width, font_size, font_name)
    text_width, text_height = text_clip.size

    bar_width = max(4, int(font_size * 0.12))
    bar_height = text_height + max(12, int(font_size * 0.28))
    accent = ColorClip(size=(bar_width, bar_height), color=(255, 255, 255)).set_duration(duration).set_opacity(0.92)

    x_start, y_pos = _resolve_position(position, width, height, text_width, text_height, bar_width)
    accent = accent.set_position((x_start, y_pos - max(6, int(font_size * 0.12))))
    text_clip = text_clip.set_position((x_start + bar_width + max(12, int(font_size * 0.24)), y_pos))

    composite = CompositeVideoClip([accent, text_clip], size=(width, height)).set_duration(duration)

    if animation == "slide_up":
        return _animate_slide_up(composite, duration, slide_px=max(18, int(font_size * 0.45)))
    if animation == "fade":
        return composite.fadein(0.25).fadeout(0.25)
    if animation == "pop":
        return _animate_pop(composite, duration)
    return composite.fadein(0.18).fadeout(0.18)


def _create_text_clip(text_clip_cls, text: str, duration: float, width: int, font_size: int, font_name: str | None):
    kwargs = {
        "text": text,
        "font_size": font_size,
        "font": font_name or None,
        "color": "white",
        "stroke_color": "black",
        "stroke_width": max(1, int(font_size * 0.05)),
        "method": "caption",
        "size": (max(220, width - 180), None),
        "text_align": "left",
        "horizontal_align": "left",
        "duration": duration,
    }
    try:
        return text_clip_cls(**kwargs)
    except Exception:
        kwargs["font"] = None
        return text_clip_cls(**kwargs)


def _resolve_position(position: str, width: int, height: int, text_width: int, text_height: int, bar_width: int):
    total_width = bar_width + max(12, int(text_height * 0.35)) + text_width
    x_start = max(24, (width - total_width) // 2)
    top_map = {
        "top": int(height * 0.08),
        "upper_third": int(height * 0.18),
        "center": int((height - text_height) * 0.5),
        "lower_third": int(height * 0.62),
        "bottom": int(height * 0.78),
    }
    y_pos = top_map.get(position, top_map["upper_third"])
    y_pos = max(16, min(y_pos, max(16, height - text_height - 24)))
    return x_start, y_pos


def _animate_slide_up(clip, duration: float, slide_px: int = 30):
    from moviepy import ColorClip, CompositeVideoClip

    width, height = clip.size
    ease_dur = min(0.5, duration * 0.3)

    def position_fn(t):
        if t < ease_dur:
            progress = t / max(ease_dur, 0.001)
            progress = 1 - (1 - progress) ** 3
            offset = int(slide_px * (1 - progress))
        else:
            offset = 0
        return ("center", offset)

    bg = ColorClip(size=(width, height), color=(0, 0, 0)).set_opacity(0).set_duration(duration)
    moving = clip.set_position(position_fn)
    return CompositeVideoClip([bg, moving], size=(width, height)).set_duration(duration)


def _animate_pop(clip, duration: float):
    from moviepy import ColorClip, CompositeVideoClip

    width, height = clip.size
    ease_dur = min(0.35, duration * 0.25)

    def resize_fn(t):
        if t >= ease_dur:
            return 1.0
        progress = t / max(ease_dur, 0.001)
        progress = 1 - (1 - progress) ** 3
        return 0.9 + (0.1 * progress)

    bg = ColorClip(size=(width, height), color=(0, 0, 0)).set_opacity(0).set_duration(duration)
    animated = clip.resize(resize_fn).set_position("center").fadeout(min(0.22, duration * 0.2))
    return CompositeVideoClip([bg, animated], size=(width, height)).set_duration(duration)
