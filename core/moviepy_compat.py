"""
Compatibility helpers for MoviePy 1.x style method names.

The current environment ships a newer MoviePy API that prefers `with_*`,
`resized`, `cropped`, and `subclipped`. The existing codebase uses the older
`set_*`, `resize`, `crop`, and `subclip` methods, so this shim restores those
aliases in one place.
"""

from moviepy import vfx
from moviepy.Clip import Clip
from moviepy.video.VideoClip import VideoClip


def _patch_method(cls, name: str, func):
    if not hasattr(cls, name):
        setattr(cls, name, func)


def patch_moviepy():
    _patch_method(Clip, "set_duration", lambda self, value: self.with_duration(value))
    _patch_method(Clip, "set_start", lambda self, value: self.with_start(value))
    _patch_method(Clip, "subclip", lambda self, start=0, end=None: self.subclipped(start, end))

    _patch_method(VideoClip, "set_audio", lambda self, audio: self.with_audio(audio))
    _patch_method(VideoClip, "set_fps", lambda self, fps: self.with_fps(fps))
    _patch_method(VideoClip, "set_position", lambda self, pos: self.with_position(pos))
    _patch_method(VideoClip, "set_opacity", lambda self, opacity: self.with_opacity(opacity))
    _patch_method(VideoClip, "resize", lambda self, *args, **kwargs: self.resized(*args, **kwargs))
    _patch_method(VideoClip, "crop", lambda self, *args, **kwargs: self.cropped(*args, **kwargs))
    _patch_method(
        VideoClip,
        "fadein",
        lambda self, duration: self.with_effects([vfx.FadeIn(duration)]),
    )
    _patch_method(
        VideoClip,
        "fadeout",
        lambda self, duration: self.with_effects([vfx.FadeOut(duration)]),
    )
    _patch_method(VideoClip, "fl_image", lambda self, fn: self.image_transform(fn))
