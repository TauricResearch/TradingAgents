from pathlib import Path
import shutil

import pytest
from pytest import approx

from matplotlib.testing.compare import compare_images
from matplotlib.testing.decorators import _image_directories


# Tests of the image comparison algorithm.
@pytest.mark.parametrize(
    'im1, im2, tol, expect_rms',
    [
        # Comparison of an image and the same image with minor differences.
        # This expects the images to compare equal under normal tolerance, and
        # have a small RMS.
        ('basn3p02.png', 'basn3p02-minorchange.png', 10, None),
        # Now test with no tolerance.
        ('basn3p02.png', 'basn3p02-minorchange.png', 0, 6.50646),
        # Comparison with an image that is shifted by 1px in the X axis.
        ('basn3p02.png', 'basn3p02-1px-offset.png', 0, 90.15611),
        # Comparison with an image with half the pixels shifted by 1px in the X
        # axis.
        ('basn3p02.png', 'basn3p02-half-1px-offset.png', 0, 63.75),
        # Comparison of an image and the same image scrambled.
        # This expects the images to compare completely different, with a very
        # large RMS.
        # Note: The image has been scrambled in a specific way, by having
        # each color component of each pixel randomly placed somewhere in the
        # image. It contains exactly the same number of pixels of each color
        # value of R, G and B, but in a totally different position.
        # Test with no tolerance to make sure that we pick up even a very small
        # RMS error.
        ('basn3p02.png', 'basn3p02-scrambled.png', 0, 172.63582),
        # Comparison of an image and a slightly brighter image.
        # The two images are solid color, with the second image being exactly 1
        # color value brighter.
        # This expects the images to compare equal under normal tolerance, and
        # have an RMS of exactly 1.
        ('all127.png', 'all128.png', 0, 1),
        # Now test the reverse comparison.
        ('all128.png', 'all127.png', 0, 1),
    ])
def test_image_comparison_expect_rms(im1, im2, tol, expect_rms, tmp_path,
                                     monkeypatch):
    """
    Compare two images, expecting a particular RMS error.

    im1 and im2 are filenames relative to the baseline_dir directory.

    tol is the tolerance to pass to compare_images.

    expect_rms is the expected RMS value, or None. If None, the test will
    succeed if compare_images succeeds. Otherwise, the test will succeed if
    compare_images fails and returns an RMS error almost equal to this value.
    """
    # Change the working directory using monkeypatch to use a temporary
    # test specific directory
    monkeypatch.chdir(tmp_path)
    baseline_dir, result_dir = map(Path, _image_directories(lambda: "dummy"))
    # Copy "test" image to result_dir, so that compare_images writes
    # the diff to result_dir, rather than to the source tree
    result_im2 = result_dir / im1
    shutil.copyfile(baseline_dir / im2, result_im2)
    results = compare_images(
        baseline_dir / im1, result_im2, tol=tol, in_decorator=True)

    if expect_rms is None:
        assert results is None
    else:
        assert results is not None
        assert results['rms'] == approx(expect_rms, abs=1e-4)
