# OpenShot Qt Project Guidelines

## Architecture

- This repository is the Python/Qt application layer. Media processing and core editing primitives are provided by the separately built `libopenshot` and `libopenshot-audio` C++ libraries; Python code imports the `openshot` bindings.
- `src/launch.py` initializes native dependencies, configures Qt, and starts the desktop application or dispatches the CLI. Keep native-library and Qt initialization order intact.
- `src/classes/project_data.py` and `src/classes/json_data.py` own project data and JSON persistence. `src/classes/updates.py` coordinates change notifications and undo/redo; the main window, models, and views consume these updates.
- The Qt UI is primarily in `src/windows/`, with Qt models in `src/windows/models/`, views in `src/windows/views/`, and the modular timeline widget in `src/windows/views/timeline_backend/`. Designer forms and their resources are kept alongside the UI code in `src/windows/ui/`.

## Build and Test

- Run the editor when its Python, Qt, and native `libopenshot` dependencies are installed: `python3 src/launch.py`.
- Run the complete CI unit-test suite headlessly: `QT_QPA_PLATFORM=offscreen python3 -m unittest discover -s src/tests -t src/tests --quiet`.
- Run one test module: `QT_QPA_PLATFORM=offscreen PYTHONPATH=src python3 -m unittest tests.test_project_data -v`.
- Run one test case: `QT_QPA_PLATFORM=offscreen PYTHONPATH=src python3 -m unittest tests.test_project_data.ProjectDataTests.test_new_project_uses_default_track_count -v`.
- Build the HTML documentation: `cd doc && make html`.
- CI also checks the installed package layout with `python3 setup.py build --build-base build/package-tests`, then runs `python3 -m unittest discover --quiet` from `build/package-tests/lib`.

## Conventions

- Import Qt APIs through `src/qt_api.py`, not directly from PyQt or PySide. Use this compatibility layer (and helpers in `src/classes/qt_types.py`) for binding differences; `OPENSHOT_QT_API` can select `auto`, `pyqt6`, `pyside6`, or `pyqt5`.
- Qt tests run across multiple bindings. Set `QT_QPA_PLATFORM=offscreen` for headless runs, and use `src/tests/qt_test_app.py` when a test needs a shared `QApplication`; do not quit the shared application in individual test teardown.
- Keep application UI translations under `src/language/` and documentation translations under `doc/locale/`; their gettext workflows are separate. See [doc/README.md](../doc/README.md) for documentation translation commands.
