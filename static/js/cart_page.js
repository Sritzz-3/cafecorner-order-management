(function () {
  const form = document.querySelector("#order-cart-form");
  if (!form) return;

  const storageKey = "cafecorner-cart";
  const linesRoot = form.querySelector("[data-cart-lines]");
  const totalNode = form.querySelector("[data-cart-total]");
  const errorNode = form.querySelector("[data-cart-error]");
  const placeButton = form.querySelector("[data-place-order]");

  function readCart() {
    try { return JSON.parse(window.localStorage.getItem(storageKey) || "{}"); }
    catch (_error) { return {}; }
  }

  function writeCart(cart) {
    window.localStorage.setItem(storageKey, JSON.stringify(cart));
    const count = Object.values(cart).reduce((sum, line) => sum + Number(line.quantity || 0), 0);
    document.querySelectorAll("[data-cart-count]").forEach((badge) => { badge.textContent = String(count); });
  }

  function priceInCents(price) {
    const [whole, fraction = ""] = String(price).split(".");
    return (Number(whole) * 100) + Number((fraction + "00").slice(0, 2));
  }

  function money(cents) {
    return `₹${Math.floor(cents / 100)}.${String(cents % 100).padStart(2, "0")}`;
  }

  function render() {
    const cart = readCart();
    linesRoot.replaceChildren();
    let total = 0;
    Object.values(cart).forEach((line) => {
      const quantity = Math.max(1, Math.min(20, Number(line.quantity) || 1));
      line.quantity = quantity;
      const subtotal = priceInCents(line.price) * quantity;
      total += subtotal;

      const row = document.createElement("div");
      row.className = "d-flex align-items-center justify-content-between gap-3 border-bottom py-3";
      const description = document.createElement("div");
      const name = document.createElement("div");
      name.className = "fw-semibold";
      name.textContent = line.name;
      const price = document.createElement("div");
      price.className = "small text-muted";
      price.textContent = `${money(priceInCents(line.price))} each`;
      description.append(name, price);

      const controls = document.createElement("div");
      controls.className = "d-flex align-items-center gap-2";
      const quantityInput = document.createElement("input");
      quantityInput.className = "form-control form-control-sm";
      quantityInput.type = "number";
      quantityInput.min = "1";
      quantityInput.max = "20";
      quantityInput.value = String(quantity);
      quantityInput.setAttribute("aria-label", `Quantity for ${line.name}`);
      quantityInput.style.width = "76px";
      const remove = document.createElement("button");
      remove.type = "button";
      remove.className = "btn btn-sm btn-outline-secondary";
      remove.textContent = "Remove";
      controls.append(quantityInput, remove);
      row.append(description, controls);
      linesRoot.append(row);

      quantityInput.addEventListener("change", () => {
        const latest = readCart();
        latest[line.id].quantity = Math.max(1, Math.min(20, Number(quantityInput.value) || 1));
        writeCart(latest);
        render();
      });
      remove.addEventListener("click", () => {
        const latest = readCart();
        delete latest[line.id];
        writeCart(latest);
        render();
      });
    });
    writeCart(cart);
    totalNode.textContent = money(total);
    placeButton.disabled = Object.keys(cart).length === 0;
    if (!Object.keys(cart).length) {
      const empty = document.createElement("p");
      empty.className = "text-muted mb-0 py-3";
      empty.textContent = "Your cart is empty. Add an item from the menu to get started.";
      linesRoot.append(empty);
    }
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const cart = readCart();
    const items = Object.values(cart).map((line) => ({ menu_item_id: Number(line.id), quantity: Number(line.quantity) }));
    if (!items.length) return;

    errorNode.classList.add("d-none");
    placeButton.disabled = true;
    placeButton.textContent = "Placing order…";
    try {
      const response = await fetch("/api/orders/", {
        method: "POST",
        credentials: "same-origin",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": form.querySelector("[name=csrfmiddlewaretoken]").value,
        },
        // Only item IDs and quantities leave the browser; the server prices every line.
        body: JSON.stringify({ items }),
      });
      const data = await response.json();
      if (!response.ok) {
        const detail = data.detail || data.items || data;
        throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
      }
      window.localStorage.removeItem(storageKey);
      window.location.assign("/orders/mine/");
    } catch (error) {
      errorNode.textContent = error.message || "Could not place your order. Please try again.";
      errorNode.classList.remove("d-none");
      placeButton.disabled = false;
      placeButton.textContent = "Place order";
    }
  });

  render();
})();
