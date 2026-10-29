"""Filter the *display* of the QGIS Layers panel without changing layer state.

The native layer tree model stays in place. We use QTreeView.setRowHidden()
instead of replacing the model, so QGIS's built-in drag/drop, context menus,
indicators, selection and legend continue to work normally.

Compatible with QGIS 3.x (Qt5 / PyQt5) and QGIS 4.x (Qt6 / PyQt6).
"""

import os

from qgis.PyQt.QtCore import QPersistentModelIndex, QTimer
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QDockWidget, QToolBar
from qgis.core import QgsLayerTreeGroup, QgsLayerTreeLayer, QgsSettings

try:  # Qt6: QAction lives in QtGui
    from qgis.PyQt.QtGui import QAction
except ImportError:  # Qt5: QAction lives in QtWidgets
    from qgis.PyQt.QtWidgets import QAction


ICON_DIR = os.path.join(os.path.dirname(__file__), "icons")
SETTINGS_KEY = "visible_layers_only/enabled"


class VisibleLayersOnlyPlugin:
    """A checkable button in the native Layers panel toolbar."""

    def __init__(self, iface):
        self.iface = iface
        self.view = None
        self.model = None
        self.toolbar = None
        self.action = None
        self.timer = None
        self.icon_on = None
        self.icon_off = None
        self._signals = []
        # The view may already hide rows for other reasons/plugins. Track ONLY
        # the rows hidden by this plugin and restore ONLY those rows.
        # Persistent indexes follow rows across insertions and reordering.
        self._hidden_rows = []

    # ------------------------------------------------------------------ setup

    def initGui(self):
        self.view = self.iface.layerTreeView()
        self.model = self.view.layerTreeModel()

        self.icon_on = self._load_icon("visible_on")
        self.icon_off = self._load_icon("visible_off")

        self.action = QAction(self.icon_off, "Show only visible layers", self.iface.mainWindow())
        self.action.setObjectName("visible_layers_only_filter_action")
        self.action.setCheckable(True)
        self.action.setToolTip(
            "Show only visible layers in this panel\n"
            "Does not change layer visibility or project contents"
        )
        self.action.toggled.connect(self._on_toggled)

        self.toolbar = self._find_layers_toolbar()
        if self.toolbar is not None:
            # Insert just before the native Remove Layer button (right-hand end).
            native_actions = self.toolbar.actions()
            if native_actions:
                self.toolbar.insertAction(native_actions[-1], self.action)
            else:
                self.toolbar.addAction(self.action)
        else:
            # Fallback: keep the feature reachable even if the panel layout changed.
            self.iface.addToolBarIcon(self.action)

        # Queue refreshes until the layer model has finished inserting/removing
        # rows. A zero-delay single-shot timer coalesces bursts of signals.
        self.timer = QTimer(self.iface.mainWindow())
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self._apply_filter)

        # Visibility checkboxes are reported through the model, which covers
        # every change made in the panel, by map themes or by other code.
        for signal in (
            self.model.dataChanged,
            self.model.rowsInserted,
            self.model.rowsRemoved,
            self.model.modelReset,
            self.model.layoutChanged,
        ):
            signal.connect(self._schedule_update)
            self._signals.append(signal)

        # QTreeView forgets hidden rows when the view's model is reset; the
        # proxy model (QGIS >= 3.18) may reset independently of the source.
        view_model = self.view.model()
        if view_model is not None and view_model is not self.model:
            for signal in (view_model.modelReset, view_model.layoutChanged):
                signal.connect(self._schedule_update)
                self._signals.append(signal)

        self.action.setChecked(QgsSettings().value(SETTINGS_KEY, False, type=bool))

    def _find_layers_toolbar(self):
        # "Layers" is the objectName assigned by QGIS to its Layers dock.
        dock = self.iface.mainWindow().findChild(QDockWidget, "Layers")
        if dock is not None:
            toolbar = dock.findChild(QToolBar)
            if toolbar is not None:
                return toolbar
        # Last resort: the toolbar whose parent chain contains the layer view.
        parent = self.view.parentWidget()
        while parent is not None:
            toolbar = parent.findChild(QToolBar)
            if toolbar is not None:
                return toolbar
            parent = parent.parentWidget()
        return None

    @staticmethod
    def _load_icon(name):
        # Prefer the generated PNG artwork; the SVGs are a vector fallback.
        for ext in (".png", ".svg"):
            path = os.path.join(ICON_DIR, name + ext)
            if os.path.exists(path):
                return QIcon(path)
        return QIcon()

    # ---------------------------------------------------------------- toggling

    def _on_toggled(self, enabled):
        self.action.setIcon(self.icon_on if enabled else self.icon_off)
        self.action.setText("Show all layers" if enabled else "Show only visible layers")
        QgsSettings().setValue(SETTINGS_KEY, bool(enabled))
        if enabled:
            self._schedule_update()
        else:
            if self.timer:
                self.timer.stop()
            self._restore_hidden_rows()

    def _schedule_update(self, *args):
        """Refresh later, after model-change notifications have settled."""
        if self.action is not None and self.action.isChecked() and self.timer:
            self.timer.start(0)

    # ---------------------------------------------------------------- filtering

    def _apply_filter(self):
        if self.action is None or not self.action.isChecked():
            return

        # A removed node invalidates its persistent index. A model reset also
        # clears the view's hidden rows, so drop entries that are no longer
        # actually hidden and let the pass below hide them again.
        self._hidden_rows = [
            index
            for index in self._hidden_rows
            if index.isValid() and self.view.isRowHidden(index.row(), index.parent())
        ]

        root = self.model.rootGroup()
        if root is not None:
            self._filter_group(root)

    def _filter_group(self, group):
        """Return True if this group contains any effectively visible layer.

        Groups are retained only when they contain a shown layer, including
        when that layer is in a nested subgroup. isVisible() considers both
        the layer's checkbox and the checkboxes on all ancestor groups.
        """
        contains_visible_layer = False

        for child in group.children():
            if isinstance(child, QgsLayerTreeGroup):
                should_show = self._filter_group(child)
            elif isinstance(child, QgsLayerTreeLayer):
                layer = child.layer()
                # Nonspatial tables have no map visibility checkbox in QGIS.
                should_show = bool(
                    layer is not None and layer.isSpatial() and child.isVisible()
                )
            else:
                # Newer QGIS versions also support custom tree nodes.
                should_show = child.isVisible()

            self._set_row_visible(child, should_show)
            contains_visible_layer = contains_visible_layer or should_show

        return contains_visible_layer

    def _view_index(self, node):
        """Index of a node in the model the view actually displays.

        Since QGIS 3.18 the view shows a proxy model on top of the layer tree
        model, so source indexes must not be passed to the view directly.
        """
        if hasattr(self.view, "node2index"):
            return self.view.node2index(node)
        index = self.model.node2index(node)
        view_model = self.view.model()
        if view_model is not self.model and hasattr(view_model, "mapFromSource"):
            index = view_model.mapFromSource(index)
        return index

    def _tracked(self, index):
        for i, tracked in enumerate(self._hidden_rows):
            if tracked == QPersistentModelIndex(index):
                return i
        return -1

    def _set_row_visible(self, node, should_show):
        index = self._view_index(node)
        if not index.isValid():
            return

        row, parent = index.row(), index.parent()
        tracked = self._tracked(index)
        if should_show:
            if tracked >= 0:
                self.view.setRowHidden(row, parent, False)
                del self._hidden_rows[tracked]
        elif tracked < 0 and not self.view.isRowHidden(row, parent):
            self.view.setRowHidden(row, parent, True)
            self._hidden_rows.append(QPersistentModelIndex(index))

    def _restore_hidden_rows(self):
        """Undo only our own UI hiding, leaving other plugins' rows alone."""
        if self.view is not None:
            for index in self._hidden_rows:
                if index.isValid():
                    self.view.setRowHidden(index.row(), index.parent(), False)
        self._hidden_rows = []

    # ------------------------------------------------------------------ unload

    def unload(self):
        # Always leave the Layers panel as we found it.
        if self.timer is not None:
            self.timer.stop()

        self._restore_hidden_rows()

        for signal in self._signals:
            try:
                signal.disconnect(self._schedule_update)
            except (RuntimeError, TypeError):
                pass
        self._signals = []

        if self.action is not None:
            try:
                self.action.toggled.disconnect(self._on_toggled)
            except (RuntimeError, TypeError):
                pass
            if self.toolbar is not None:
                self.toolbar.removeAction(self.action)
            else:
                self.iface.removeToolBarIcon(self.action)
            self.action.deleteLater()
            self.action = None

        if self.timer is not None:
            self.timer.timeout.disconnect(self._apply_filter)
            self.timer.deleteLater()
            self.timer = None

        self.model = None
        self.toolbar = None
        self.view = None
