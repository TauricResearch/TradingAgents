from pandas.core.groupby.base import transformation_kernels

# There is no Series.cumcount or DataFrame.cumcount
series_transform_kernels = [
    x for x in sorted(transformation_kernels) if x != "cumcount"
]
frame_transform_kernels = [x for x in sorted(transformation_kernels) if x != "cumcount"]
