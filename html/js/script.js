/**
 * Noxious map Leaflet viewer, driven by Tiled files.
 *
 * The Tiled world (`js/tiled/world.tmx`) is an *isometric* map with 64x32
 * tiles, that contains:
 *  - a "Maps" object group with one ImageObject per game map
 *    (each referencing a tile in `js/tiled/maps.tsx` by `gid`)
 *  - a "Connections" object group with point objects for teleports.
 *  - optionally other point-object groups (e.g. "POIs") for interesting
 *    places that should be toggled separately.
 *
 * The tileset (`js/tiled/maps.tsx`) describes, for each game map, the path to
 * the rendered image, its paddings, base size, and final image dimensions.
 *
 * Tiled stores object-layer coordinates in "isometric pixel" space: they have
 * to be projected onto screen pixels via Tiled's `pixelToScreenCoords`
 * transform before they can be used as Leaflet coordinates.
 *
 * See also: `src/noxious_map/generator/maps.py` (Python side) for:
 *  - `to_tiled_image_position(local_xy, image_xy, image_wh)`
 *  - `get_tile_center(tile_x, tile_y, tile_map, paddings)`
 */

const metadataMtime = document.querySelector('meta[name="metadata-mtime"]')
    ?.getAttribute('content') || '0';

window.globalSettings = {
    enablePoi: true,
    enableConnections: true,
};

window.settingCallbacks = [];

function toggle(which) {
    window.globalSettings[which] = !window.globalSettings[which];
    window.settingCallbacks.forEach(callback => callback());
}


// ---------------------------------------------------------------------------
// Tiled / isometric projection helpers
// ---------------------------------------------------------------------------

/**
 * Apply Tiled's isometric `pixelToScreenCoords` transform.
 *
 * For a map with tileWidth and tileHeight:
 *     screenX = (x - y) * tileWidth / (2 * tileHeight) + originX
 *     screenY = (x + y) / 2
 * where originX = mapHeightInTiles * tileWidth / 2.
 *
 * For our 64x32 map this simplifies to:
 *     screenX = (x - y) + originX
 *     screenY = (x + y) / 2
 *
 * @param {number} x - tiled isometric x
 * @param {number} y - tiled isometric y
 * @param {{tileWidth: number, tileHeight: number, originX: number}} proj
 * @returns {{sx: number, sy: number}}
 */
function isoToScreen(x, y, proj) {
    const sx = (x - y) * proj.tileWidth / (2 * proj.tileHeight) + proj.originX;
    const sy = (x + y) / 2;
    return {sx, sy};
}

/**
 * Convert a screen-pixel coordinate to Leaflet [lat, lng] for L.CRS.Simple.
 * We flip Y so that "up" on screen is positive lat, which matches the
 * existing map images being drawn "right way up".
 */
function screenToLatLng(sx, sy) {
    return [-sy, sx];
}


// ---------------------------------------------------------------------------
// Tiled XML loading
// ---------------------------------------------------------------------------

async function loadXml(url) {
    const resp = await fetch(url);
    if (!resp.ok) throw new Error(`Failed to load ${url}: ${resp.status}`);
    const text = await resp.text();
    const doc = new DOMParser().parseFromString(text, 'application/xml');
    const err = doc.querySelector('parsererror');
    if (err) throw new Error(`XML parse error for ${url}: ${err.textContent}`);
    return doc;
}

function parseProperties(elem) {
    const props = {};
    const propsElem = elem.querySelector(':scope > properties');
    if (!propsElem) return props;
    for (const p of propsElem.querySelectorAll(':scope > property')) {
        const name = p.getAttribute('name');
        const type = p.getAttribute('type') || 'string';
        let value = p.getAttribute('value');
        if (type === 'int' || type === 'float') value = Number(value);
        else if (type === 'bool') value = value === 'true';
        props[name] = value;
    }
    return props;
}

/**
 * @typedef {{
 *     id: number,
 *     gid: number,                // world-level gid (firstgid + local id)
 *     noxiousId: string,
 *     paddings: {top:number,right:number,bottom:number,left:number},
 *     baseSize: [number, number], // (base_w, base_h) of un-padded iso diamond
 *     mapWidth: number,           // final padded image width (pixels)
 *     mapHeight: number,          // final padded image height (pixels)
 *     mapColumns: number|null,    // iso tile columns (optional, future-proof)
 *     mapRows: number|null,       // iso tile rows (optional, future-proof)
 *     imageSource: string,        // relative path stored in the .tsx
 *     imageWidth: number,
 *     imageHeight: number,
 * }} TilesetTile
 */

/**
 * Parse a `.tsx` tileset document.
 * @param {Document} doc
 * @param {number} firstgid - assigned in the world.tmx `<tileset>` entry
 * @returns {{name:string, tiles: Object.<number, TilesetTile>, byNoxiousId: Object.<string, TilesetTile>}}
 */
function parseTileset(doc, firstgid) {
    const tileset = doc.querySelector('tileset');
    const name = tileset.getAttribute('name');

    const tiles = {};
    const byNoxiousId = {};

    for (const tileElem of tileset.querySelectorAll(':scope > tile')) {
        const localId = parseInt(tileElem.getAttribute('id'), 10);
        const props = parseProperties(tileElem);
        const imgElem = tileElem.querySelector(':scope > image');
        if (!imgElem) continue;

        // paddings stored as the string "top,right,bottom,left"
        const padParts = String(props.paddings || '0,0,0,0').split(',').map(n => parseInt(n, 10));
        const paddings = {
            top: padParts[0] || 0,
            right: padParts[1] || 0,
            bottom: padParts[2] || 0,
            left: padParts[3] || 0,
        };

        // baseSize stored as "(w, h)"
        const bsMatch = String(props.baseSize || '').match(/\(\s*(\d+)\s*,\s*(\d+)\s*\)/);
        const baseSize = bsMatch
            ? [parseInt(bsMatch[1], 10), parseInt(bsMatch[2], 10)]
            : [0, 0];

        const tile = {
            id: localId,
            gid: firstgid + localId,
            noxiousId: props.noxious_id,
            paddings,
            baseSize,
            mapWidth: props.mapWidth != null ? Number(props.mapWidth) : parseInt(imgElem.getAttribute('width'), 10),
            mapHeight: props.mapHeight != null ? Number(props.mapHeight) : parseInt(imgElem.getAttribute('height'), 10),
            mapColumns: props.mapColumns != null ? Number(props.mapColumns) : null,
            mapRows: props.mapRows != null ? Number(props.mapRows) : null,
            imageSource: imgElem.getAttribute('source'),
            imageWidth: parseInt(imgElem.getAttribute('width'), 10),
            imageHeight: parseInt(imgElem.getAttribute('height'), 10),
        };
        tiles[tile.gid] = tile;
        if (tile.noxiousId) byNoxiousId[tile.noxiousId] = tile;
    }

    return {name, tiles, byNoxiousId};
}

/**
 * @typedef {{
 *     id: number, name: string, group: string,
 *     x: number, y: number,
 *     gid: number, width: number, height: number,
 *     properties: Object.<string, any>,
 * }} WorldImageObject
 *
 * @typedef {{
 *     id: number, name: string, group: string,
 *     x: number, y: number,
 *     properties: Object.<string, any>,
 * }} WorldPointObject
 *
 * @typedef {{
 *     projection: {tileWidth:number, tileHeight:number, mapWidthInTiles:number, mapHeightInTiles:number, originX:number},
 *     tilesetFirstGid: number,
 *     tilesetSource: string,
 *     imageObjects: WorldImageObject[],
 *     pointObjects: WorldPointObject[],
 * }} ParsedWorld
 */

/**
 * @param {Document} doc
 * @returns {ParsedWorld}
 */
function parseWorld(doc) {
    const mapElem = doc.querySelector('map');
    const tileWidth = parseInt(mapElem.getAttribute('tilewidth'), 10);
    const tileHeight = parseInt(mapElem.getAttribute('tileheight'), 10);
    const mapWidthInTiles = parseInt(mapElem.getAttribute('width'), 10);
    const mapHeightInTiles = parseInt(mapElem.getAttribute('height'), 10);
    const originX = mapHeightInTiles * tileWidth / 2;

    const tilesetElem = mapElem.querySelector(':scope > tileset');
    const tilesetFirstGid = parseInt(tilesetElem.getAttribute('firstgid'), 10);
    const tilesetSource = tilesetElem.getAttribute('source');

    const imageObjects = [];
    const pointObjects = [];

    for (const og of mapElem.querySelectorAll(':scope > objectgroup')) {
        const groupName = og.getAttribute('name') || '';
        for (const obj of og.querySelectorAll(':scope > object')) {
            const base = {
                id: parseInt(obj.getAttribute('id'), 10),
                name: obj.getAttribute('name') || '',
                group: groupName,
                x: parseFloat(obj.getAttribute('x')),
                y: parseFloat(obj.getAttribute('y')),
                properties: parseProperties(obj),
            };
            const gidAttr = obj.getAttribute('gid');
            if (gidAttr != null) {
                base.gid = parseInt(gidAttr, 10);
                base.width = parseFloat(obj.getAttribute('width'));
                base.height = parseFloat(obj.getAttribute('height'));
                imageObjects.push(base);
            } else if (obj.querySelector(':scope > point')) {
                pointObjects.push(base);
            }
        }
    }

    return {
        projection: {tileWidth, tileHeight, mapWidthInTiles, mapHeightInTiles, originX},
        tilesetFirstGid, tilesetSource, imageObjects, pointObjects,
    };
}


// ---------------------------------------------------------------------------
// Coordinate conversions
// ---------------------------------------------------------------------------

/**
 * Get the screen-pixel position of an image object's anchor point.
 *
 * For isometric maps, Tiled anchors tile image objects at their
 * **bottom-center**. That is: `isoToScreen(obj.x, obj.y)` is the screen
 * pixel where the bottom-center of the object's image is drawn.
 *
 * This matches the offsets used by the Python generator's
 * `to_tiled_image_position`, which encodes
 *   delta_screen = (local_x - image_width/2, local_y - image_height)
 * i.e. the image pixel (image_width/2, image_height) = bottom-center is
 * positioned at iso(obj.x, obj.y).
 *
 * @param {WorldImageObject} obj
 * @param proj
 * @returns {{sx:number, sy:number}}
 */
function imageObjectScreenAnchor(obj, proj) {
    return isoToScreen(obj.x, obj.y, proj);
}

/**
 * Compute the Leaflet [lat,lng] bounds of an image object.
 *
 * @param {WorldImageObject} obj
 * @param proj
 * @returns {L.LatLngBounds}
 */
function imageObjectLatLngBounds(obj, proj) {
    const {sx, sy} = imageObjectScreenAnchor(obj, proj);
    // Anchor = bottom-center of the image.
    const blSx = sx - obj.width / 2;
    const blSy = sy;
    const trSx = sx + obj.width / 2;
    const trSy = sy - obj.height;
    return L.latLngBounds(
        screenToLatLng(blSx, blSy),
        screenToLatLng(trSx, trSy),
    );
}

// ---------------------------------------------------------------------------
// Leaflet map building
// ---------------------------------------------------------------------------

/**
 * @param {ParsedWorld} world
 * @param tileset {{tiles: Object.<number, TilesetTile>}}
 */
async function buildMap(world, tileset) {
    // Respect Tiled's authored draw order. The "Maps" object group uses
    // draworder="index": objects are drawn in document order, so the
    // first object in the XML is at the bottom and the last one is on top.
    // Leaflet also draws later-added overlays on top, so iterating the
    // image objects in document order gives the right stacking.
    const mapObjects = [...world.imageObjects];

    const map = L.map('map', {
        crs: L.CRS.Simple,
        minZoom: -10,
        maxZoom: 2,
    });

    let overallBounds = L.latLngBounds([[0, 0], [1, 1]]);

    mapObjects.forEach(obj => {
        const tile = tileset.tiles[obj.gid];
        if (!tile) {
            console.warn('No tile found for gid', obj.gid, obj.name);
            return;
        }

        const bounds = imageObjectLatLngBounds(obj, world.projection);

        // The tile's imageSource is relative to js/tiled/maps.tsx, typically
        // "../../maps/default/<id>.webp". Rewrite it into a path relative to
        // start.html/index.php, preserving the per-resolution folder.
        const fileName = tile.imageSource.replace(/^.*\/maps\/[^/]+\//, '');
        const stampedFile = fileName.replace(/\.webp$/, `.${metadataMtime}.webp`);

        const resolutions = [
            {url: `./maps/default/${stampedFile}`, zoom: 0},
            {url: `./maps/low/${stampedFile}`, zoom: -2},
            {url: `./maps/small/${stampedFile}`, zoom: -4},
            {url: `./maps/tiny/${stampedFile}`, zoom: -6},
            {url: `./maps/micro/${stampedFile}`, zoom: -9999},
        ];

        let current = resolutions[resolutions.length - 1].url;
        const image = L.imageOverlay(current, bounds).addTo(map);

        map.on('zoomend', function () {
            const zoom = map.getZoom();
            for (let i = 0; i < resolutions.length; i++) {
                const res = resolutions[i];
                if (zoom >= res.zoom) {
                    if (res.url !== current) {
                        current = res.url;
                        image.setUrl(current);
                    }
                    break;
                }
            }
        });

        overallBounds = overallBounds.extend(bounds);
    });

    let stored = JSON.parse(localStorage.getItem('mapBounds') || 'null');
    let initialBounds;
    if (Array.isArray(stored) && stored.length === 2) {
        initialBounds = L.latLngBounds(stored[0], stored[1]);
    } else {
        initialBounds = overallBounds;
    }
    map.fitBounds(initialBounds);

    map.on('moveend', () => {
        const b = map.getBounds();
        localStorage.setItem('mapBounds', JSON.stringify([b.getSouthWest(), b.getNorthEast()]));
    });

    return map;
}


/**
 * Add markers for the point objects in world.tmx. Points in the
 * "Connections" object group become teleport markers; points in any other
 * group become POI markers.
 *
 * Each point may carry a `color` property to override its icon color.
 *
 * @param {ParsedWorld} world
 * @param {L.Map} map
 */
async function addMarkers(world, map) {
    /** @type {L.Marker[]} */
    const poiMarkers = [];
    /** @type {L.Marker[]} */
    const connectionMarkers = [];

    // One POI marker at the center of each named map image object.
    world.imageObjects.forEach(obj => {
        if (obj.group !== 'Maps') return;
        const label = obj.name || obj.properties.tileMapName;
        if (!label) return;

        const center = imageObjectLatLngBounds(obj, world.projection).getCenter();
        const icon = new L.Icon({
            iconUrl: poiIconUrl('#00f'),
            iconSize: [32, 32],
            iconAnchor: [16, 32],
            tooltipAnchor: [0, -32],
        });
        const marker = new L.Marker(center, {icon});
        marker.bindTooltip(label, {direction: 'top'});
        marker.addTo(map);
        poiMarkers.push(marker);
    });

    world.pointObjects.forEach(pt => {
        const {sx, sy} = isoToScreen(pt.x, pt.y, world.projection);
        const pos = screenToLatLng(sx, sy);

        const isConnection = pt.group === 'Connections';
        const color = pt.properties.color
            || (isConnection ? '#c00' : '#fff');

        const icon = isConnection
            ? new L.Icon({
                iconUrl: connectionIconUrl(color),
                iconSize: [32, 42],
                iconAnchor: [16, 42],
                tooltipAnchor: [0, -42],
            })
            : new L.Icon({
                iconUrl: poiIconUrl(color),
                iconSize: [32, 32],
                iconAnchor: [16, 32],
                tooltipAnchor: [0, -32],
            });

        const label = pt.name
            || pt.properties.destMapName
            || pt.properties.srcMapName
            || (isConnection ? 'Connection' : 'POI');
        const marker = new L.Marker(pos, {icon});
        marker.bindTooltip(label, {direction: 'top'});
        marker.addTo(map);

        (isConnection ? connectionMarkers : poiMarkers).push(marker);
    });

    const updateMarkers = () => {
        if (globalSettings.enablePoi) poiMarkers.forEach(m => m.addTo(map));
        else poiMarkers.forEach(m => m.remove(map));
        if (globalSettings.enableConnections) connectionMarkers.forEach(m => m.addTo(map));
        else connectionMarkers.forEach(m => m.remove(map));
    };
    window.settingCallbacks.push(updateMarkers);
}


// ---------------------------------------------------------------------------
// Marker icons
// ---------------------------------------------------------------------------

function htmlEscape(text) {
    return String(text)
        .replace(/&/g, '&amp;')
        .replace(/>/g, '&gt;')
        .replace(/</g, '&lt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&apos;');
}

function connectionIconUrl(color) {
    const svg = `<svg version="1.1" width="32" height="42" viewBox="0 0 32 42" xmlns="http://www.w3.org/2000/svg">`
        + `<path fill="${htmlEscape(color)}" d="m16.009 0c-10.473 0-15.984 8.5816-16.009 15.681-0.027134 7.6056 4.2516 10.894 16.035 26.319 10.968-14.496 15.965-19.02 15.965-26.344 0-6.6659-5.3362-15.656-15.991-15.656zm-0.039977 11.245a4.6046 4.5705 0 0 1 4.6054 4.5706 4.6046 4.5705 0 0 1-4.6054 4.5706 4.6046 4.5705 0 0 1-4.6054-4.5706 4.6046 4.5705 0 0 1 4.6054-4.5706z"/>`
        + `</svg>`;
    return `data:image/svg+xml;base64,${btoa(svg)}`;
}

function poiIconUrl(color) {
    const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 640 640">`
        + `<path fill="${htmlEscape(color)}" d="M96 96L32 96L32 320L64 320L64 576L576 576L576 320L608 320L608 96L544 96L544 160L512 160L512 96L448 96L448 160L416 160L416 96L352 96L352 224L288 224L288 96L224 96L224 160L192 160L192 96L128 96L128 160L96 160L96 96zM384 384L384 528L256 528L256 384L384 384z"/>`
        + `</svg>`;
    return `data:image/svg+xml;base64,${btoa(svg)}`;
}


// ---------------------------------------------------------------------------
// Boot
// ---------------------------------------------------------------------------

(async () => {
    const worldDoc = await loadXml('./js/tiled/world.tmx');
    const world = parseWorld(worldDoc);

    // Resolve the tileset referenced by world.tmx relative to that file.
    const tsxUrl = new URL(world.tilesetSource, new URL('./js/tiled/world.tmx', window.location.href)).href;
    const tsxDoc = await loadXml(tsxUrl);
    const tileset = parseTileset(tsxDoc, world.tilesetFirstGid);

    const map = await buildMap(world, tileset);

    await addMarkers(world, map);

    const poisButton = document.querySelector('#toggle-pois');
    const connectionsButton = document.querySelector('#toggle-connections');
    window.settingCallbacks.push(() => {
        poisButton?.classList.toggle('active', globalSettings.enablePoi);
        connectionsButton?.classList.toggle('active', globalSettings.enableConnections);
    });
    window.settingCallbacks.push(() => {
        localStorage.setItem('globalSettings', JSON.stringify(globalSettings));
    });

    const tmp = JSON.parse(localStorage.getItem('globalSettings') || '{}');
    if (tmp.enablePoi !== undefined) globalSettings.enablePoi = tmp.enablePoi;
    if (tmp.enableConnections !== undefined) globalSettings.enableConnections = tmp.enableConnections;

    // run once, after everything's set up
    settingCallbacks.forEach(callback => callback());
})();
