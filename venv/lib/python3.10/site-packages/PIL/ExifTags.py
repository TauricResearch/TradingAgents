#
# The Python Imaging Library.
# $Id$
#
# EXIF tags
#
# Copyright (c) 2003 by Secret Labs AB
#
# See the README file for information on usage and redistribution.
#

"""
This module provides constants and clear-text names for various
well-known EXIF tags.
"""
from __future__ import annotations

from enum import IntEnum


class Base(IntEnum):
    # possibly incomplete
    InteropIndex = 0x0001
    ProcessingSoftware = 0x000B
    NewSubfileType = 0x00FE
    SubfileType = 0x00FF
    ImageWidth = 0x0100
    ImageLength = 0x0101
    BitsPerSample = 0x0102
    Compression = 0x0103
    PhotometricInterpretation = 0x0106
    Thresholding = 0x0107
    CellWidth = 0x0108
    CellLength = 0x0109
    FillOrder = 0x010A
    DocumentName = 0x010D
    ImageDescription = 0x010E
    Make = 0x010F
    Model = 0x0110
    StripOffsets = 0x0111
    Orientation = 0x0112
    SamplesPerPixel = 0x0115
    RowsPerStrip = 0x0116
    StripByteCounts = 0x0117
    MinSampleValue = 0x0118
    MaxSampleValue = 0x0119
    XResolution = 0x011A
    YResolution = 0x011B
    PlanarConfiguration = 0x011C
    PageName = 0x011D
    FreeOffsets = 0x0120
    FreeByteCounts = 0x0121
    GrayResponseUnit = 0x0122
    GrayResponseCurve = 0x0123
    T4Options = 0x0124
    T6Options = 0x0125
    ResolutionUnit = 0x0128
    PageNumber = 0x0129
    TransferFunction = 0x012D
    Software = 0x0131
    DateTime = 0x0132
    Artist = 0x013B
    HostComputer = 0x013C
    Predictor = 0x013D
    WhitePoint = 0x013E
    PrimaryChromaticities = 0x013F
    ColorMap = 0x0140
    HalftoneHints = 0x0141
    TileWidth = 0x0142
    TileLength = 0x0143
    TileOffsets = 0x0144
    TileByteCounts = 0x0145
    SubIFDs = 0x014A
    InkSet = 0x014C
    InkNames = 0x014D
    NumberOfInks = 0x014E
    DotRange = 0x0150
    TargetPrinter = 0x0151
    ExtraSamples = 0x0152
    SampleFormat = 0x0153
    SMinSampleValue = 0x0154
    SMaxSampleValue = 0x0155
    TransferRange = 0x0156
    ClipPath = 0x0157
    XClipPathUnits = 0x0158
    YClipPathUnits = 0x0159
    Indexed = 0x015A
    JPEGTables = 0x015B
    OPIProxy = 0x015F
    JPEGProc = 0x0200
    JpegIFOffset = 0x0201
    JpegIFByteCount = 0x0202
    JpegRestartInterval = 0x0203
    JpegLosslessPredictors = 0x0205
    JpegPointTransforms = 0x0206
    JpegQTables = 0x0207
    JpegDCTables = 0x0208
    JpegACTables = 0x0209
    YCbCrCoefficients = 0x0211
    YCbCrSubSampling = 0x0212
    YCbCrPositioning = 0x0213
    ReferenceBlackWhite = 0x0214
    XMLPacket = 0x02BC
    RelatedImageFileFormat = 0x1000
    RelatedImageWidth = 0x1001
    RelatedImageLength = 0x1002
    Rating = 0x4746
    RatingPercent = 0x4749
    ImageID = 0x800D
    CFARepeatPatternDim = 0x828D
    BatteryLevel = 0x828F
    Copyright = 0x8298
    ExposureTime = 0x829A
    FNumber = 0x829D
    IPTCNAA = 0x83BB
    ImageResources = 0x8649
    ExifOffset = 0x8769
    InterColorProfile = 0x8773
    ExposureProgram = 0x8822
    SpectralSensitivity = 0x8824
    GPSInfo = 0x8825
    ISOSpeedRatings = 0x8827
    OECF = 0x8828
    Interlace = 0x8829
    TimeZoneOffset = 0x882A
    SelfTimerMode = 0x882B
    SensitivityType = 0x8830
    StandardOutputSensitivity = 0x8831
    RecommendedExposureIndex = 0x8832
    ISOSpeed = 0x8833
    ISOSpeedLatitudeyyy = 0x8834
    ISOSpeedLatitudezzz = 0x8835
    ExifVersion = 0x9000
    DateTimeOriginal = 0x9003
    DateTimeDigitized = 0x9004
    OffsetTime = 0x9010
    OffsetTimeOriginal = 0x9011
    OffsetTimeDigitized = 0x9012
    ComponentsConfiguration = 0x9101
    CompressedBitsPerPixel = 0x9102
    ShutterSpeedValue = 0x9201
    ApertureValue = 0x9202
    BrightnessValue = 0x9203
    ExposureBiasValue = 0x9204
    MaxApertureValue = 0x9205
    SubjectDistance = 0x9206
    MeteringMode = 0x9207
    LightSource = 0x9208
    Flash = 0x9209
    FocalLength = 0x920A
    Noise = 0x920D
    ImageNumber = 0x9211
    SecurityClassification = 0x9212
    ImageHistory = 0x9213
    TIFFEPStandardID = 0x9216
    MakerNote = 0x927C
    UserComment = 0x9286
    SubsecTime = 0x9290
    SubsecTimeOriginal = 0x9291
    SubsecTimeDigitized = 0x9292
    AmbientTemperature = 0x9400
    Humidity = 0x9401
    Pressure = 0x9402
    WaterDepth = 0x9403
    Acceleration = 0x9404
    CameraElevationAngle = 0x9405
    XPTitle = 0x9C9B
    XPComment = 0x9C9C
    XPAuthor = 0x9C9D
    XPKeywords = 0x9C9E
    XPSubject = 0x9C9F
    FlashPixVersion = 0xA000
    ColorSpace = 0xA001
    ExifImageWidth = 0xA002
    ExifImageHeight = 0xA003
    RelatedSoundFile = 0xA004
    ExifInteroperabilityOffset = 0xA005
    FlashEnergy = 0xA20B
    SpatialFrequencyResponse = 0xA20C
    FocalPlaneXResolution = 0xA20E
    FocalPlaneYResolution = 0xA20F
    FocalPlaneResolutionUnit = 0xA210
    SubjectLocation = 0xA214
    ExposureIndex = 0xA215
    SensingMethod = 0xA217
    FileSource = 0xA300
    SceneType = 0xA301
    CFAPattern = 0xA302
    CustomRendered = 0xA401
    ExposureMode = 0xA402
    WhiteBalance = 0xA403
    DigitalZoomRatio = 0xA404
    FocalLengthIn35mmFilm = 0xA405
    SceneCaptureType = 0xA406
    GainControl = 0xA407
    Contrast = 0xA408
    Saturation = 0xA409
    Sharpness = 0xA40A
    DeviceSettingDescription = 0xA40B
    SubjectDistanceRange = 0xA40C
    ImageUniqueID = 0xA420
    CameraOwnerName = 0xA430
    BodySerialNumber = 0xA431
    LensSpecification = 0xA432
    LensMake = 0xA433
    LensModel = 0xA434
    LensSerialNumber = 0xA435
    CompositeImage = 0xA460
    CompositeImageCount = 0xA461
    CompositeImageExposureTimes = 0xA462
    Gamma = 0xA500
    PrintImageMatching = 0xC4A5
    DNGVersion = 0xC612
    DNGBackwardVersion = 0xC613
    UniqueCameraModel = 0xC614
    LocalizedCameraModel = 0xC615
    CFAPlaneColor = 0xC616
    CFALayout = 0xC617
    LinearizationTable = 0xC618
    BlackLevelRepeatDim = 0xC619
    BlackLevel = 0xC61A
    BlackLevelDeltaH = 0xC61B
    BlackLevelDeltaV = 0xC61C
    WhiteLevel = 0xC61D
    DefaultScale = 0xC61E
    DefaultCropOrigin = 0xC61F
    DefaultCropSize = 0xC620
    ColorMatrix1 = 0xC621
    ColorMatrix2 = 0xC622
    CameraCalibration1 = 0xC623
    CameraCalibration2 = 0xC624
    ReductionMatrix1 = 0xC625
    ReductionMatrix2 = 0xC626
    AnalogBalance = 0xC627
    AsShotNeutral = 0xC628
    AsShotWhiteXY = 0xC629
    BaselineExposure = 0xC62A
    BaselineNoise = 0xC62B
    BaselineSharpness = 0xC62C
    BayerGreenSplit = 0xC62D
    LinearResponseLimit = 0xC62E
    CameraSerialNumber = 0xC62F
    LensInfo = 0xC630
    ChromaBlurRadius = 0xC631
    AntiAliasStrength = 0xC632
    ShadowScale = 0xC633
    DNGPrivateData = 0xC634
    MakerNoteSafety = 0xC635
    CalibrationIlluminant1 = 0xC65A
    CalibrationIlluminant2 = 0xC65B
    BestQualityScale = 0xC65C
    RawDataUniqueID = 0xC65D
    OriginalRawFileName = 0xC68B
    OriginalRawFileData = 0xC68C
    ActiveArea = 0xC68D
    MaskedAreas = 0xC68E
    AsShotICCProfile = 0xC68F
    AsShotPreProfileMatrix = 0xC690
    CurrentICCProfile = 0xC691
    CurrentPreProfileMatrix = 0xC692
    ColorimetricReference = 0xC6BF
    CameraCalibrationSignature = 0xC6F3
    ProfileCalibrationSignature = 0xC6F4
    AsShotProfileName = 0xC6F6
    NoiseReductionApplied = 0xC6F7
    ProfileName = 0xC6F8
    ProfileHueSatMapDims = 0xC6F9
    ProfileHueSatMapData1 = 0xC6FA
    ProfileHueSatMapData2 = 0xC6FB
    ProfileToneCurve = 0xC6FC
    ProfileEmbedPolicy = 0xC6FD
    ProfileCopyright = 0xC6FE
    ForwardMatrix1 = 0xC714
    ForwardMatrix2 = 0xC715
    PreviewApplicationName = 0xC716
    PreviewApplicationVersion = 0xC717
    PreviewSettingsName = 0xC718
    PreviewSettingsDigest = 0xC719
    PreviewColorSpace = 0xC71A
    PreviewDateTime = 0xC71B
    RawImageDigest = 0xC71C
    OriginalRawFileDigest = 0xC71D
    SubTileBlockSize = 0xC71E
    RowInterleaveFactor = 0xC71F
    ProfileLookTableDims = 0xC725
    ProfileLookTableData = 0xC726
    OpcodeList1 = 0xC740
    OpcodeList2 = 0xC741
    OpcodeList3 = 0xC74E
    NoiseProfile = 0xC761


"""Maps EXIF tags to tag names."""
TAGS = {
    **{i.value: i.name for i in Base},
    0x920C: "SpatialFrequencyResponse",
    0x9214: "SubjectLocation",
    0x9215: "ExposureIndex",
    0x828E: "CFAPattern",
    0x920B: "FlashEnergy",
    0x9216: "TIFF/EPStandardID",
}


class GPS(IntEnum):
    GPSVersionID = 0x00
    GPSLatitudeRef = 0x01
    GPSLatitude = 0x02
    GPSLongitudeRef = 0x03
    GPSLongitude = 0x04
    GPSAltitudeRef = 0x05
    GPSAltitude = 0x06
    GPSTimeStamp = 0x07
    GPSSatellites = 0x08
    GPSStatus = 0x09
    GPSMeasureMode = 0x0A
    GPSDOP = 0x0B
    GPSSpeedRef = 0x0C
    GPSSpeed = 0x0D
    GPSTrackRef = 0x0E
    GPSTrack = 0x0F
    GPSImgDirectionRef = 0x10
    GPSImgDirection = 0x11
    GPSMapDatum = 0x12
    GPSDestLatitudeRef = 0x13
    GPSDestLatitude = 0x14
    GPSDestLongitudeRef = 0x15
    GPSDestLongitude = 0x16
    GPSDestBearingRef = 0x17
    GPSDestBearing = 0x18
    GPSDestDistanceRef = 0x19
    GPSDestDistance = 0x1A
    GPSProcessingMethod = 0x1B
    GPSAreaInformation = 0x1C
    GPSDateStamp = 0x1D
    GPSDifferential = 0x1E
    GPSHPositioningError = 0x1F


"""Maps EXIF GPS tags to tag names."""
GPSTAGS = {i.value: i.name for i in GPS}


class Interop(IntEnum):
    InteropIndex = 0x0001
    InteropVersion = 0x0002
    RelatedImageFileFormat = 0x1000
    RelatedImageWidth = 0x1001
    RelatedImageHeight = 0x1002


class IFD(IntEnum):
    Exif = 0x8769
    GPSInfo = 0x8825
    MakerNote = 0x927C
    Makernote = 0x927C  # Deprecated
    Interop = 0xA005
    IFD1 = -1


class LightSource(IntEnum):
    Unknown = 0x00
    Daylight = 0x01
    Fluorescent = 0x02
    Tungsten = 0x03
    Flash = 0x04
    Fine = 0x09
    Cloudy = 0x0A
    Shade = 0x0B
    DaylightFluorescent = 0x0C
    DayWhiteFluorescent = 0x0D
    CoolWhiteFluorescent = 0x0E
    WhiteFluorescent = 0x0F
    StandardLightA = 0x11
    StandardLightB = 0x12
    StandardLightC = 0x13
    D55 = 0x14
    D65 = 0x15
    D75 = 0x16
    D50 = 0x17
    ISO = 0x18
    Other = 0xFF
