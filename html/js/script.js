/**
 * paddings are in css order: [top, right, bottom, left]
 *
 * @typedef {{
 *     id: string,
 *     file: string,
 *     size: number[],
 *     pos: number[],
 *     paddings: number[],
 *     columns: number,
 *     rows: number,
 * }} MapConfig
 * @typedef {{x: number, y: number, color: string}} Marker
 * @typedef {Object.<string, Marker[]>} Markers
 */

/*
 Enable drag by setting cookie
     document.cookie = 'admin=1; path=/';
 disable with:
     document.cookie = 'admin=0; path=/';
 */
const ENABLE_DRAG = document.cookie.match(/\badmin=1\b/) !== null;

const metadataMtime = document.querySelector('meta[name="metadata-mtime"]').getAttribute('content');

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
 * @param mapMarkers {Markers}
 * @param map {L.Map}
 * @return {Promise<void>}
 */
async function addMarkers(mapsConfig, mapMarkers, map) {

    /** @type {Object.<string, MapConfig>} */
    const idMap = {};
    mapsConfig.forEach(mapConfig => {
        idMap[mapConfig.id] = mapConfig;
    });

    let id;
    for (id in mapMarkers) {
        if (!mapMarkers.hasOwnProperty(id)) continue;
        if (!idMap.hasOwnProperty(id)) continue;

        let mapConfig = idMap[id];

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

        mapMarkers[id].forEach(marker => {

            let markerPos = [
                origin[0] - (marker.x + marker.y) * 16,
                origin[1] + (marker.x - marker.y) * 32
            ];

            let icon = L.icon({
                iconUrl: iconUrl(marker.color),
                iconAnchor: [13, 42],
            })

            L.marker(markerPos, {icon: icon}).addTo(map);
        });
    }
}

function htmlEscape(text) {
    return text.replace('&', '&amp;')
        .replace('>', '&gt;')
        .replace('<', '&lt;')
        .replace('"', '&quot;')
        .replace("'", '&apos;');
}

function iconUrl(color) {
    let svg = `<svg width="26" height="42" version="1.1" viewBox="0 0 6.8792 11.112" xmlns="http://www.w3.org/2000/svg">`
        + `<path fill="${htmlEscape(color)}" d="m3.44 0c-2.3042 0-3.4396 1.8023-3.4396 3.4396 0 4.1562 3.4396 7.6729 3.4396 7.6729s3.4396-3.7567 3.4396-7.6729c0-1.685-1.1354-3.4396-3.4396-3.4396zm0 1.8521a1.5875 1.5875 0 0 1 1.5875 1.5875 1.5875 1.5875 0 0 1-1.5875 1.5875 1.5875 1.5875 0 0 1-1.5875-1.5875 1.5875 1.5875 0 0 1 1.5875-1.5875z"/>`
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

})();
