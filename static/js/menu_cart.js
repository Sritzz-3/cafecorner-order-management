(function () {
  const storageKey = "cafecorner-cart";

  function readCart() {
    try {
      return JSON.parse(window.localStorage.getItem(storageKey) || "{}");
    } catch (_error) {
      return {};
    }
  }

  function writeCart(cart) {
    window.localStorage.setItem(storageKey, JSON.stringify(cart));
    const count = Object.values(cart).reduce((sum, line) => sum + Number(line.quantity || 0), 0);
    document.querySelectorAll("[data-cart-count]").forEach((badge) => {
      badge.textContent = String(count);
    });
  }

  writeCart(readCart());
  document.querySelectorAll("[data-add-to-cart]").forEach((button) => {
    button.addEventListener("click", () => {
      const cart = readCart();
      const id = button.dataset.id;
      const previous = cart[id];
      const quantity = Math.min(20, Number(previous ? previous.quantity : 0) + 1);
      cart[id] = {
        id: Number(id),
        name: button.dataset.name,
        price: button.dataset.price,
        quantity,
      };
      writeCart(cart);
      const oldText = button.textContent;
      button.textContent = "Added";
      window.setTimeout(() => { button.textContent = oldText; }, 900);
    });
  });
})();
