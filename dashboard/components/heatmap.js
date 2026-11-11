(function () {
  const mapStore = {};

  function ensureMap(containerId) {
    if (mapStore[containerId]) {
      return mapStore[containerId];
    }
    if (typeof L === "undefined") {
      return null;
    }

    const map = L.map(containerId, {
      center: [12.97, 77.61],
      zoom: 11,
      zoomControl: true,
      preferCanvas: true,
      scrollWheelZoom: "center",
      wheelDebounceTime: 80,
      wheelPxPerZoomLevel: 90,
    });
    const container = map.getContainer();
    L.DomEvent.disableClickPropagation(container);
    L.DomEvent.disableScrollPropagation(container);
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: "&copy; OpenStreetMap contributors",
    }).addTo(map);

    const store = {
      map,
      layers: [],
      hasFitBounds: false,
      isInteracting: false,
      pendingPayload: null,
      userMovedMap: false,
    };

    map.on("zoomstart movestart", () => {
      store.isInteracting = true;
    });
    map.on("dragstart zoomstart", () => {
      store.userMovedMap = true;
    });
    map.on("zoomend moveend", () => {
      store.isInteracting = false;
      if (store.pendingPayload) {
        const pendingPayload = store.pendingPayload;
        store.pendingPayload = null;
        renderMap(containerId, pendingPayload);
      }
    });

    mapStore[containerId] = store;
    return mapStore[containerId];
  }

  function clearLayers(store) {
    (store.layers || []).forEach((layer) => store.map.removeLayer(layer));
    store.layers = [];
  }

  function renderMap(containerId, payload) {
    const store = ensureMap(containerId);
    if (!store) {
      return;
    }
    if (store.isInteracting) {
      store.pendingPayload = payload;
      return;
    }
    clearLayers(store);

    const bounds = [];
    const meters = payload.meters || [];
    const theft = payload.theft || [];
    const anomalies = payload.anomalies || [];

    const meterLayer = L.layerGroup();
    meters.forEach((meter) => {
      const latitude = Number(meter.latitude);
      const longitude = Number(meter.longitude);
      if (!Number.isFinite(latitude) || !Number.isFinite(longitude)) {
        return;
      }
      bounds.push([latitude, longitude]);
      L.circleMarker([latitude, longitude], {
        radius: meter.status === "Electricity Theft" ? 7 : 5,
        color: meter.status === "Electricity Theft" ? "#ef4444" : "#38bdf8",
        weight: meter.status === "Electricity Theft" ? 3 : 2,
        fillColor: meter.status === "Electricity Theft" ? "#ef4444" : "#38bdf8",
        fillOpacity: 0.7,
      })
        .bindPopup(`<strong>${meter.meter_id}</strong><br />${meter.area}<br />Status: ${meter.status}`)
        .addTo(meterLayer);
    });
    meterLayer.addTo(store.map);
    store.layers.push(meterLayer);

    const theftLayer = L.layerGroup();
    theft.forEach((record) => {
      const latitude = Number(record.latitude);
      const longitude = Number(record.longitude);
      if (!Number.isFinite(latitude) || !Number.isFinite(longitude)) {
        return;
      }
      bounds.push([latitude, longitude]);
      L.circle([latitude, longitude], {
        radius: 650,
        color: "#f97316",
        weight: 3,
        fillColor: "#ef4444",
        fillOpacity: 0.22,
      })
        .bindPopup(`<strong>Theft Alert</strong><br />${record.meter_id} | ${record.area}`)
        .addTo(theftLayer);
    });
    theftLayer.addTo(store.map);
    store.layers.push(theftLayer);

    const anomalyPoints = anomalies
      .map((record) => [Number(record.latitude), Number(record.longitude), Number(record.anomaly_score || 0.3)])
      .filter((record) => Number.isFinite(record[0]) && Number.isFinite(record[1]));
    if (typeof L.heatLayer === "function" && anomalyPoints.length) {
      const heatLayer = L.heatLayer(anomalyPoints, {
        radius: 24,
        blur: 18,
        maxZoom: 14,
        gradient: { 0.35: "#38bdf8", 0.6: "#f97316", 0.9: "#ef4444" },
      });
      heatLayer.addTo(store.map);
      store.layers.push(heatLayer);
    }

    if (bounds.length && !store.hasFitBounds && !store.userMovedMap) {
      store.map.fitBounds(bounds, { padding: [24, 24] });
      store.hasFitBounds = true;
    }
    window.setTimeout(() => store.map.invalidateSize(), 120);
  }

  window.SmartGridHeatmap = {
    renderMap,
  };
})();
