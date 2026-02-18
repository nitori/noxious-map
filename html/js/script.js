/**
 * @typedef {{id: string, file: string, size: number[], pos: number[]}} MapConfig
 */

const ENABLE_DRAG = false;

(async () => {
    let resp = await fetch('./js/metadata.json');
    /** @type MapConfig[] */
    const mapsConfig = await resp.json();
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

        const resolutions = [
            {url: `./maps/default/${mapConfig.file}`, zoom: 0},
            {url: `./maps/low/${mapConfig.file}`, zoom: -2},
            {url: `./maps/small/${mapConfig.file}`, zoom: -4},
            {url: `./maps/tiny/${mapConfig.file}`, zoom: -6},
            {url: `./maps/micro/${mapConfig.file}`, zoom: -9999},
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
})();
