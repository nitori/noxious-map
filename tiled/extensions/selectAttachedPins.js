var selectAttached = tiled.registerAction("SelectAttachedObjects", function (action) {
    var asset = tiled.activeAsset;
    if (!asset || !asset.isTileMap) {
        tiled.alert("No map open.");
        return;
    }

    var selectedObjects = asset.selectedObjects;
    if (selectedObjects.length === 0) {
        tiled.alert("Select at least one map object first.");
        return;
    }

    // Collect IDs of selected maps (in case multiple), excluding pins
    var parentIds = new Set();
    for (var i = 0; i < selectedObjects.length; i++) {
        parentIds.add(selectedObjects[i].id);
    }

    // Find all object layers in the map
    var allObjects = [];

    function collectObjects(layer) {
        if (layer.isObjectLayer) {
            allObjects = allObjects.concat(layer.objects);
        } else if (layer.isGroupLayer) {
            for (var j = 0; j < layer.layerCount; j++) {
                collectObjects(layer.layerAt(j));
            }
        }
    }

    // Start from root layers
    for (var i = 0; i < asset.layerCount; i++) {
        collectObjects(asset.layerAt(i));
    }

    // Find attached pins
    var attached = [];
    for (var k = 0; k < allObjects.length; k++) {
        var obj = allObjects[k];
        var attachedTo = obj.property("attachedTo");
        if (attachedTo && attachedTo.id && parentIds.has(attachedTo.id)) {
            attached.push(obj);
        }
    }

    // Combine original selection with attached
    var newSelection = selectedObjects.concat(attached);

    // Set the new selection
    asset.selectedObjects = newSelection;

    tiled.log("Selected " + newSelection.length + " objects (including attached pins).");
});

selectAttached.text = "Select Attached Objects";
selectAttached.shortcut = "Ctrl+Alt+S";

tiled.extendMenu("Map", [
    {action: "SelectAttachedObjects"}
]);
