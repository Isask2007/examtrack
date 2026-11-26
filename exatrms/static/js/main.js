/* ExamTrack UI interactions */
(function () {
  "use strict";

  document.addEventListener("DOMContentLoaded", function () {
    // Mobile sidebar
    const sidebar = document.getElementById("sidebar");
    const backdrop = document.getElementById("sidebarBackdrop");
    const toggle = document.getElementById("sidebarToggle");

    function closeSidebar() {
      if (sidebar) sidebar.classList.remove("open");
      if (backdrop) backdrop.classList.remove("show");
    }

    if (toggle) {
      toggle.addEventListener("click", function () {
        if (sidebar) sidebar.classList.toggle("open");
        if (backdrop) backdrop.classList.toggle("show");
      });
    }
    if (backdrop) backdrop.addEventListener("click", closeSidebar);
    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape") closeSidebar();
    });

    // Delete / destructive confirmations bound to hidden forms
    document.querySelectorAll("[data-confirm]").forEach(function (button) {
      button.addEventListener("click", function () {
        const message = button.dataset.confirm || "Are you sure?";
        if (!window.confirm(message)) return;
        const form = button.dataset.form
          ? document.getElementById(button.dataset.form)
          : button.closest("form");
        if (form) form.submit();
      });
    });

    // Auto-submit filter dropdowns
    document.querySelectorAll("select[data-auto-submit]").forEach(function (select) {
      select.addEventListener("change", function () {
        if (select.form) select.form.submit();
      });
    });

    // Show/hide password fields
    document.querySelectorAll(".toggle-password").forEach(function (button) {
      button.addEventListener("click", function () {
        const input = document.getElementById(button.dataset.target);
        if (!input) return;
        const show = input.type === "password";
        input.type = show ? "text" : "password";
        button.innerHTML = show ? '<i class="bi bi-eye-slash"></i>' : '<i class="bi bi-eye"></i>';
      });
    });

    // Keep mark entries inside the allowed range
    document.querySelectorAll(".mark-input").forEach(function (input) {
      input.addEventListener("input", function () {
        const max = parseFloat(input.max);
        const value = parseFloat(input.value);
        if (!Number.isNaN(max) && !Number.isNaN(value) && value > max) {
          input.setCustomValidity("Marks cannot exceed " + max + ".");
        } else {
          input.setCustomValidity("");
        }
      });
    });

    // Gentle auto-dismiss for flash messages
    document.querySelectorAll(".flash-stack .alert").forEach(function (alert) {
      window.setTimeout(function () {
        const instance = window.bootstrap && window.bootstrap.Alert
          ? window.bootstrap.Alert.getOrCreateInstance(alert)
          : null;
        if (instance) instance.close();
      }, 7000);
    });
  });
})();
