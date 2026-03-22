# Changelog

Framesync adheres to [Semantic Versioning](http://semver.org/).

## [6.1.2] 2022-08-15

### Update

-   `tslib` and `typescript`.

## [6.1.1] 2022-08-10

### Update

-   Adding `types` to `exports` field.

## [6.1.0] 2021-11-24

### Update

-   Updating `tslib`.

## [6.0.1] 2021-10-22

### Fixed

-   Fixing bug where `flushSync` being called from an existing process would boot keep-alive processes off the thread.

## [6.0.0] 2021-09-23

### Fixed

-   Fixing `exports` and `module` in `package.json`. This will break (unsupported) direct file imports.

## [5.3.0] 2021-03-30

### Added

-   Adding `flushSync` API for manual flushing of job queues.

## [5.2.3] 2021-03-19

### Fixed

-   Fixing `main` entry point.

## [5.2.2] 2021-03-19

### Fixed

-   Fixing `main` entry point.

## [5.2.1] 2021-03-19

### Added

-   Adding `exports` to `package.json`.

### Updated

-   `tslib` to latest.

## [5.2.0] 2021-03-01

### Fixed

-   Unbundling ES code to facilitate code-splitting in Webpack.

## [5.1.0] 2021-02-22

### Fixed

-   Adding polyfill for `performance.now` for better compatibility with Node environments.

## [5.0.0] 2021-01-01

### Changed

-   Using `performance.now` to measure polyfilled elapsed time.

## [4.1.0] 2020-8-24

### Added

-   `preRender` step.

## [4.0.2] 2019-02-05

### Fixed

-   Fixing rescheduling keepAlive method.

## [4.0.1] 2018-09-24

### Changed

-   Updated README.

## [4.0.0] 2018-09-24

### Changed

-   New API.
    -   `onFrameUpdate(callback, immediate)` -> `sync.update(callback, keepAlive, immediate)`
    -   `cancelOnFrameUpdate(callback)` -> `cancelSync.update(callback)`

### Added

-   `keepAlive` parameter.

## [3.1.9] 2018-05-16

### Fixed

-   Fixing Rollup config.

## [3.1.8] 2018-05-13

### Added

-   Rollup support for outputting ES modules and UMD bundles.

## [3.1.7] 2018-01-04

### Fixed

-   Fixing illegal invocation errors.

## [3.1.6] 2018-01-04

### Changed

-   Using previous frame duration as default duration (for instance between active cycles).

## [3.1.5] 2018-01-04

### Changed

-   Cleaning polyfill.

## [3.1.4] 2018-01-04

### Changed

-   Max permitted time elapsed is now 40ms to permit 30fps max.
-   When `startRenderLoop` is fired, and the loop is not active, we set a new `currentTime`.

## [3.1.3] 2017-11-08

### Fixed

-   Actually pointing to new declaration file.

## [3.1.2] 2017-11-08

### Fixed

-   Pointing to new declaration file.

## [3.1.1] 2017-11-08

### Fixed

-   Automatically exporting declaration file.

## [3.1.0] 2017-11-08

### Added

-   Added optional `true` flag to `schedule`. This will schedule a job to run at the end of the current frame step.

## [3.0.0] 2017-08-28

-   `currentFrameTimestamp` becomes `currentFrameTime` for symmetry with `currentTime`.

## [2.0.1] 2017-08-26

### Added

-   Changelog and Readme.

## [2.0.0] 2017-08-26

### Added

-   First publish.
