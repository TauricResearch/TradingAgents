import abc
from collections.abc import Callable, Collection, Iterable, Sequence, Generator
import contextlib
from pathlib import Path
from matplotlib.artist import Artist
from matplotlib.backend_bases import TimerBase
from matplotlib.figure import Figure

from typing import Any

subprocess_creation_flags: int

def adjusted_figsize(w: float, h: float, dpi: float, n: int) -> tuple[float, float]: ...

class MovieWriterRegistry:
    def __init__(self) -> None: ...
    def register(
        self, name: str
    ) -> Callable[[type[AbstractMovieWriter]], type[AbstractMovieWriter]]: ...
    def is_available(self, name: str) -> bool: ...
    def __iter__(self) -> Generator[str, None, None]: ...
    def list(self) -> list[str]: ...
    def __getitem__(self, name: str) -> type[AbstractMovieWriter]: ...

writers: MovieWriterRegistry

class AbstractMovieWriter(abc.ABC, metaclass=abc.ABCMeta):
    fps: int
    metadata: dict[str, str]
    codec: str
    bitrate: int
    def __init__(
        self,
        fps: int = ...,
        metadata: dict[str, str] | None = ...,
        codec: str | None = ...,
        bitrate: int | None = ...,
    ) -> None: ...
    outfile: str | Path
    fig: Figure
    dpi: float

    @abc.abstractmethod
    def setup(self, fig: Figure, outfile: str | Path, dpi: float | None = ...) -> None: ...
    @property
    def frame_size(self) -> tuple[int, int]: ...
    @abc.abstractmethod
    def grab_frame(self, **savefig_kwargs) -> None: ...
    @abc.abstractmethod
    def finish(self) -> None: ...
    @contextlib.contextmanager
    def saving(
        self, fig: Figure, outfile: str | Path, dpi: float | None, *args, **kwargs
    ) -> Generator[AbstractMovieWriter, None, None]: ...

class MovieWriter(AbstractMovieWriter):
    supported_formats: list[str]
    frame_format: str
    extra_args: list[str] | None
    def __init__(
        self,
        fps: int = ...,
        codec: str | None = ...,
        bitrate: int | None = ...,
        extra_args: list[str] | None = ...,
        metadata: dict[str, str] | None = ...,
    ) -> None: ...
    def setup(self, fig: Figure, outfile: str | Path, dpi: float | None = ...) -> None: ...
    def grab_frame(self, **savefig_kwargs) -> None: ...
    def finish(self) -> None: ...
    @classmethod
    def bin_path(cls) -> str: ...
    @classmethod
    def isAvailable(cls) -> bool: ...

class FileMovieWriter(MovieWriter):
    fig: Figure
    outfile: str | Path
    dpi: float
    temp_prefix: str
    fname_format_str: str
    def setup(
        self,
        fig: Figure,
        outfile: str | Path,
        dpi: float | None = ...,
        frame_prefix: str | Path | None = ...,
    ) -> None: ...
    def __del__(self) -> None: ...
    @property
    def frame_format(self) -> str: ...
    @frame_format.setter
    def frame_format(self, frame_format: str) -> None: ...

class PillowWriter(AbstractMovieWriter):
    @classmethod
    def isAvailable(cls) -> bool: ...
    def setup(
        self, fig: Figure, outfile: str | Path, dpi: float | None = ...
    ) -> None: ...
    def grab_frame(self, **savefig_kwargs) -> None: ...
    def finish(self) -> None: ...

class FFMpegBase:
    codec: str
    @property
    def output_args(self) -> list[str]: ...

class FFMpegWriter(FFMpegBase, MovieWriter): ...

class FFMpegFileWriter(FFMpegBase, FileMovieWriter):
    supported_formats: list[str]

class ImageMagickBase:
    @classmethod
    def bin_path(cls) -> str: ...
    @classmethod
    def isAvailable(cls) -> bool: ...

class ImageMagickWriter(ImageMagickBase, MovieWriter):
    input_names: str

class ImageMagickFileWriter(ImageMagickBase, FileMovieWriter):
    supported_formats: list[str]
    @property
    def input_names(self) -> str: ...

class HTMLWriter(FileMovieWriter):
    supported_formats: list[str]
    @classmethod
    def isAvailable(cls) -> bool: ...
    embed_frames: bool
    default_mode: str
    def __init__(
        self,
        fps: int = ...,
        codec: str | None = ...,
        bitrate: int | None = ...,
        extra_args: list[str] | None = ...,
        metadata: dict[str, str] | None = ...,
        embed_frames: bool = ...,
        default_mode: str = ...,
        embed_limit: float | None = ...,
    ) -> None: ...
    def setup(
        self,
        fig: Figure,
        outfile: str | Path,
        dpi: float | None = ...,
        frame_dir: str | Path | None = ...,
    ) -> None: ...
    def grab_frame(self, **savefig_kwargs): ...
    def finish(self) -> None: ...

class Animation:
    frame_seq: Iterable[Artist]
    event_source: Any
    def __init__(
        self, fig: Figure, event_source: Any | None = ..., blit: bool = ...
    ) -> None: ...
    def __del__(self) -> None: ...
    def save(
        self,
        filename: str | Path,
        writer: AbstractMovieWriter | str | None = ...,
        fps: int | None = ...,
        dpi: float | None = ...,
        codec: str | None = ...,
        bitrate: int | None = ...,
        extra_args: list[str] | None = ...,
        metadata: dict[str, str] | None = ...,
        extra_anim: list[Animation] | None = ...,
        savefig_kwargs: dict[str, Any] | None = ...,
        *,
        progress_callback: Callable[[int, int], Any] | None = ...
    ) -> None: ...
    def new_frame_seq(self) -> Iterable[Artist]: ...
    def new_saved_frame_seq(self) -> Iterable[Artist]: ...
    def to_html5_video(self, embed_limit: float | None = ...) -> str: ...
    def to_jshtml(
        self,
        fps: int | None = ...,
        embed_frames: bool = ...,
        default_mode: str | None = ...,
    ) -> str: ...
    def _repr_html_(self) -> str: ...
    def pause(self) -> None: ...
    def resume(self) -> None: ...

class TimedAnimation(Animation):
    def __init__(
        self,
        fig: Figure,
        interval: int = ...,
        repeat_delay: int = ...,
        repeat: bool = ...,
        event_source: TimerBase | None = ...,
        *args,
        **kwargs
    ) -> None: ...

class ArtistAnimation(TimedAnimation):
    def __init__(self, fig: Figure, artists: Sequence[Collection[Artist]], *args, **kwargs) -> None: ...

class FuncAnimation(TimedAnimation):
    def __init__(
        self,
        fig: Figure,
        func: Callable[..., Iterable[Artist]],
        frames: Iterable | int | Callable[[], Generator] | None = ...,
        init_func: Callable[[], Iterable[Artist]] | None = ...,
        fargs: tuple[Any, ...] | None = ...,
        save_count: int | None = ...,
        *,
        cache_frame_data: bool = ...,
        **kwargs
    ) -> None: ...
