(function () {
  const root = document.querySelector("[data-live-orders]");
  if (!root) return;

  let timer = null;
  let controller = null;
  const labels = { PLACED: "Placed", PREPARING: "Preparing", READY: "Ready", COLLECTED: "Collected", CANCELLED: "Cancelled" };

  function addOrder(order) {
    const card = document.createElement("article");
    card.className = "card border-0 shadow-sm mb-3";
    card.id = `order-${order.id}`;
    card.dataset.orderId = String(order.id);
    const body = document.createElement("div");
    body.className = "card-body";
    const heading = document.createElement("div");
    heading.className = "d-flex justify-content-between gap-3";
    const title = document.createElement("h2");
    title.className = "h6 mb-1";
    title.textContent = `Order #${order.id}`;
    const badge = document.createElement("span");
    badge.className = "badge text-bg-primary";
    badge.dataset.orderStatus = "";
    heading.append(title, badge);
    const total = document.createElement("div");
    total.className = "fw-semibold mt-2";
    total.dataset.orderTotal = "";
    body.append(heading, total);
    card.append(body);
    root.prepend(card);
    const empty = root.querySelector("[data-empty-orders]");
    if (empty) empty.remove();
    return card;
  }

  function applyOrder(order) {
    const card = root.querySelector(`[data-order-id="${order.id}"]`) || addOrder(order);
    const badge = card.querySelector("[data-order-status]");
    if (badge) badge.textContent = labels[order.status] || order.status;
    const total = card.querySelector("[data-order-total]");
    if (total) total.textContent = `Total: ₹${order.total}`;
  }

  async function fetchChangedOrders(signal) {
    const since = new Date(Date.now() - 5000).toISOString();
    const url = `${root.dataset.endpoint}?since=${encodeURIComponent(since)}`;
    let next = url;
    while (next) {
      const response = await fetch(next, { credentials: "same-origin", signal, headers: { Accept: "application/json" } });
      if (!response.ok) throw new Error("Could not refresh your orders.");
      const page = await response.json();
      (page.results || []).forEach(applyOrder);
      next = page.next;
    }
  }

  async function poll() {
    if (document.hidden || controller) return;
    controller = new AbortController();
    try { await fetchChangedOrders(controller.signal); }
    catch (error) { if (error.name !== "AbortError") console.error(error); }
    finally { controller = null; }
  }

  function stop() {
    if (timer) window.clearInterval(timer);
    timer = null;
    if (controller) controller.abort();
  }

  function start() {
    if (document.hidden || timer) return;
    poll();
    timer = window.setInterval(poll, 4000);
  }

  document.addEventListener("visibilitychange", () => (document.hidden ? stop() : start()));
  start();
})();
