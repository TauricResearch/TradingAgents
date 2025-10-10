from typing import ClassVar, NoReturn, TypeAlias

import numpy as np
import numpy.typing as npt

import contourpy._contourpy as cpy

# Input numpy array types, the same as in common.h
CoordinateArray: TypeAlias = npt.NDArray[np.float64]
MaskArray: TypeAlias = npt.NDArray[np.bool_]
LevelArray: TypeAlias = npt.ArrayLike

# Output numpy array types, the same as in common.h
PointArray: TypeAlias = npt.NDArray[np.float64]
CodeArray: TypeAlias = npt.NDArray[np.uint8]
OffsetArray: TypeAlias = npt.NDArray[np.uint32]

# Types returned from filled()
FillReturn_OuterCode: TypeAlias = tuple[list[PointArray], list[CodeArray]]
FillReturn_OuterOffset: TypeAlias = tuple[list[PointArray], list[OffsetArray]]
FillReturn_ChunkCombinedCode: TypeAlias = tuple[list[PointArray | None], list[CodeArray | None]]
FillReturn_ChunkCombinedOffset: TypeAlias = tuple[list[PointArray | None], list[OffsetArray | None]]
FillReturn_ChunkCombinedCodeOffset: TypeAlias = tuple[list[PointArray | None], list[CodeArray | None], list[OffsetArray | None]]
FillReturn_ChunkCombinedOffsetOffset: TypeAlias = tuple[list[PointArray | None], list[OffsetArray | None], list[OffsetArray | None]]
FillReturn_Chunk: TypeAlias = FillReturn_ChunkCombinedCode | FillReturn_ChunkCombinedOffset | FillReturn_ChunkCombinedCodeOffset | FillReturn_ChunkCombinedOffsetOffset
FillReturn: TypeAlias = FillReturn_OuterCode | FillReturn_OuterOffset | FillReturn_Chunk

# Types returned from lines()
LineReturn_Separate: TypeAlias = list[PointArray]
LineReturn_SeparateCode: TypeAlias = tuple[list[PointArray], list[CodeArray]]
LineReturn_ChunkCombinedCode: TypeAlias = tuple[list[PointArray | None], list[CodeArray | None]]
LineReturn_ChunkCombinedOffset: TypeAlias = tuple[list[PointArray | None], list[OffsetArray | None]]
LineReturn_ChunkCombinedNan: TypeAlias = tuple[list[PointArray | None]]
LineReturn_Chunk: TypeAlias = LineReturn_ChunkCombinedCode | LineReturn_ChunkCombinedOffset | LineReturn_ChunkCombinedNan
LineReturn: TypeAlias = LineReturn_Separate | LineReturn_SeparateCode | LineReturn_Chunk


NDEBUG: int
__version__: str

class FillType:
    ChunkCombinedCode: ClassVar[cpy.FillType]
    ChunkCombinedCodeOffset: ClassVar[cpy.FillType]
    ChunkCombinedOffset: ClassVar[cpy.FillType]
    ChunkCombinedOffsetOffset: ClassVar[cpy.FillType]
    OuterCode: ClassVar[cpy.FillType]
    OuterOffset: ClassVar[cpy.FillType]
    __members__: ClassVar[dict[str, cpy.FillType]]
    def __eq__(self, other: object) -> bool: ...
    def __getstate__(self) -> int: ...
    def __hash__(self) -> int: ...
    def __index__(self) -> int: ...
    def __init__(self, value: int) -> None: ...
    def __int__(self) -> int: ...
    def __ne__(self, other: object) -> bool: ...
    def __setstate__(self, state: int) -> NoReturn: ...
    @property
    def name(self) -> str: ...
    @property
    def value(self) -> int: ...

class LineType:
    ChunkCombinedCode: ClassVar[cpy.LineType]
    ChunkCombinedNan: ClassVar[cpy.LineType]
    ChunkCombinedOffset: ClassVar[cpy.LineType]
    Separate: ClassVar[cpy.LineType]
    SeparateCode: ClassVar[cpy.LineType]
    __members__: ClassVar[dict[str, cpy.LineType]]
    def __eq__(self, other: object) -> bool: ...
    def __getstate__(self) -> int: ...
    def __hash__(self) -> int: ...
    def __index__(self) -> int: ...
    def __init__(self, value: int) -> None: ...
    def __int__(self) -> int: ...
    def __ne__(self, other: object) -> bool: ...
    def __setstate__(self, state: int) -> NoReturn: ...
    @property
    def name(self) -> str: ...
    @property
    def value(self) -> int: ...

class ZInterp:
    Linear: ClassVar[cpy.ZInterp]
    Log: ClassVar[cpy.ZInterp]
    __members__: ClassVar[dict[str, cpy.ZInterp]]
    def __eq__(self, other: object) -> bool: ...
    def __getstate__(self) -> int: ...
    def __hash__(self) -> int: ...
    def __index__(self) -> int: ...
    def __init__(self, value: int) -> None: ...
    def __int__(self) -> int: ...
    def __ne__(self, other: object) -> bool: ...
    def __setstate__(self, state: int) -> NoReturn: ...
    @property
    def name(self) -> str: ...
    @property
    def value(self) -> int: ...

def max_threads() -> int: ...

class ContourGenerator:
    def create_contour(self, level: float) -> LineReturn: ...
    def create_filled_contour(self, lower_level: float, upper_level: float) -> FillReturn: ...
    def filled(self, lower_level: float, upper_level: float) -> FillReturn: ...
    def lines(self, level: float) -> LineReturn: ...
    def multi_filled(self, levels: LevelArray) -> list[FillReturn]: ...
    def multi_lines(self, levels: LevelArray) -> list[LineReturn]: ...
    @staticmethod
    def supports_corner_mask() -> bool: ...
    @staticmethod
    def supports_fill_type(fill_type: FillType) -> bool: ...
    @staticmethod
    def supports_line_type(line_type: LineType) -> bool: ...
    @staticmethod
    def supports_quad_as_tri() -> bool: ...
    @staticmethod
    def supports_threads() -> bool: ...
    @staticmethod
    def supports_z_interp() -> bool: ...
    @property
    def chunk_count(self) -> tuple[int, int]: ...
    @property
    def chunk_size(self) -> tuple[int, int]: ...
    @property
    def corner_mask(self) -> bool: ...
    @property
    def fill_type(self) -> FillType: ...
    @property
    def line_type(self) -> LineType: ...
    @property
    def quad_as_tri(self) -> bool: ...
    @property
    def thread_count(self) -> int: ...
    @property
    def z_interp(self) -> ZInterp: ...
    default_fill_type: cpy.FillType
    default_line_type: cpy.LineType

class Mpl2005ContourGenerator(ContourGenerator):
    def __init__(
        self,
        x: CoordinateArray,
        y: CoordinateArray,
        z: CoordinateArray,
        mask: MaskArray,
        *,
        x_chunk_size: int = 0,
        y_chunk_size: int = 0,
    ) -> None: ...

class Mpl2014ContourGenerator(ContourGenerator):
    def __init__(
        self,
        x: CoordinateArray,
        y: CoordinateArray,
        z: CoordinateArray,
        mask: MaskArray,
        *,
        corner_mask: bool,
        x_chunk_size: int = 0,
        y_chunk_size: int = 0,
    ) -> None: ...

class SerialContourGenerator(ContourGenerator):
    def __init__(
        self,
        x: CoordinateArray,
        y: CoordinateArray,
        z: CoordinateArray,
        mask: MaskArray,
        *,
        corner_mask: bool,
        line_type: LineType,
        fill_type: FillType,
        quad_as_tri: bool,
        z_interp: ZInterp,
        x_chunk_size: int = 0,
        y_chunk_size: int = 0,
    ) -> None: ...
    def _write_cache(self) -> NoReturn: ...

class ThreadedContourGenerator(ContourGenerator):
    def __init__(
        self,
        x: CoordinateArray,
        y: CoordinateArray,
        z: CoordinateArray,
        mask: MaskArray,
        *,
        corner_mask: bool,
        line_type: LineType,
        fill_type: FillType,
        quad_as_tri: bool,
        z_interp: ZInterp,
        x_chunk_size: int = 0,
        y_chunk_size: int = 0,
        thread_count: int = 0,
    ) -> None: ...
    def _write_cache(self) -> None: ...
