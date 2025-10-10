from numpy.testing import (assert_allclose, assert_almost_equal,
                           assert_array_equal, assert_array_almost_equal_nulp)
import numpy as np
import pytest

from matplotlib import mlab


def test_window():
    np.random.seed(0)
    n = 1000
    rand = np.random.standard_normal(n) + 100
    ones = np.ones(n)
    assert_array_equal(mlab.window_none(ones), ones)
    assert_array_equal(mlab.window_none(rand), rand)
    assert_array_equal(np.hanning(len(rand)) * rand, mlab.window_hanning(rand))
    assert_array_equal(np.hanning(len(ones)), mlab.window_hanning(ones))


class TestDetrend:
    def setup_method(self):
        np.random.seed(0)
        n = 1000
        x = np.linspace(0., 100, n)

        self.sig_zeros = np.zeros(n)

        self.sig_off = self.sig_zeros + 100.
        self.sig_slope = np.linspace(-10., 90., n)
        self.sig_slope_mean = x - x.mean()

        self.sig_base = (
            np.random.standard_normal(n) + np.sin(x*2*np.pi/(n/100)))
        self.sig_base -= self.sig_base.mean()

    def allclose(self, *args):
        assert_allclose(*args, atol=1e-8)

    def test_detrend_none(self):
        assert mlab.detrend_none(0.) == 0.
        assert mlab.detrend_none(0., axis=1) == 0.
        assert mlab.detrend(0., key="none") == 0.
        assert mlab.detrend(0., key=mlab.detrend_none) == 0.
        for sig in [
                5.5, self.sig_off, self.sig_slope, self.sig_base,
                (self.sig_base + self.sig_slope + self.sig_off).tolist(),
                np.vstack([self.sig_base,  # 2D case.
                           self.sig_base + self.sig_off,
                           self.sig_base + self.sig_slope,
                           self.sig_base + self.sig_off + self.sig_slope]),
                np.vstack([self.sig_base,  # 2D transposed case.
                           self.sig_base + self.sig_off,
                           self.sig_base + self.sig_slope,
                           self.sig_base + self.sig_off + self.sig_slope]).T,
        ]:
            if isinstance(sig, np.ndarray):
                assert_array_equal(mlab.detrend_none(sig), sig)
            else:
                assert mlab.detrend_none(sig) == sig

    def test_detrend_mean(self):
        for sig in [0., 5.5]:  # 0D.
            assert mlab.detrend_mean(sig) == 0.
            assert mlab.detrend(sig, key="mean") == 0.
            assert mlab.detrend(sig, key=mlab.detrend_mean) == 0.
        # 1D.
        self.allclose(mlab.detrend_mean(self.sig_zeros), self.sig_zeros)
        self.allclose(mlab.detrend_mean(self.sig_base), self.sig_base)
        self.allclose(mlab.detrend_mean(self.sig_base + self.sig_off),
                      self.sig_base)
        self.allclose(mlab.detrend_mean(self.sig_base + self.sig_slope),
                      self.sig_base + self.sig_slope_mean)
        self.allclose(
            mlab.detrend_mean(self.sig_base + self.sig_slope + self.sig_off),
            self.sig_base + self.sig_slope_mean)

    def test_detrend_mean_1d_base_slope_off_list_andor_axis0(self):
        input = self.sig_base + self.sig_slope + self.sig_off
        target = self.sig_base + self.sig_slope_mean
        self.allclose(mlab.detrend_mean(input, axis=0), target)
        self.allclose(mlab.detrend_mean(input.tolist()), target)
        self.allclose(mlab.detrend_mean(input.tolist(), axis=0), target)

    def test_detrend_mean_2d(self):
        input = np.vstack([self.sig_off,
                           self.sig_base + self.sig_off])
        target = np.vstack([self.sig_zeros,
                            self.sig_base])
        self.allclose(mlab.detrend_mean(input), target)
        self.allclose(mlab.detrend_mean(input, axis=None), target)
        self.allclose(mlab.detrend_mean(input.T, axis=None).T, target)
        self.allclose(mlab.detrend(input), target)
        self.allclose(mlab.detrend(input, axis=None), target)
        self.allclose(
            mlab.detrend(input.T, key="constant", axis=None), target.T)

        input = np.vstack([self.sig_base,
                           self.sig_base + self.sig_off,
                           self.sig_base + self.sig_slope,
                           self.sig_base + self.sig_off + self.sig_slope])
        target = np.vstack([self.sig_base,
                            self.sig_base,
                            self.sig_base + self.sig_slope_mean,
                            self.sig_base + self.sig_slope_mean])
        self.allclose(mlab.detrend_mean(input.T, axis=0), target.T)
        self.allclose(mlab.detrend_mean(input, axis=1), target)
        self.allclose(mlab.detrend_mean(input, axis=-1), target)
        self.allclose(mlab.detrend(input, key="default", axis=1), target)
        self.allclose(mlab.detrend(input.T, key="mean", axis=0), target.T)
        self.allclose(
            mlab.detrend(input.T, key=mlab.detrend_mean, axis=0), target.T)

    def test_detrend_ValueError(self):
        for signal, kwargs in [
                (self.sig_slope[np.newaxis], {"key": "spam"}),
                (self.sig_slope[np.newaxis], {"key": 5}),
                (5.5, {"axis": 0}),
                (self.sig_slope, {"axis": 1}),
                (self.sig_slope[np.newaxis], {"axis": 2}),
        ]:
            with pytest.raises(ValueError):
                mlab.detrend(signal, **kwargs)

    def test_detrend_mean_ValueError(self):
        for signal, kwargs in [
                (5.5, {"axis": 0}),
                (self.sig_slope, {"axis": 1}),
                (self.sig_slope[np.newaxis], {"axis": 2}),
        ]:
            with pytest.raises(ValueError):
                mlab.detrend_mean(signal, **kwargs)

    def test_detrend_linear(self):
        # 0D.
        assert mlab.detrend_linear(0.) == 0.
        assert mlab.detrend_linear(5.5) == 0.
        assert mlab.detrend(5.5, key="linear") == 0.
        assert mlab.detrend(5.5, key=mlab.detrend_linear) == 0.
        for sig in [  # 1D.
                self.sig_off,
                self.sig_slope,
                self.sig_slope + self.sig_off,
        ]:
            self.allclose(mlab.detrend_linear(sig), self.sig_zeros)

    def test_detrend_str_linear_1d(self):
        input = self.sig_slope + self.sig_off
        target = self.sig_zeros
        self.allclose(mlab.detrend(input, key="linear"), target)
        self.allclose(mlab.detrend(input, key=mlab.detrend_linear), target)
        self.allclose(mlab.detrend_linear(input.tolist()), target)

    def test_detrend_linear_2d(self):
        input = np.vstack([self.sig_off,
                           self.sig_slope,
                           self.sig_slope + self.sig_off])
        target = np.vstack([self.sig_zeros,
                            self.sig_zeros,
                            self.sig_zeros])
        self.allclose(
            mlab.detrend(input.T, key="linear", axis=0), target.T)
        self.allclose(
            mlab.detrend(input.T, key=mlab.detrend_linear, axis=0), target.T)
        self.allclose(
            mlab.detrend(input, key="linear", axis=1), target)
        self.allclose(
            mlab.detrend(input, key=mlab.detrend_linear, axis=1), target)

        with pytest.raises(ValueError):
            mlab.detrend_linear(self.sig_slope[np.newaxis])


@pytest.mark.parametrize('iscomplex', [False, True],
                         ids=['real', 'complex'], scope='class')
@pytest.mark.parametrize('sides', ['onesided', 'twosided', 'default'],
                         scope='class')
@pytest.mark.parametrize(
    'fstims,len_x,NFFT_density,nover_density,pad_to_density,pad_to_spectrum',
    [
        ([], None, -1, -1, -1, -1),
        ([4], None, -1, -1, -1, -1),
        ([4, 5, 10], None, -1, -1, -1, -1),
        ([], None, None, -1, -1, None),
        ([], None, -1, -1, None, None),
        ([], None, None, -1, None, None),
        ([], 1024, 512, -1, -1, 128),
        ([], 256, -1, -1, 33, 257),
        ([], 255, 33, -1, -1, None),
        ([], 256, 128, -1, 256, 256),
        ([], None, -1, 32, -1, -1),
    ],
    ids=[
        'nosig',
        'Fs4',
        'FsAll',
        'nosig_noNFFT',
        'nosig_nopad_to',
        'nosig_noNFFT_no_pad_to',
        'nosig_trim',
        'nosig_odd',
        'nosig_oddlen',
        'nosig_stretch',
        'nosig_overlap',
    ],
    scope='class')
class TestSpectral:
    @pytest.fixture(scope='class', autouse=True)
    def stim(self, request, fstims, iscomplex, sides, len_x, NFFT_density,
             nover_density, pad_to_density, pad_to_spectrum):
        Fs = 100.

        x = np.arange(0, 10, 1 / Fs)
        if len_x is not None:
            x = x[:len_x]

        # get the stimulus frequencies, defaulting to None
        fstims = [Fs / fstim for fstim in fstims]

        # get the constants, default to calculated values
        if NFFT_density is None:
            NFFT_density_real = 256
        elif NFFT_density < 0:
            NFFT_density_real = NFFT_density = 100
        else:
            NFFT_density_real = NFFT_density

        if nover_density is None:
            nover_density_real = 0
        elif nover_density < 0:
            nover_density_real = nover_density = NFFT_density_real // 2
        else:
            nover_density_real = nover_density

        if pad_to_density is None:
            pad_to_density_real = NFFT_density_real
        elif pad_to_density < 0:
            pad_to_density = int(2**np.ceil(np.log2(NFFT_density_real)))
            pad_to_density_real = pad_to_density
        else:
            pad_to_density_real = pad_to_density

        if pad_to_spectrum is None:
            pad_to_spectrum_real = len(x)
        elif pad_to_spectrum < 0:
            pad_to_spectrum_real = pad_to_spectrum = len(x)
        else:
            pad_to_spectrum_real = pad_to_spectrum

        if pad_to_spectrum is None:
            NFFT_spectrum_real = NFFT_spectrum = pad_to_spectrum_real
        else:
            NFFT_spectrum_real = NFFT_spectrum = len(x)
        nover_spectrum = 0

        NFFT_specgram = NFFT_density
        nover_specgram = nover_density
        pad_to_specgram = pad_to_density
        NFFT_specgram_real = NFFT_density_real
        nover_specgram_real = nover_density_real

        if sides == 'onesided' or (sides == 'default' and not iscomplex):
            # frequencies for specgram, psd, and csd
            # need to handle even and odd differently
            if pad_to_density_real % 2:
                freqs_density = np.linspace(0, Fs / 2,
                                            num=pad_to_density_real,
                                            endpoint=False)[::2]
            else:
                freqs_density = np.linspace(0, Fs / 2,
                                            num=pad_to_density_real // 2 + 1)

            # frequencies for complex, magnitude, angle, and phase spectrums
            # need to handle even and odd differently
            if pad_to_spectrum_real % 2:
                freqs_spectrum = np.linspace(0, Fs / 2,
                                             num=pad_to_spectrum_real,
                                             endpoint=False)[::2]
            else:
                freqs_spectrum = np.linspace(0, Fs / 2,
                                             num=pad_to_spectrum_real // 2 + 1)
        else:
            # frequencies for specgram, psd, and csd
            # need to handle even and odd differently
            if pad_to_density_real % 2:
                freqs_density = np.linspace(-Fs / 2, Fs / 2,
                                            num=2 * pad_to_density_real,
                                            endpoint=False)[1::2]
            else:
                freqs_density = np.linspace(-Fs / 2, Fs / 2,
                                            num=pad_to_density_real,
                                            endpoint=False)

            # frequencies for complex, magnitude, angle, and phase spectrums
            # need to handle even and odd differently
            if pad_to_spectrum_real % 2:
                freqs_spectrum = np.linspace(-Fs / 2, Fs / 2,
                                             num=2 * pad_to_spectrum_real,
                                             endpoint=False)[1::2]
            else:
                freqs_spectrum = np.linspace(-Fs / 2, Fs / 2,
                                             num=pad_to_spectrum_real,
                                             endpoint=False)

        freqs_specgram = freqs_density
        # time points for specgram
        t_start = NFFT_specgram_real // 2
        t_stop = len(x) - NFFT_specgram_real // 2 + 1
        t_step = NFFT_specgram_real - nover_specgram_real
        t_specgram = x[t_start:t_stop:t_step]
        if NFFT_specgram_real % 2:
            t_specgram += 1 / Fs / 2
        if len(t_specgram) == 0:
            t_specgram = np.array([NFFT_specgram_real / (2 * Fs)])
        t_spectrum = np.array([NFFT_spectrum_real / (2 * Fs)])
        t_density = t_specgram

        y = np.zeros_like(x)
        for i, fstim in enumerate(fstims):
            y += np.sin(fstim * x * np.pi * 2) * 10**i

        if iscomplex:
            y = y.astype('complex')

        # Interestingly, the instance on which this fixture is called is not
        # the same as the one on which a test is run. So we need to modify the
        # class itself when using a class-scoped fixture.
        cls = request.cls

        cls.Fs = Fs
        cls.sides = sides
        cls.fstims = fstims

        cls.NFFT_density = NFFT_density
        cls.nover_density = nover_density
        cls.pad_to_density = pad_to_density

        cls.NFFT_spectrum = NFFT_spectrum
        cls.nover_spectrum = nover_spectrum
        cls.pad_to_spectrum = pad_to_spectrum

        cls.NFFT_specgram = NFFT_specgram
        cls.nover_specgram = nover_specgram
        cls.pad_to_specgram = pad_to_specgram

        cls.t_specgram = t_specgram
        cls.t_density = t_density
        cls.t_spectrum = t_spectrum
        cls.y = y

        cls.freqs_density = freqs_density
        cls.freqs_spectrum = freqs_spectrum
        cls.freqs_specgram = freqs_specgram

        cls.NFFT_density_real = NFFT_density_real

    def check_freqs(self, vals, targfreqs, resfreqs, fstims):
        assert resfreqs.argmin() == 0
        assert resfreqs.argmax() == len(resfreqs)-1
        assert_allclose(resfreqs, targfreqs, atol=1e-06)
        for fstim in fstims:
            i = np.abs(resfreqs - fstim).argmin()
            assert vals[i] > vals[i+2]
            assert vals[i] > vals[i-2]

    def check_maxfreq(self, spec, fsp, fstims):
        # skip the test if there are no frequencies
        if len(fstims) == 0:
            return

        # if twosided, do the test for each side
        if fsp.min() < 0:
            fspa = np.abs(fsp)
            zeroind = fspa.argmin()
            self.check_maxfreq(spec[:zeroind], fspa[:zeroind], fstims)
            self.check_maxfreq(spec[zeroind:], fspa[zeroind:], fstims)
            return

        fstimst = fstims[:]
        spect = spec.copy()

        # go through each peak and make sure it is correctly the maximum peak
        while fstimst:
            maxind = spect.argmax()
            maxfreq = fsp[maxind]
            assert_almost_equal(maxfreq, fstimst[-1])
            del fstimst[-1]
            spect[maxind-5:maxind+5] = 0

    def test_spectral_helper_raises(self):
        # We don't use parametrize here to handle ``y = self.y``.
        for kwargs in [  # Various error conditions:
            {"y": self.y+1, "mode": "complex"},  # Modes requiring ``x is y``.
            {"y": self.y+1, "mode": "magnitude"},
            {"y": self.y+1, "mode": "angle"},
            {"y": self.y+1, "mode": "phase"},
            {"mode": "spam"},  # Bad mode.
            {"y": self.y, "sides": "eggs"},  # Bad sides.
            {"y": self.y, "NFFT": 10, "noverlap": 20},  # noverlap > NFFT.
            {"NFFT": 10, "noverlap": 10},  # noverlap == NFFT.
            {"y": self.y, "NFFT": 10,
             "window": np.ones(9)},  # len(win) != NFFT.
        ]:
            with pytest.raises(ValueError):
                mlab._spectral_helper(x=self.y, **kwargs)

    @pytest.mark.parametrize('mode', ['default', 'psd'])
    def test_single_spectrum_helper_unsupported_modes(self, mode):
        with pytest.raises(ValueError):
            mlab._single_spectrum_helper(x=self.y, mode=mode)

    @pytest.mark.parametrize("mode, case", [
        ("psd", "density"),
        ("magnitude", "specgram"),
        ("magnitude", "spectrum"),
    ])
    def test_spectral_helper_psd(self, mode, case):
        freqs = getattr(self, f"freqs_{case}")
        spec, fsp, t = mlab._spectral_helper(
            x=self.y, y=self.y,
            NFFT=getattr(self, f"NFFT_{case}"),
            Fs=self.Fs,
            noverlap=getattr(self, f"nover_{case}"),
            pad_to=getattr(self, f"pad_to_{case}"),
            sides=self.sides,
            mode=mode)

        assert_allclose(fsp, freqs, atol=1e-06)
        assert_allclose(t, getattr(self, f"t_{case}"), atol=1e-06)
        assert spec.shape[0] == freqs.shape[0]
        assert spec.shape[1] == getattr(self, f"t_{case}").shape[0]

    def test_csd(self):
        freqs = self.freqs_density
        spec, fsp = mlab.csd(x=self.y, y=self.y+1,
                             NFFT=self.NFFT_density,
                             Fs=self.Fs,
                             noverlap=self.nover_density,
                             pad_to=self.pad_to_density,
                             sides=self.sides)
        assert_allclose(fsp, freqs, atol=1e-06)
        assert spec.shape == freqs.shape

    def test_csd_padding(self):
        """Test zero padding of csd()."""
        if self.NFFT_density is None:  # for derived classes
            return
        sargs = dict(x=self.y, y=self.y+1, Fs=self.Fs, window=mlab.window_none,
                     sides=self.sides)

        spec0, _ = mlab.csd(NFFT=self.NFFT_density, **sargs)
        spec1, _ = mlab.csd(NFFT=self.NFFT_density*2, **sargs)
        assert_almost_equal(np.sum(np.conjugate(spec0)*spec0).real,
                            np.sum(np.conjugate(spec1/2)*spec1/2).real)

    def test_psd(self):
        freqs = self.freqs_density
        spec, fsp = mlab.psd(x=self.y,
                             NFFT=self.NFFT_density,
                             Fs=self.Fs,
                             noverlap=self.nover_density,
                             pad_to=self.pad_to_density,
                             sides=self.sides)
        assert spec.shape == freqs.shape
        self.check_freqs(spec, freqs, fsp, self.fstims)

    @pytest.mark.parametrize(
        'make_data, detrend',
        [(np.zeros, mlab.detrend_mean), (np.zeros, 'mean'),
         (np.arange, mlab.detrend_linear), (np.arange, 'linear')])
    def test_psd_detrend(self, make_data, detrend):
        if self.NFFT_density is None:
            return
        ydata = make_data(self.NFFT_density)
        ydata1 = ydata+5
        ydata2 = ydata+3.3
        ydata = np.vstack([ydata1, ydata2])
        ydata = np.tile(ydata, (20, 1))
        ydatab = ydata.T.flatten()
        ydata = ydata.flatten()
        ycontrol = np.zeros_like(ydata)
        spec_g, fsp_g = mlab.psd(x=ydata,
                                 NFFT=self.NFFT_density,
                                 Fs=self.Fs,
                                 noverlap=0,
                                 sides=self.sides,
                                 detrend=detrend)
        spec_b, fsp_b = mlab.psd(x=ydatab,
                                 NFFT=self.NFFT_density,
                                 Fs=self.Fs,
                                 noverlap=0,
                                 sides=self.sides,
                                 detrend=detrend)
        spec_c, fsp_c = mlab.psd(x=ycontrol,
                                 NFFT=self.NFFT_density,
                                 Fs=self.Fs,
                                 noverlap=0,
                                 sides=self.sides)
        assert_array_equal(fsp_g, fsp_c)
        assert_array_equal(fsp_b, fsp_c)
        assert_allclose(spec_g, spec_c, atol=1e-08)
        # these should not be almost equal
        with pytest.raises(AssertionError):
            assert_allclose(spec_b, spec_c, atol=1e-08)

    def test_psd_window_hanning(self):
        if self.NFFT_density is None:
            return
        ydata = np.arange(self.NFFT_density)
        ydata1 = ydata+5
        ydata2 = ydata+3.3
        windowVals = mlab.window_hanning(np.ones_like(ydata1))
        ycontrol1 = ydata1 * windowVals
        ycontrol2 = mlab.window_hanning(ydata2)
        ydata = np.vstack([ydata1, ydata2])
        ycontrol = np.vstack([ycontrol1, ycontrol2])
        ydata = np.tile(ydata, (20, 1))
        ycontrol = np.tile(ycontrol, (20, 1))
        ydatab = ydata.T.flatten()
        ydataf = ydata.flatten()
        ycontrol = ycontrol.flatten()
        spec_g, fsp_g = mlab.psd(x=ydataf,
                                 NFFT=self.NFFT_density,
                                 Fs=self.Fs,
                                 noverlap=0,
                                 sides=self.sides,
                                 window=mlab.window_hanning)
        spec_b, fsp_b = mlab.psd(x=ydatab,
                                 NFFT=self.NFFT_density,
                                 Fs=self.Fs,
                                 noverlap=0,
                                 sides=self.sides,
                                 window=mlab.window_hanning)
        spec_c, fsp_c = mlab.psd(x=ycontrol,
                                 NFFT=self.NFFT_density,
                                 Fs=self.Fs,
                                 noverlap=0,
                                 sides=self.sides,
                                 window=mlab.window_none)
        spec_c *= len(ycontrol1)/(windowVals**2).sum()
        assert_array_equal(fsp_g, fsp_c)
        assert_array_equal(fsp_b, fsp_c)
        assert_allclose(spec_g, spec_c, atol=1e-08)
        # these should not be almost equal
        with pytest.raises(AssertionError):
            assert_allclose(spec_b, spec_c, atol=1e-08)

    def test_psd_window_hanning_detrend_linear(self):
        if self.NFFT_density is None:
            return
        ydata = np.arange(self.NFFT_density)
        ycontrol = np.zeros(self.NFFT_density)
        ydata1 = ydata+5
        ydata2 = ydata+3.3
        ycontrol1 = ycontrol
        ycontrol2 = ycontrol
        windowVals = mlab.window_hanning(np.ones_like(ycontrol1))
        ycontrol1 = ycontrol1 * windowVals
        ycontrol2 = mlab.window_hanning(ycontrol2)
        ydata = np.vstack([ydata1, ydata2])
        ycontrol = np.vstack([ycontrol1, ycontrol2])
        ydata = np.tile(ydata, (20, 1))
        ycontrol = np.tile(ycontrol, (20, 1))
        ydatab = ydata.T.flatten()
        ydataf = ydata.flatten()
        ycontrol = ycontrol.flatten()
        spec_g, fsp_g = mlab.psd(x=ydataf,
                                 NFFT=self.NFFT_density,
                                 Fs=self.Fs,
                                 noverlap=0,
                                 sides=self.sides,
                                 detrend=mlab.detrend_linear,
                                 window=mlab.window_hanning)
        spec_b, fsp_b = mlab.psd(x=ydatab,
                                 NFFT=self.NFFT_density,
                                 Fs=self.Fs,
                                 noverlap=0,
                                 sides=self.sides,
                                 detrend=mlab.detrend_linear,
                                 window=mlab.window_hanning)
        spec_c, fsp_c = mlab.psd(x=ycontrol,
                                 NFFT=self.NFFT_density,
                                 Fs=self.Fs,
                                 noverlap=0,
                                 sides=self.sides,
                                 window=mlab.window_none)
        spec_c *= len(ycontrol1)/(windowVals**2).sum()
        assert_array_equal(fsp_g, fsp_c)
        assert_array_equal(fsp_b, fsp_c)
        assert_allclose(spec_g, spec_c, atol=1e-08)
        # these should not be almost equal
        with pytest.raises(AssertionError):
            assert_allclose(spec_b, spec_c, atol=1e-08)

    def test_psd_window_flattop(self):
        # flattop window
        # adaption from https://github.com/scipy/scipy/blob\
        # /v1.10.0/scipy/signal/windows/_windows.py#L562-L622
        a = [0.21557895, 0.41663158, 0.277263158, 0.083578947, 0.006947368]
        fac = np.linspace(-np.pi, np.pi, self.NFFT_density_real)
        win = np.zeros(self.NFFT_density_real)
        for k in range(len(a)):
            win += a[k] * np.cos(k * fac)

        spec, fsp = mlab.psd(x=self.y,
                             NFFT=self.NFFT_density,
                             Fs=self.Fs,
                             noverlap=0,
                             sides=self.sides,
                             window=win,
                             scale_by_freq=False)
        spec_a, fsp_a = mlab.psd(x=self.y,
                                 NFFT=self.NFFT_density,
                                 Fs=self.Fs,
                                 noverlap=0,
                                 sides=self.sides,
                                 window=win)
        assert_allclose(spec*win.sum()**2,
                        spec_a*self.Fs*(win**2).sum(),
                        atol=1e-08)

    def test_psd_windowarray(self):
        freqs = self.freqs_density
        spec, fsp = mlab.psd(x=self.y,
                             NFFT=self.NFFT_density,
                             Fs=self.Fs,
                             noverlap=self.nover_density,
                             pad_to=self.pad_to_density,
                             sides=self.sides,
                             window=np.ones(self.NFFT_density_real))
        assert_allclose(fsp, freqs, atol=1e-06)
        assert spec.shape == freqs.shape

    def test_psd_windowarray_scale_by_freq(self):
        win = mlab.window_hanning(np.ones(self.NFFT_density_real))

        spec, fsp = mlab.psd(x=self.y,
                             NFFT=self.NFFT_density,
                             Fs=self.Fs,
                             noverlap=self.nover_density,
                             pad_to=self.pad_to_density,
                             sides=self.sides,
                             window=mlab.window_hanning)
        spec_s, fsp_s = mlab.psd(x=self.y,
                                 NFFT=self.NFFT_density,
                                 Fs=self.Fs,
                                 noverlap=self.nover_density,
                                 pad_to=self.pad_to_density,
                                 sides=self.sides,
                                 window=mlab.window_hanning,
                                 scale_by_freq=True)
        spec_n, fsp_n = mlab.psd(x=self.y,
                                 NFFT=self.NFFT_density,
                                 Fs=self.Fs,
                                 noverlap=self.nover_density,
                                 pad_to=self.pad_to_density,
                                 sides=self.sides,
                                 window=mlab.window_hanning,
                                 scale_by_freq=False)
        assert_array_equal(fsp, fsp_s)
        assert_array_equal(fsp, fsp_n)
        assert_array_equal(spec, spec_s)
        assert_allclose(spec_s*(win**2).sum(),
                        spec_n/self.Fs*win.sum()**2,
                        atol=1e-08)

    @pytest.mark.parametrize(
        "kind", ["complex", "magnitude", "angle", "phase"])
    def test_spectrum(self, kind):
        freqs = self.freqs_spectrum
        spec, fsp = getattr(mlab, f"{kind}_spectrum")(
            x=self.y,
            Fs=self.Fs, sides=self.sides, pad_to=self.pad_to_spectrum)
        assert_allclose(fsp, freqs, atol=1e-06)
        assert spec.shape == freqs.shape
        if kind == "magnitude":
            self.check_maxfreq(spec, fsp, self.fstims)
            self.check_freqs(spec, freqs, fsp, self.fstims)

    @pytest.mark.parametrize(
        'kwargs',
        [{}, {'mode': 'default'}, {'mode': 'psd'}, {'mode': 'magnitude'},
         {'mode': 'complex'}, {'mode': 'angle'}, {'mode': 'phase'}])
    def test_specgram(self, kwargs):
        freqs = self.freqs_specgram
        spec, fsp, t = mlab.specgram(x=self.y,
                                     NFFT=self.NFFT_specgram,
                                     Fs=self.Fs,
                                     noverlap=self.nover_specgram,
                                     pad_to=self.pad_to_specgram,
                                     sides=self.sides,
                                     **kwargs)
        if kwargs.get('mode') == 'complex':
            spec = np.abs(spec)
        specm = np.mean(spec, axis=1)

        assert_allclose(fsp, freqs, atol=1e-06)
        assert_allclose(t, self.t_specgram, atol=1e-06)

        assert spec.shape[0] == freqs.shape[0]
        assert spec.shape[1] == self.t_specgram.shape[0]

        if kwargs.get('mode') not in ['complex', 'angle', 'phase']:
            # using a single freq, so all time slices should be about the same
            if np.abs(spec.max()) != 0:
                assert_allclose(
                    np.diff(spec, axis=1).max() / np.abs(spec.max()), 0,
                    atol=1e-02)
        if kwargs.get('mode') not in ['angle', 'phase']:
            self.check_freqs(specm, freqs, fsp, self.fstims)

    def test_specgram_warn_only1seg(self):
        """Warning should be raised if len(x) <= NFFT."""
        with pytest.warns(UserWarning, match="Only one segment is calculated"):
            mlab.specgram(x=self.y, NFFT=len(self.y), Fs=self.Fs)

    def test_psd_csd_equal(self):
        Pxx, freqsxx = mlab.psd(x=self.y,
                                NFFT=self.NFFT_density,
                                Fs=self.Fs,
                                noverlap=self.nover_density,
                                pad_to=self.pad_to_density,
                                sides=self.sides)
        Pxy, freqsxy = mlab.csd(x=self.y, y=self.y,
                                NFFT=self.NFFT_density,
                                Fs=self.Fs,
                                noverlap=self.nover_density,
                                pad_to=self.pad_to_density,
                                sides=self.sides)
        assert_array_almost_equal_nulp(Pxx, Pxy)
        assert_array_equal(freqsxx, freqsxy)

    @pytest.mark.parametrize("mode", ["default", "psd"])
    def test_specgram_auto_default_psd_equal(self, mode):
        """
        Test that mlab.specgram without mode and with mode 'default' and 'psd'
        are all the same.
        """
        speca, freqspeca, ta = mlab.specgram(x=self.y,
                                             NFFT=self.NFFT_specgram,
                                             Fs=self.Fs,
                                             noverlap=self.nover_specgram,
                                             pad_to=self.pad_to_specgram,
                                             sides=self.sides)
        specb, freqspecb, tb = mlab.specgram(x=self.y,
                                             NFFT=self.NFFT_specgram,
                                             Fs=self.Fs,
                                             noverlap=self.nover_specgram,
                                             pad_to=self.pad_to_specgram,
                                             sides=self.sides,
                                             mode=mode)
        assert_array_equal(speca, specb)
        assert_array_equal(freqspeca, freqspecb)
        assert_array_equal(ta, tb)

    @pytest.mark.parametrize(
        "mode, conv", [
            ("magnitude", np.abs),
            ("angle", np.angle),
            ("phase", lambda x: np.unwrap(np.angle(x), axis=0))
        ])
    def test_specgram_complex_equivalent(self, mode, conv):
        specc, freqspecc, tc = mlab.specgram(x=self.y,
                                             NFFT=self.NFFT_specgram,
                                             Fs=self.Fs,
                                             noverlap=self.nover_specgram,
                                             pad_to=self.pad_to_specgram,
                                             sides=self.sides,
                                             mode='complex')
        specm, freqspecm, tm = mlab.specgram(x=self.y,
                                             NFFT=self.NFFT_specgram,
                                             Fs=self.Fs,
                                             noverlap=self.nover_specgram,
                                             pad_to=self.pad_to_specgram,
                                             sides=self.sides,
                                             mode=mode)

        assert_array_equal(freqspecc, freqspecm)
        assert_array_equal(tc, tm)
        assert_allclose(conv(specc), specm, atol=1e-06)

    def test_psd_windowarray_equal(self):
        win = mlab.window_hanning(np.ones(self.NFFT_density_real))
        speca, fspa = mlab.psd(x=self.y,
                               NFFT=self.NFFT_density,
                               Fs=self.Fs,
                               noverlap=self.nover_density,
                               pad_to=self.pad_to_density,
                               sides=self.sides,
                               window=win)
        specb, fspb = mlab.psd(x=self.y,
                               NFFT=self.NFFT_density,
                               Fs=self.Fs,
                               noverlap=self.nover_density,
                               pad_to=self.pad_to_density,
                               sides=self.sides)
        assert_array_equal(fspa, fspb)
        assert_allclose(speca, specb, atol=1e-08)


# extra test for cohere...
def test_cohere():
    N = 1024
    np.random.seed(19680801)
    x = np.random.randn(N)
    # phase offset
    y = np.roll(x, 20)
    # high-freq roll-off
    y = np.convolve(y, np.ones(20) / 20., mode='same')
    cohsq, f = mlab.cohere(x, y, NFFT=256, Fs=2, noverlap=128)
    assert_allclose(np.mean(cohsq), 0.837, atol=1.e-3)
    assert np.isreal(np.mean(cohsq))


# *****************************************************************
# These Tests were taken from SCIPY with some minor modifications
# this can be retrieved from:
# https://github.com/scipy/scipy/blob/master/scipy/stats/tests/test_kdeoth.py
# *****************************************************************

class TestGaussianKDE:

    def test_kde_integer_input(self):
        """Regression test for #1181."""
        x1 = np.arange(5)
        kde = mlab.GaussianKDE(x1)
        y_expected = [0.13480721, 0.18222869, 0.19514935, 0.18222869,
                      0.13480721]
        np.testing.assert_array_almost_equal(kde(x1), y_expected, decimal=6)

    def test_gaussian_kde_covariance_caching(self):
        x1 = np.array([-7, -5, 1, 4, 5], dtype=float)
        xs = np.linspace(-10, 10, num=5)
        # These expected values are from scipy 0.10, before some changes to
        # gaussian_kde. They were not compared with any external reference.
        y_expected = [0.02463386, 0.04689208, 0.05395444, 0.05337754,
                      0.01664475]

        # set it to the default bandwidth.
        kde2 = mlab.GaussianKDE(x1, 'scott')
        y2 = kde2(xs)

        np.testing.assert_array_almost_equal(y_expected, y2, decimal=7)

    def test_kde_bandwidth_method(self):

        np.random.seed(8765678)
        n_basesample = 50
        xn = np.random.randn(n_basesample)

        # Default
        gkde = mlab.GaussianKDE(xn)
        # Supply a callable
        gkde2 = mlab.GaussianKDE(xn, 'scott')
        # Supply a scalar
        gkde3 = mlab.GaussianKDE(xn, bw_method=gkde.factor)

        xs = np.linspace(-7, 7, 51)
        kdepdf = gkde.evaluate(xs)
        kdepdf2 = gkde2.evaluate(xs)
        assert kdepdf.all() == kdepdf2.all()
        kdepdf3 = gkde3.evaluate(xs)
        assert kdepdf.all() == kdepdf3.all()


class TestGaussianKDECustom:
    def test_no_data(self):
        """Pass no data into the GaussianKDE class."""
        with pytest.raises(ValueError):
            mlab.GaussianKDE([])

    def test_single_dataset_element(self):
        """Pass a single dataset element into the GaussianKDE class."""
        with pytest.raises(ValueError):
            mlab.GaussianKDE([42])

    def test_silverman_multidim_dataset(self):
        """Test silverman's for a multi-dimensional array."""
        x1 = np.array([[1, 2, 3], [4, 5, 6], [7, 8, 9]])
        with pytest.raises(np.linalg.LinAlgError):
            mlab.GaussianKDE(x1, "silverman")

    def test_silverman_singledim_dataset(self):
        """Test silverman's output for a single dimension list."""
        x1 = np.array([-7, -5, 1, 4, 5])
        mygauss = mlab.GaussianKDE(x1, "silverman")
        y_expected = 0.76770389927475502
        assert_almost_equal(mygauss.covariance_factor(), y_expected, 7)

    def test_scott_multidim_dataset(self):
        """Test scott's output for a multi-dimensional array."""
        x1 = np.array([[1, 2, 3], [4, 5, 6], [7, 8, 9]])
        with pytest.raises(np.linalg.LinAlgError):
            mlab.GaussianKDE(x1, "scott")

    def test_scott_singledim_dataset(self):
        """Test scott's output a single-dimensional array."""
        x1 = np.array([-7, -5, 1, 4, 5])
        mygauss = mlab.GaussianKDE(x1, "scott")
        y_expected = 0.72477966367769553
        assert_almost_equal(mygauss.covariance_factor(), y_expected, 7)

    def test_scalar_empty_dataset(self):
        """Test the scalar's cov factor for an empty array."""
        with pytest.raises(ValueError):
            mlab.GaussianKDE([], bw_method=5)

    def test_scalar_covariance_dataset(self):
        """Test a scalar's cov factor."""
        np.random.seed(8765678)
        n_basesample = 50
        multidim_data = [np.random.randn(n_basesample) for i in range(5)]

        kde = mlab.GaussianKDE(multidim_data, bw_method=0.5)
        assert kde.covariance_factor() == 0.5

    def test_callable_covariance_dataset(self):
        """Test the callable's cov factor for a multi-dimensional array."""
        np.random.seed(8765678)
        n_basesample = 50
        multidim_data = [np.random.randn(n_basesample) for i in range(5)]

        def callable_fun(x):
            return 0.55
        kde = mlab.GaussianKDE(multidim_data, bw_method=callable_fun)
        assert kde.covariance_factor() == 0.55

    def test_callable_singledim_dataset(self):
        """Test the callable's cov factor for a single-dimensional array."""
        np.random.seed(8765678)
        n_basesample = 50
        multidim_data = np.random.randn(n_basesample)

        kde = mlab.GaussianKDE(multidim_data, bw_method='silverman')
        y_expected = 0.48438841363348911
        assert_almost_equal(kde.covariance_factor(), y_expected, 7)

    def test_wrong_bw_method(self):
        """Test the error message that should be called when bw is invalid."""
        np.random.seed(8765678)
        n_basesample = 50
        data = np.random.randn(n_basesample)
        with pytest.raises(ValueError):
            mlab.GaussianKDE(data, bw_method="invalid")


class TestGaussianKDEEvaluate:

    def test_evaluate_diff_dim(self):
        """
        Test the evaluate method when the dim's of dataset and points have
        different dimensions.
        """
        x1 = np.arange(3, 10, 2)
        kde = mlab.GaussianKDE(x1)
        x2 = np.arange(3, 12, 2)
        y_expected = [
            0.08797252, 0.11774109, 0.11774109, 0.08797252, 0.0370153
        ]
        y = kde.evaluate(x2)
        np.testing.assert_array_almost_equal(y, y_expected, 7)

    def test_evaluate_inv_dim(self):
        """
        Invert the dimensions; i.e., for a dataset of dimension 1 [3, 2, 4],
        the points should have a dimension of 3 [[3], [2], [4]].
        """
        np.random.seed(8765678)
        n_basesample = 50
        multidim_data = np.random.randn(n_basesample)
        kde = mlab.GaussianKDE(multidim_data)
        x2 = [[1], [2], [3]]
        with pytest.raises(ValueError):
            kde.evaluate(x2)

    def test_evaluate_dim_and_num(self):
        """Tests if evaluated against a one by one array"""
        x1 = np.arange(3, 10, 2)
        x2 = np.array([3])
        kde = mlab.GaussianKDE(x1)
        y_expected = [0.08797252]
        y = kde.evaluate(x2)
        np.testing.assert_array_almost_equal(y, y_expected, 7)

    def test_evaluate_point_dim_not_one(self):
        x1 = np.arange(3, 10, 2)
        x2 = [np.arange(3, 10, 2), np.arange(3, 10, 2)]
        kde = mlab.GaussianKDE(x1)
        with pytest.raises(ValueError):
            kde.evaluate(x2)

    def test_evaluate_equal_dim_and_num_lt(self):
        x1 = np.arange(3, 10, 2)
        x2 = np.arange(3, 8, 2)
        kde = mlab.GaussianKDE(x1)
        y_expected = [0.08797252, 0.11774109, 0.11774109]
        y = kde.evaluate(x2)
        np.testing.assert_array_almost_equal(y, y_expected, 7)


def test_psd_onesided_norm():
    u = np.array([0, 1, 2, 3, 1, 2, 1])
    dt = 1.0
    Su = np.abs(np.fft.fft(u) * dt)**2 / (dt * u.size)
    P, f = mlab.psd(u, NFFT=u.size, Fs=1/dt, window=mlab.window_none,
                    detrend=mlab.detrend_none, noverlap=0, pad_to=None,
                    scale_by_freq=None,
                    sides='onesided')
    Su_1side = np.append([Su[0]], Su[1:4] + Su[4:][::-1])
    assert_allclose(P, Su_1side, atol=1e-06)


def test_psd_oversampling():
    """Test the case len(x) < NFFT for psd()."""
    u = np.array([0, 1, 2, 3, 1, 2, 1])
    dt = 1.0
    Su = np.abs(np.fft.fft(u) * dt)**2 / (dt * u.size)
    P, f = mlab.psd(u, NFFT=u.size*2, Fs=1/dt, window=mlab.window_none,
                    detrend=mlab.detrend_none, noverlap=0, pad_to=None,
                    scale_by_freq=None,
                    sides='onesided')
    Su_1side = np.append([Su[0]], Su[1:4] + Su[4:][::-1])
    assert_almost_equal(np.sum(P), np.sum(Su_1side))  # same energy
