# Visible Layers Only — QGIS plugin

<img src="visible_layers_only/icons/visible_on.png" width="64" alt="On"> <img src="visible_layers_only/icons/visible_off.png" width="64" alt="Off">

Adds a toggle button to the toolbar of the QGIS **Layers** panel. When enabled, the panel lists only the layers that are currently visible on the map canvas.

- Layers whose checkbox (or any parent group's checkbox) is off are hidden from the panel.
- Groups without any visible layer inside are hidden too.
- It only changes what the panel *displays* — layer visibility, order and project contents are never modified. Drag & drop, context menus and indicators keep working.
- The button icon reflects the state (colour + open eye = filtering, grey + slashed eye = showing all), and the state is remembered between sessions.

Compatible with **QGIS 3.x (Qt5)** and **QGIS 4.x (Qt6)**.

## Install

1. Download `visible_layers_only-<version>.zip` from the [latest release](https://github.com/danzig666/qgis-visible-layers-only/releases/latest).
2. In QGIS: **Plugins → Manage and Install Plugins… → Install from ZIP**, pick the zip, click **Install Plugin**.

Or copy the `visible_layers_only` folder into your profile's `python/plugins` folder (e.g. `%APPDATA%\QGIS\QGIS3\profiles\default\python\plugins` on Windows) and enable it in the Plugin Manager.

## Usage

Click the eye/layers button at the right end of the Layers panel toolbar (left of *Remove Layer*). Click again to show all layers.

Note: while the filter is on, unchecking a layer makes it disappear from the panel immediately; turn the filter off to see it again.

## License

GPL-2.0-or-later — see [LICENSE](LICENSE).
