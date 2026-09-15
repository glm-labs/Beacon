let beaconInstallPrompt = null;
let beaconPwaRefreshing = false;

function currentBeaconLocale() {
    if (window.i18n && i18n.locale) {
        return i18n.locale;
    }

    return document.documentElement.lang || navigator.language || "en";
}

function syncBeaconServiceWorkerLocale(registration) {
    if (!registration) {
        return;
    }

    const worker = registration.active || registration.waiting || registration.installing;

    if (worker) {
        worker.postMessage({
            type: "SET_LOCALE",
            locale: currentBeaconLocale()
        });
    }
}

function isBeaconPwaStandalone() {
    return (
        window.matchMedia("(display-mode: standalone)").matches
        || window.navigator.standalone === true
    );
}

function setPwaInstallButtonVisible(visible) {
    const button = $("#topbar-install-app");

    if (!button.length) {
        return;
    }

    button.toggleClass("is-hidden", !visible);
}

function installBeaconPwa() {
    if (!beaconInstallPrompt) {
        return;
    }

    beaconInstallPrompt.prompt();

    beaconInstallPrompt.userChoice.finally(function () {
        beaconInstallPrompt = null;
        setPwaInstallButtonVisible(false);
    });
}

function registerBeaconServiceWorker() {
    if (!("serviceWorker" in navigator)) {
        return;
    }

    navigator.serviceWorker.register("/service-worker.js", {
        scope: "/"
    }).then(function (registration) {
        syncBeaconServiceWorkerLocale(registration);

        if (registration.waiting) {
            registration.waiting.postMessage({type: "SKIP_WAITING"});
        }

        registration.addEventListener("updatefound", function () {
            const worker = registration.installing;

            if (!worker) {
                return;
            }

            worker.addEventListener("statechange", function () {
                if (
                    worker.state === "installed"
                    && navigator.serviceWorker.controller
                ) {
                    worker.postMessage({type: "SKIP_WAITING"});
                }
            });
        });
    }).catch(function (error) {
        console.warn("Beacon service worker registration failed", error);
    });

    navigator.serviceWorker.addEventListener("controllerchange", function () {
        if (beaconPwaRefreshing) {
            return;
        }

        beaconPwaRefreshing = true;

        navigator.serviceWorker.ready.then(function (registration) {
            syncBeaconServiceWorkerLocale(registration);
        });

        window.location.reload();
    });
}

function setupBeaconPwaInstallPrompt() {
    if (isBeaconPwaStandalone()) {
        setPwaInstallButtonVisible(false);
        return;
    }

    window.addEventListener("beforeinstallprompt", function (event) {
        event.preventDefault();
        beaconInstallPrompt = event;
        setPwaInstallButtonVisible(true);
    });

    window.addEventListener("appinstalled", function () {
        beaconInstallPrompt = null;
        setPwaInstallButtonVisible(false);
    });

    $(document).on("click", "#topbar-install-app", function () {
        installBeaconPwa();
    });
}

$(document).ready(function () {
    setupBeaconPwaInstallPrompt();
    registerBeaconServiceWorker();
});
