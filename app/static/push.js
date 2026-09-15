function urlBase64ToUint8Array(base64String) {
  const padding = "=".repeat((4 - base64String.length % 4) % 4);
  const base64 = (base64String + padding)
    .replace(/-/g, "+")
    .replace(/_/g, "/");

  const rawData = window.atob(base64);
  const outputArray = new Uint8Array(rawData.length);

  for (let i = 0; i < rawData.length; ++i) {
    outputArray[i] = rawData.charCodeAt(i);
  }

  return outputArray;
}


async function registerBeaconServiceWorker() {
  if (!("serviceWorker" in navigator)) {
    throw new Error("Service workers are not supported by this browser");
  }

  if (!("PushManager" in window)) {
    throw new Error("Push notifications are not supported by this browser");
  }

  return navigator.serviceWorker.register("/service-worker.js");
}


async function getBrowserPushConfig() {
  const response = await fetch("/api/profile/push/vapid-public-key");

  if (!response.ok) {
    throw new Error("Failed to load browser push config");
  }

  return response.json();
}


async function enableBrowserPushNotifications(deviceName) {
  const config = await getBrowserPushConfig();

  if (!config.enabled || !config.public_key) {
    throw new Error("Browser push notifications are not enabled");
  }

  const permission = await Notification.requestPermission();

  if (permission !== "granted") {
    throw new Error("Notification permission was not granted");
  }

  const registration = await registerBeaconServiceWorker();

  const existingSubscription = await registration.pushManager.getSubscription();

  if (existingSubscription) {
    await existingSubscription.unsubscribe();
  }

  const subscription = await registration.pushManager.subscribe({
    userVisibleOnly: true,
    applicationServerKey: urlBase64ToUint8Array(config.public_key)
  });

  const payload = subscription.toJSON();

  payload.device_name = deviceName || getDefaultPushDeviceName();

  const response = await fetch("/api/profile/push/subscriptions", {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify(payload)
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.message || "Failed to save browser push subscription");
  }

  return response.json();
}


async function sendBrowserPushTest() {
  const response = await fetch("/api/profile/push/test", {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    }
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.message || "Failed to send test push");
  }

  return response.json();
}


async function loadBrowserPushSubscriptions() {
  const response = await fetch("/api/profile/push/subscriptions");

  if (!response.ok) {
    throw new Error("Failed to load browser push subscriptions");
  }

  return response.json();
}


async function disableBrowserPushSubscription(subscriptionId) {
  const response = await fetch(`/api/profile/push/subscriptions/${subscriptionId}`, {
    method: "DELETE"
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.message || "Failed to disable browser push subscription");
  }

  return response.json();
}


function getDefaultPushDeviceName() {
  const platform = navigator.platform || "Browser";
  const userAgent = navigator.userAgent || "";

  if (/Android/i.test(userAgent)) {
    return "Android browser";
  }

  if (/iPhone|iPad|iPod/i.test(userAgent)) {
    return "iOS browser";
  }

  if (/Mac/i.test(platform)) {
    return "Mac browser";
  }

  if (/Win/i.test(platform)) {
    return "Windows browser";
  }

  if (/Linux/i.test(platform)) {
    return "Linux browser";
  }

  return "Browser";
}
