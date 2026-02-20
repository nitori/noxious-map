/**
 * paddings are in css order: [top, right, bottom, left]
 *
 * @typedef {{
 *     id: string,
 *     name: string,
 *     file: string,
 *     size: number[],
 *     pos: number[],
 *     paddings: number[],
 *     columns: number,
 *     rows: number,
 * }} MapConfig
 *
 * @typedef {{name: string, color: string, map: string, x: [number], y: [number]}} Poi
 * @typedef {{map: string, x: number, y: number}} ConnectionPoint
 * @typedef {{
 *     name: string,
 *     color: string,
 *     points: ConnectionPoint[],
 * }} Connection
 *
 *
 * @typedef {{pois: Poi[], connections: Connection[]}} MarkersFile
 *
 */

/*
 Enable drag by setting cookie
     document.cookie = 'admin=1; path=/';
 disable with:
     document.cookie = 'admin=0; path=/';
 */
const ENABLE_DRAG = document.cookie.match(/\badmin=1\b/) !== null;

const metadataMtime = document.querySelector('meta[name="metadata-mtime"]').getAttribute('content');


window.globalSettings = {
    enablePoi: true,
    enableConnections: true,
};

window.settingCallbacks = [];

function toggle(which) {
    window.globalSettings[which] = !window.globalSettings[which];
    window.settingCallbacks.forEach(callback => callback());
}

/**
 * @param mapsConfig {MapConfig[]}
 * @return {Promise<*>}
 */
async function buildMap(mapsConfig) {
    mapsConfig.sort((a, b) => {
        return b.pos[1] - a.pos[1];
    });

    const map = L.map('map', {
        crs: L.CRS.Simple,
        minZoom: -10,
        maxZoom: 2,
    });

    let overallBounds = L.latLngBounds([[0, 0], [1, 1]]);
    mapsConfig.forEach((mapConfig, index) => {
        let [x, y] = mapConfig.pos
        let [w, h] = mapConfig.size;

        const bounds = [[y, x], [y + h, x + w]];

        const fileName = mapConfig.file.replace(/\.webp$/, `.${metadataMtime}.webp`);

        const resolutions = [
            {url: `./maps/default/${fileName}`, zoom: 0},
            {url: `./maps/low/${fileName}`, zoom: -2},
            {url: `./maps/small/${fileName}`, zoom: -4},
            {url: `./maps/tiny/${fileName}`, zoom: -6},
            {url: `./maps/micro/${fileName}`, zoom: -9999},
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

        if (ENABLE_DRAG) {
            const sw = [y, x];
            const nw = [y + h, x];
            const ne = [y + h, x + w];
            const se = [y, x + w];
            const polyPoints = [sw, se, ne, nw];  // Clockwise order

            const pg = new L.Polygon([polyPoints], {
                draggable: true,
                opacity: 0.1,
                fillOpacity: 0,
                color: 'red'
            }).addTo(map);

            pg.on('drag, dragend', function (e) {
                image.setBounds(pg.getBounds());
                /** @type L.LatLngBounds */
                let bounds = pg.getBounds();

                let [y, x] = [bounds.getSouth(), bounds.getWest()];
                mapConfig.pos = [x, y];
                mapsConfig.sort((a, b) => a.id.toLocaleLowerCase().localeCompare(b.id.toLocaleLowerCase()));

                // output object, to copy-paste it
                console.log(mapsConfig);
            });
        }
    });

    map.fitBounds(overallBounds);
    return map;
}

/**
 * @param mapsConfig {MapConfig[]}
 * @param mapMarkers {MarkersFile}
 * @param map {L.Map}
 * @return {Promise<void>}
 */
async function addMarkers(mapsConfig, mapMarkers, map) {
    /** @type {L.Marker[]} */
    let poiMarkers = [];
    /** @type {L.Marker[]} */
    let connectionMarkers = [];

    /** @type {Object.<string, MapConfig>} */
    const idMap = {};
    mapsConfig.forEach(mapConfig => {
        idMap[mapConfig.id] = mapConfig;
    });

    const translateTilePos = (x, y, mapConfig) => {
        // coords are bottom left of the image layer
        let [map_x, map_y] = mapConfig.pos;
        let [map_w, map_h] = mapConfig.size;
        let [pad_top, pad_right, pad_bottom, pad_left] = mapConfig.paddings;

        // remove paddings to get tile map pos (bottom-left) and size
        map_x += pad_left;
        map_y += pad_bottom;
        map_w -= (pad_left + pad_right);
        map_h -= (pad_top + pad_bottom);

        let origin = [
            map_y + map_h - 16,
            map_x + (mapConfig.rows * 32)
        ];

        return [
            origin[0] - (x + y) * 16,
            origin[1] + (x - y) * 32
        ];
    };

    mapMarkers.connections.forEach(connection => {
        if (connection.points.length === 0) return;

        let names = connection.points.map(point => idMap[point.map].name);
        let nameString = names.join(' ⇆ ');

        connection.points.forEach(point => {
            let mapConfig = idMap[point.map];
            let markerPos = translateTilePos(point.x, point.y, mapConfig);
            let icon = new L.Icon({
                iconUrl: connectionIconUrl(connection.color),
                iconAnchor: [16, 42],
                tooltipAnchor: [0, -42],
            })
            let marker = new L.Marker(markerPos, {icon: icon});
            marker.addTo(map);
            marker.bindTooltip(connection.name || nameString, {direction: 'top'});
            connectionMarkers.push(marker);
        });
    });

    mapMarkers.pois.forEach(poi => {
        let mapConfig = idMap[poi.map];
        let x = Number.isInteger(poi.x) ? poi.x : Math.floor(mapConfig.columns / 2);
        let y = Number.isInteger(poi.y) ? poi.y : Math.floor(mapConfig.rows / 2);
        let markerPos = translateTilePos(x, y, mapConfig);
        let icon = new L.Icon({
            iconUrl: poiIconUrl(poi.color),
            iconAnchor: [16, 32],
            tooltipAnchor: [0, -32],
        })
        let marker = new L.Marker(markerPos, {icon: icon});
        marker.addTo(map);
        marker.bindTooltip(poi.name || mapConfig.name, {direction: 'top'});
        poiMarkers.push(marker);
    });


    const updateMarkers = (zoom) => {
        if (zoom >= -5 && globalSettings.enablePoi) {
            poiMarkers.forEach(marker => marker.addTo(map));
        } else {
            poiMarkers.forEach(marker => marker.remove(map));
        }

        if (zoom >= -4 && globalSettings.enableConnections) {
            connectionMarkers.forEach(marker => marker.addTo(map));
        } else {
            connectionMarkers.forEach(marker => marker.remove(map));
        }
    }

    map.on('zoomend', function (e) {
        updateMarkers(map.getZoom());
    });

    window.settingCallbacks.push(() => {
        updateMarkers(map.getZoom());
    });

}

function htmlEscape(text) {
    return text.replace('&', '&amp;')
        .replace('>', '&gt;')
        .replace('<', '&lt;')
        .replace('"', '&quot;')
        .replace("'", '&apos;');
}

function connectionIconUrl(color) {
    let svg = `<svg version="1.1" width="32" height="42" viewBox="0 0 32 42" xmlns="http://www.w3.org/2000/svg">`
        + `<path fill="${htmlEscape(color)}" d="m16.009 0c-10.473 0-15.984 8.5816-16.009 15.681-0.027134 7.6056 4.2516 10.894 16.035 26.319 10.968-14.496 15.965-19.02 15.965-26.344 0-6.6659-5.3362-15.656-15.991-15.656zm-0.039977 11.245a4.6046 4.5705 0 0 1 4.6054 4.5706 4.6046 4.5705 0 0 1-4.6054 4.5706 4.6046 4.5705 0 0 1-4.6054-4.5706 4.6046 4.5705 0 0 1 4.6054-4.5706z"/>`
        + `</svg>`;
    return `data:image/svg+xml;base64,${btoa(svg)}`;
}

function poiIconUrl(color) {
    let svg = `<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 640 640">`
        + `<path fill="${htmlEscape(color)}" d="M96 96L32 96L32 320L64 320L64 576L576 576L576 320L608 320L608 96L544 96L544 160L512 160L512 96L448 96L448 160L416 160L416 96L352 96L352 224L288 224L288 96L224 96L224 160L192 160L192 96L128 96L128 160L96 160L96 96zM384 384L384 528L256 528L256 384L384 384z"/>`
        + `</svg>`;
    return `data:image/svg+xml;base64,${btoa(svg)}`;
}

(async () => {

    let resp = await fetch(`./js/metadata.${metadataMtime}.json`);
    const mapsConfig = await resp.json();

    const map = await buildMap(mapsConfig);

    let resp2 = await fetch(`./js/markers.${metadataMtime}.json`);
    let markers = await resp2.json();

    await addMarkers(mapsConfig, markers, map);

    const poisButton = document.querySelector('#toggle-pois');
    const connectionsButton = document.querySelector('#toggle-connections');
    window.settingCallbacks.push(() => {
        poisButton.classList.toggle('active', globalSettings.enablePoi);
        connectionsButton.classList.toggle('active', globalSettings.enableConnections);
    });

    window.settingCallbacks.forEach(callback => callback());

})();
