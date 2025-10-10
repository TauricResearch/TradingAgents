import os
import argparse
import logging
import shutil
import multiprocessing as mp
from contextlib import closing
from functools import partial

import fontTools
from .ufo import font_to_quadratic, fonts_to_quadratic

ufo_module = None
try:
    import ufoLib2 as ufo_module
except ImportError:
    try:
        import defcon as ufo_module
    except ImportError as e:
        pass


logger = logging.getLogger("fontTools.cu2qu")


def _cpu_count():
    try:
        return mp.cpu_count()
    except NotImplementedError:  # pragma: no cover
        return 1


def open_ufo(path):
    if hasattr(ufo_module.Font, "open"):  # ufoLib2
        return ufo_module.Font.open(path)
    return ufo_module.Font(path)  # defcon


def _font_to_quadratic(input_path, output_path=None, **kwargs):
    ufo = open_ufo(input_path)
    logger.info("Converting curves for %s", input_path)
    if font_to_quadratic(ufo, **kwargs):
        logger.info("Saving %s", output_path)
        if output_path:
            ufo.save(output_path)
        else:
            ufo.save()  # save in-place
    elif output_path:
        _copytree(input_path, output_path)


def _samepath(path1, path2):
    # TODO on python3+, there's os.path.samefile
    path1 = os.path.normcase(os.path.abspath(os.path.realpath(path1)))
    path2 = os.path.normcase(os.path.abspath(os.path.realpath(path2)))
    return path1 == path2


def _copytree(input_path, output_path):
    if _samepath(input_path, output_path):
        logger.debug("input and output paths are the same file; skipped copy")
        return
    if os.path.exists(output_path):
        shutil.rmtree(output_path)
    shutil.copytree(input_path, output_path)


def _main(args=None):
    """Convert a UFO font from cubic to quadratic curves"""
    parser = argparse.ArgumentParser(prog="cu2qu")
    parser.add_argument("--version", action="version", version=fontTools.__version__)
    parser.add_argument(
        "infiles",
        nargs="+",
        metavar="INPUT",
        help="one or more input UFO source file(s).",
    )
    parser.add_argument("-v", "--verbose", action="count", default=0)
    parser.add_argument(
        "-e",
        "--conversion-error",
        type=float,
        metavar="ERROR",
        default=None,
        help="maxiumum approximation error measured in EM (default: 0.001)",
    )
    parser.add_argument(
        "-m",
        "--mixed",
        default=False,
        action="store_true",
        help="whether to used mixed quadratic and cubic curves",
    )
    parser.add_argument(
        "--keep-direction",
        dest="reverse_direction",
        action="store_false",
        help="do not reverse the contour direction",
    )

    mode_parser = parser.add_mutually_exclusive_group()
    mode_parser.add_argument(
        "-i",
        "--interpolatable",
        action="store_true",
        help="whether curve conversion should keep interpolation compatibility",
    )
    mode_parser.add_argument(
        "-j",
        "--jobs",
        type=int,
        nargs="?",
        default=1,
        const=_cpu_count(),
        metavar="N",
        help="Convert using N multiple processes (default: %(default)s)",
    )

    output_parser = parser.add_mutually_exclusive_group()
    output_parser.add_argument(
        "-o",
        "--output-file",
        default=None,
        metavar="OUTPUT",
        help=(
            "output filename for the converted UFO. By default fonts are "
            "modified in place. This only works with a single input."
        ),
    )
    output_parser.add_argument(
        "-d",
        "--output-dir",
        default=None,
        metavar="DIRECTORY",
        help="output directory where to save converted UFOs",
    )

    options = parser.parse_args(args)

    if ufo_module is None:
        parser.error("Either ufoLib2 or defcon are required to run this script.")

    if not options.verbose:
        level = "WARNING"
    elif options.verbose == 1:
        level = "INFO"
    else:
        level = "DEBUG"
    logging.basicConfig(level=level)

    if len(options.infiles) > 1 and options.output_file:
        parser.error("-o/--output-file can't be used with multile inputs")

    if options.output_dir:
        output_dir = options.output_dir
        if not os.path.exists(output_dir):
            os.mkdir(output_dir)
        elif not os.path.isdir(output_dir):
            parser.error("'%s' is not a directory" % output_dir)
        output_paths = [
            os.path.join(output_dir, os.path.basename(p)) for p in options.infiles
        ]
    elif options.output_file:
        output_paths = [options.output_file]
    else:
        # save in-place
        output_paths = [None] * len(options.infiles)

    kwargs = dict(
        dump_stats=options.verbose > 0,
        max_err_em=options.conversion_error,
        reverse_direction=options.reverse_direction,
        all_quadratic=False if options.mixed else True,
    )

    if options.interpolatable:
        logger.info("Converting curves compatibly")
        ufos = [open_ufo(infile) for infile in options.infiles]
        if fonts_to_quadratic(ufos, **kwargs):
            for ufo, output_path in zip(ufos, output_paths):
                logger.info("Saving %s", output_path)
                if output_path:
                    ufo.save(output_path)
                else:
                    ufo.save()
        else:
            for input_path, output_path in zip(options.infiles, output_paths):
                if output_path:
                    _copytree(input_path, output_path)
    else:
        jobs = min(len(options.infiles), options.jobs) if options.jobs > 1 else 1
        if jobs > 1:
            func = partial(_font_to_quadratic, **kwargs)
            logger.info("Running %d parallel processes", jobs)
            with closing(mp.Pool(jobs)) as pool:
                pool.starmap(func, zip(options.infiles, output_paths))
        else:
            for input_path, output_path in zip(options.infiles, output_paths):
                _font_to_quadratic(input_path, output_path, **kwargs)
