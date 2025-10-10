from io import BytesIO
from pathlib import Path

import pytest

from matplotlib.testing.decorators import image_comparison
from matplotlib import cm, pyplot as plt


@image_comparison(['pngsuite.png'], tol=0.04)
def test_pngsuite():
    files = sorted(
        (Path(__file__).parent / "baseline_images/pngsuite").glob("basn*.png"))

    plt.figure(figsize=(len(files), 2))

    for i, fname in enumerate(files):
        data = plt.imread(fname)
        cmap = None  # use default colormap
        if data.ndim == 2:
            # keep grayscale images gray
            cmap = cm.gray
        # Using the old default data interpolation stage lets us
        # continue to use the existing reference image
        plt.imshow(data, extent=(i, i + 1, 0, 1), cmap=cmap,
                   interpolation_stage='data')

    plt.gca().patch.set_facecolor("#ddffff")
    plt.gca().set_xlim(0, len(files))


def test_truncated_file(tmp_path):
    path = tmp_path / 'test.png'
    path_t = tmp_path / 'test_truncated.png'
    plt.savefig(path)
    with open(path, 'rb') as fin:
        buf = fin.read()
    with open(path_t, 'wb') as fout:
        fout.write(buf[:20])

    with pytest.raises(Exception):
        plt.imread(path_t)


def test_truncated_buffer():
    b = BytesIO()
    plt.savefig(b)
    b.seek(0)
    b2 = BytesIO(b.read(20))
    b2.seek(0)

    with pytest.raises(Exception):
        plt.imread(b2)
