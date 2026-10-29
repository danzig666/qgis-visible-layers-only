def classFactory(iface):
    from .visible_layers_only import VisibleLayersOnlyPlugin

    return VisibleLayersOnlyPlugin(iface)
