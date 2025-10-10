# _build_config.py.in is converted into _build_config.py during the meson build process.

from __future__ import annotations


def build_config() -> dict[str, str]:
    """
    Return a dictionary containing build configuration settings.

    All dictionary keys and values are strings, for example ``False`` is
    returned as ``"False"``.

        .. versionadded:: 1.1.0
    """
    return dict(
        # Python settings
        python_version="3.10",
        python_install_dir=r"/usr/local/lib/python3.10/site-packages/",
        python_path=r"/private/var/folders/qn/7t0vq3ts721cmgt0tgrtgzl80000gn/T/build-env-mn4etw2n/bin/python",

        # Package versions
        contourpy_version="1.3.2",
        meson_version="1.7.2",
        mesonpy_version="0.17.1",
        pybind11_version="2.13.6",

        # Misc meson settings
        meson_backend="ninja",
        build_dir=r"/Users/runner/work/contourpy/contourpy/.mesonpy-a241s0qn/lib/contourpy/util",
        source_dir=r"/Users/runner/work/contourpy/contourpy/lib/contourpy/util",
        cross_build="False",

        # Build options
        build_options=r"-Dbuildtype=release -Db_ndebug=if-release -Db_vscrt=md -Dvsenv=True --native-file=/Users/runner/work/contourpy/contourpy/.mesonpy-a241s0qn/meson-python-native-file.ini",
        buildtype="release",
        cpp_std="c++17",
        debug="False",
        optimization="3",
        vsenv="True",
        b_ndebug="if-release",
        b_vscrt="from_buildtype",

        # C++ compiler
        compiler_name="clang",
        compiler_version="15.0.0",
        linker_id="ld64",
        compile_command="c++",

        # Host machine
        host_cpu="aarch64",
        host_cpu_family="aarch64",
        host_cpu_endian="little",
        host_cpu_system="darwin",

        # Build machine, same as host machine if not a cross_build
        build_cpu="aarch64",
        build_cpu_family="aarch64",
        build_cpu_endian="little",
        build_cpu_system="darwin",
    )
