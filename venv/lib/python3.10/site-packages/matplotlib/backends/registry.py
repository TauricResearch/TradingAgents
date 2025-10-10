from enum import Enum
import importlib


class BackendFilter(Enum):
    """
    Filter used with :meth:`~matplotlib.backends.registry.BackendRegistry.list_builtin`

    .. versionadded:: 3.9
    """
    INTERACTIVE = 0
    NON_INTERACTIVE = 1


class BackendRegistry:
    """
    Registry of backends available within Matplotlib.

    This is the single source of truth for available backends.

    All use of ``BackendRegistry`` should be via the singleton instance
    ``backend_registry`` which can be imported from ``matplotlib.backends``.

    Each backend has a name, a module name containing the backend code, and an
    optional GUI framework that must be running if the backend is interactive.
    There are three sources of backends: built-in (source code is within the
    Matplotlib repository), explicit ``module://some.backend`` syntax (backend is
    obtained by loading the module), or via an entry point (self-registering
    backend in an external package).

    .. versionadded:: 3.9
    """
    # Mapping of built-in backend name to GUI framework, or "headless" for no
    # GUI framework. Built-in backends are those which are included in the
    # Matplotlib repo. A backend with name 'name' is located in the module
    # f"matplotlib.backends.backend_{name.lower()}"
    _BUILTIN_BACKEND_TO_GUI_FRAMEWORK = {
        "gtk3agg": "gtk3",
        "gtk3cairo": "gtk3",
        "gtk4agg": "gtk4",
        "gtk4cairo": "gtk4",
        "macosx": "macosx",
        "nbagg": "nbagg",
        "notebook": "nbagg",
        "qtagg": "qt",
        "qtcairo": "qt",
        "qt5agg": "qt5",
        "qt5cairo": "qt5",
        "tkagg": "tk",
        "tkcairo": "tk",
        "webagg": "webagg",
        "wx": "wx",
        "wxagg": "wx",
        "wxcairo": "wx",
        "agg": "headless",
        "cairo": "headless",
        "pdf": "headless",
        "pgf": "headless",
        "ps": "headless",
        "svg": "headless",
        "template": "headless",
    }

    # Reverse mapping of gui framework to preferred built-in backend.
    _GUI_FRAMEWORK_TO_BACKEND = {
        "gtk3": "gtk3agg",
        "gtk4": "gtk4agg",
        "headless": "agg",
        "macosx": "macosx",
        "qt": "qtagg",
        "qt5": "qt5agg",
        "qt6": "qtagg",
        "tk": "tkagg",
        "wx": "wxagg",
    }

    def __init__(self):
        # Only load entry points when first needed.
        self._loaded_entry_points = False

        # Mapping of non-built-in backend to GUI framework, added dynamically from
        # entry points and from matplotlib.use("module://some.backend") format.
        # New entries have an "unknown" GUI framework that is determined when first
        # needed by calling _get_gui_framework_by_loading.
        self._backend_to_gui_framework = {}

        # Mapping of backend name to module name, where different from
        # f"matplotlib.backends.backend_{backend_name.lower()}". These are either
        # hardcoded for backward compatibility, or loaded from entry points or
        # "module://some.backend" syntax.
        self._name_to_module = {
            "notebook": "nbagg",
        }

    def _backend_module_name(self, backend):
        if backend.startswith("module://"):
            return backend[9:]

        # Return name of module containing the specified backend.
        # Does not check if the backend is valid, use is_valid_backend for that.
        backend = backend.lower()

        # Check if have specific name to module mapping.
        backend = self._name_to_module.get(backend, backend)

        return (backend[9:] if backend.startswith("module://")
                else f"matplotlib.backends.backend_{backend}")

    def _clear(self):
        # Clear all dynamically-added data, used for testing only.
        self.__init__()

    def _ensure_entry_points_loaded(self):
        # Load entry points, if they have not already been loaded.
        if not self._loaded_entry_points:
            entries = self._read_entry_points()
            self._validate_and_store_entry_points(entries)
            self._loaded_entry_points = True

    def _get_gui_framework_by_loading(self, backend):
        # Determine GUI framework for a backend by loading its module and reading the
        # FigureCanvas.required_interactive_framework attribute.
        # Returns "headless" if there is no GUI framework.
        module = self.load_backend_module(backend)
        canvas_class = module.FigureCanvas
        return canvas_class.required_interactive_framework or "headless"

    def _read_entry_points(self):
        # Read entry points of modules that self-advertise as Matplotlib backends.
        # Expects entry points like this one from matplotlib-inline (in pyproject.toml
        # format):
        #   [project.entry-points."matplotlib.backend"]
        #   inline = "matplotlib_inline.backend_inline"
        import importlib.metadata as im

        entry_points = im.entry_points(group="matplotlib.backend")
        entries = [(entry.name, entry.value) for entry in entry_points]

        # For backward compatibility, if matplotlib-inline and/or ipympl are installed
        # but too old to include entry points, create them. Do not import ipympl
        # directly as this calls matplotlib.use() whilst in this function.
        def backward_compatible_entry_points(
                entries, module_name, threshold_version, names, target):
            from matplotlib import _parse_to_version_info
            try:
                module_version = im.version(module_name)
                if _parse_to_version_info(module_version) < threshold_version:
                    for name in names:
                        entries.append((name, target))
            except im.PackageNotFoundError:
                pass

        names = [entry[0] for entry in entries]
        if "inline" not in names:
            backward_compatible_entry_points(
                entries, "matplotlib_inline", (0, 1, 7), ["inline"],
                "matplotlib_inline.backend_inline")
        if "ipympl" not in names:
            backward_compatible_entry_points(
                entries, "ipympl", (0, 9, 4), ["ipympl", "widget"],
                "ipympl.backend_nbagg")

        return entries

    def _validate_and_store_entry_points(self, entries):
        # Validate and store entry points so that they can be used via matplotlib.use()
        # in the normal manner. Entry point names cannot be of module:// format, cannot
        # shadow a built-in backend name, and there cannot be multiple entry points
        # with the same name but different modules. Multiple entry points with the same
        # name and value are permitted (it can sometimes happen outside of our control,
        # see https://github.com/matplotlib/matplotlib/issues/28367).
        for name, module in set(entries):
            name = name.lower()
            if name.startswith("module://"):
                raise RuntimeError(
                    f"Entry point name '{name}' cannot start with 'module://'")
            if name in self._BUILTIN_BACKEND_TO_GUI_FRAMEWORK:
                raise RuntimeError(f"Entry point name '{name}' is a built-in backend")
            if name in self._backend_to_gui_framework:
                raise RuntimeError(f"Entry point name '{name}' duplicated")

            self._name_to_module[name] = "module://" + module
            # Do not yet know backend GUI framework, determine it only when necessary.
            self._backend_to_gui_framework[name] = "unknown"

    def backend_for_gui_framework(self, framework):
        """
        Return the name of the backend corresponding to the specified GUI framework.

        Parameters
        ----------
        framework : str
            GUI framework such as "qt".

        Returns
        -------
        str or None
            Backend name or None if GUI framework not recognised.
        """
        return self._GUI_FRAMEWORK_TO_BACKEND.get(framework.lower())

    def is_valid_backend(self, backend):
        """
        Return True if the backend name is valid, False otherwise.

        A backend name is valid if it is one of the built-in backends or has been
        dynamically added via an entry point. Those beginning with ``module://`` are
        always considered valid and are added to the current list of all backends
        within this function.

        Even if a name is valid, it may not be importable or usable. This can only be
        determined by loading and using the backend module.

        Parameters
        ----------
        backend : str
            Name of backend.

        Returns
        -------
        bool
            True if backend is valid, False otherwise.
        """
        if not backend.startswith("module://"):
            backend = backend.lower()

        # For backward compatibility, convert ipympl and matplotlib-inline long
        # module:// names to their shortened forms.
        backwards_compat = {
            "module://ipympl.backend_nbagg": "widget",
            "module://matplotlib_inline.backend_inline": "inline",
        }
        backend = backwards_compat.get(backend, backend)

        if (backend in self._BUILTIN_BACKEND_TO_GUI_FRAMEWORK or
                backend in self._backend_to_gui_framework):
            return True

        if backend.startswith("module://"):
            self._backend_to_gui_framework[backend] = "unknown"
            return True

        # Only load entry points if really need to and not already done so.
        self._ensure_entry_points_loaded()
        if backend in self._backend_to_gui_framework:
            return True

        return False

    def list_all(self):
        """
        Return list of all known backends.

        These include built-in backends and those obtained at runtime either from entry
        points or explicit ``module://some.backend`` syntax.

        Entry points will be loaded if they haven't been already.

        Returns
        -------
        list of str
            Backend names.
        """
        self._ensure_entry_points_loaded()
        return [*self.list_builtin(), *self._backend_to_gui_framework]

    def list_builtin(self, filter_=None):
        """
        Return list of backends that are built into Matplotlib.

        Parameters
        ----------
        filter_ : `~.BackendFilter`, optional
            Filter to apply to returned backends. For example, to return only
            non-interactive backends use `.BackendFilter.NON_INTERACTIVE`.

        Returns
        -------
        list of str
            Backend names.
        """
        if filter_ == BackendFilter.INTERACTIVE:
            return [k for k, v in self._BUILTIN_BACKEND_TO_GUI_FRAMEWORK.items()
                    if v != "headless"]
        elif filter_ == BackendFilter.NON_INTERACTIVE:
            return [k for k, v in self._BUILTIN_BACKEND_TO_GUI_FRAMEWORK.items()
                    if v == "headless"]

        return [*self._BUILTIN_BACKEND_TO_GUI_FRAMEWORK]

    def list_gui_frameworks(self):
        """
        Return list of GUI frameworks used by Matplotlib backends.

        Returns
        -------
        list of str
            GUI framework names.
        """
        return [k for k in self._GUI_FRAMEWORK_TO_BACKEND if k != "headless"]

    def load_backend_module(self, backend):
        """
        Load and return the module containing the specified backend.

        Parameters
        ----------
        backend : str
            Name of backend to load.

        Returns
        -------
        Module
            Module containing backend.
        """
        module_name = self._backend_module_name(backend)
        return importlib.import_module(module_name)

    def resolve_backend(self, backend):
        """
        Return the backend and GUI framework for the specified backend name.

        If the GUI framework is not yet known then it will be determined by loading the
        backend module and checking the ``FigureCanvas.required_interactive_framework``
        attribute.

        This function only loads entry points if they have not already been loaded and
        the backend is not built-in and not of ``module://some.backend`` format.

        Parameters
        ----------
        backend : str or None
            Name of backend, or None to use the default backend.

        Returns
        -------
        backend : str
            The backend name.
        framework : str or None
            The GUI framework, which will be None for a backend that is non-interactive.
        """
        if isinstance(backend, str):
            if not backend.startswith("module://"):
                backend = backend.lower()
        else:  # Might be _auto_backend_sentinel or None
            # Use whatever is already running...
            from matplotlib import get_backend
            backend = get_backend()

        # Is backend already known (built-in or dynamically loaded)?
        gui = (self._BUILTIN_BACKEND_TO_GUI_FRAMEWORK.get(backend) or
               self._backend_to_gui_framework.get(backend))

        # Is backend "module://something"?
        if gui is None and isinstance(backend, str) and backend.startswith("module://"):
            gui = "unknown"

        # Is backend a possible entry point?
        if gui is None and not self._loaded_entry_points:
            self._ensure_entry_points_loaded()
            gui = self._backend_to_gui_framework.get(backend)

        # Backend known but not its gui framework.
        if gui == "unknown":
            gui = self._get_gui_framework_by_loading(backend)
            self._backend_to_gui_framework[backend] = gui

        if gui is None:
            raise RuntimeError(f"'{backend}' is not a recognised backend name")

        return backend, gui if gui != "headless" else None

    def resolve_gui_or_backend(self, gui_or_backend):
        """
        Return the backend and GUI framework for the specified string that may be
        either a GUI framework or a backend name, tested in that order.

        This is for use with the IPython %matplotlib magic command which may be a GUI
        framework such as ``%matplotlib qt`` or a backend name such as
        ``%matplotlib qtagg``.

        This function only loads entry points if they have not already been loaded and
        the backend is not built-in and not of ``module://some.backend`` format.

        Parameters
        ----------
        gui_or_backend : str or None
            Name of GUI framework or backend, or None to use the default backend.

        Returns
        -------
        backend : str
            The backend name.
        framework : str or None
            The GUI framework, which will be None for a backend that is non-interactive.
        """
        if not gui_or_backend.startswith("module://"):
            gui_or_backend = gui_or_backend.lower()

        # First check if it is a gui loop name.
        backend = self.backend_for_gui_framework(gui_or_backend)
        if backend is not None:
            return backend, gui_or_backend if gui_or_backend != "headless" else None

        # Then check if it is a backend name.
        try:
            return self.resolve_backend(gui_or_backend)
        except Exception:  # KeyError ?
            raise RuntimeError(
                f"'{gui_or_backend}' is not a recognised GUI loop or backend name")


# Singleton
backend_registry = BackendRegistry()
