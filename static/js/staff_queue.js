(function () {
  const root = document.querySelector("[data-staff-queue]");
  if (!root) return;

  let timer = null;
  let controller = null;
  const csrf = document.querySelector("[data-csrf-token]").value;
  const statusLabels = { PLACED: "Placed", PREPARING: "Preparing", READY: "Ready", COLLECTED: "Collected", CANCELLED: "Cancelled" };
  const nextLabels = { PLACED: "Start preparing", PREPARING: "Mark ready", READY: "Mark collected" };

  function updateCard(card, order) {
    card.dataset.orderId = String(order.id);
    const badge = card.querySelector("[data-order-status]");
    if (badge) badge.textContent = statusLabels[order.status] || order.status;
    const button = card.querySelector("[data-advance-order]");
    if (button) {
      button.dataset.orderId = String(order.id);
      button.textContent = nextLabels[order.status] || "Complete";
      button.disabled = !nextLabels[order.status];
    }
  }

  function makeCard(order) {
    const card = document.createElement("article");
    card.className = "card border-0 shadow-sm mb-3";
    const body = document.createElement("div");
    body.className = "card-body";
    const heading = document.createElement("div");
    heading.className = "d-flex justify-content-between gap-3";
    const title = document.createElement("h2");
    title.className = "h5";
    title.textContent = `Order #${order.id} · ${order.customer_username}`;
    const badge = document.createElement("span");
    badge.className = "badge text-bg-primary";
    badge.dataset.orderStatus = "";
    heading.append(title, badge);
    const items = document.createElement("ul");
    items.className = "small";
    (order.items || []).forEach((line) => {
      const item = document.createElement("li");
      item.textContent = `${line.quantity} × ${line.item_name}`;
      items.append(item);
    });
    const footer = document.createElement("div");
    footer.className = "d-flex justify-content-between align-items-center";
    const total = document.createElement("span");
    total.className = "fw-semibold";
    total.textContent = `₹${order.total}`;
    const button = document.createElement("button");
    button.type = "button";
    button.className = "btn btn-sm btn-primary";
    button.dataset.advanceOrder = "";
    footer.append(total, button);
    body.append(heading, items, footer);
    card.append(body);
    updateCard(card, order);
    return card;
  }

  async function getOrder(id, signal) {
    const response = await fetch(`/api/orders/${id}/`, { credentials: "same-origin", signal, headers: { Accept: "application/json" } });
    if (!response.ok) throw new Error("Could not load order details.");
    return response.json();
  }

  async function fetchQueue(signal) {
    const ids = new Set();
    let next = root.dataset.endpoint;
    while (next) {
      const response = await fetch(next, { credentials: "same-origin", signal, headers: { Accept: "application/json" } });
      if (!response.ok) throw new Error("Could not refresh the order queue.");
      const page = await response.json();
      for (const order of page.results || []) {
        ids.add(String(order.id));
        let card = root.querySelector(`[data-order-id="${order.id}"]`);
        if (!card) {
          const detail = await getOrder(order.id, signal);
          card = makeCard(detail);
          root.append(card);
        } else {
          updateCard(card, order);
        }
      }
      next = page.next;
    }
    root.querySelectorAll("[data-order-id]").forEach((card) => {
      if (!ids.has(card.dataset.orderId)) card.remove();
    });
    const empty = root.querySelector("[data-empty-queue]");
    if (ids.size === 0 && !empty) {
      const notice = document.createElement("div");
      notice.className = "text-center bg-white border rounded-3 p-5";
      notice.dataset.emptyQueue = "";
      const title = document.createElement("h2");
      title.className = "h5";
      title.textContent = "Queue is clear";
      const copy = document.createElement("p");
      copy.className = "text-muted mb-0";
      copy.textContent = "New orders will appear here automatically.";
      notice.append(title, copy);
      root.append(notice);
    } else if (ids.size > 0 && empty) {
      empty.remove();
    }
  }

  async function poll() {
    if (document.hidden || controller) return;
    controller = new AbortController();
    try { await fetchQueue(controller.signal); }
    catch (error) { if (error.name !== "AbortError") console.error(error); }
    finally { controller = null; }
  }

  root.addEventListener("click", async (event) => {
    const button = event.target.closest("[data-advance-order]");
    if (!button || button.disabled) return;
    button.disabled = true;
    try {
      const response = await fetch(`/api/orders/${button.dataset.orderId}/advance/`, {
        method: "POST",
        credentials: "same-origin",
        headers: { "X-CSRFToken": csrf, Accept: "application/json" },
      });
      const data = await response.json();
      if (response.status === 409) {
        await poll();
        return;
      }
      if (!response.ok) throw new Error(data.detail || "Could not advance this order.");
      const card = root.querySelector(`[data-order-id="${data.id}"]`);
      if (card) updateCard(card, data);
      await poll();
    } catch (error) {
      console.error(error);
      button.disabled = false;
    }
  });

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
