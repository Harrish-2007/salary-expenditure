/* ==========================================================================
   Salary Expenditure Management System - JavaScript
   1. Mobile sidebar   2. Confirm before delete   3. Small helpers
   4. Charts (uses Chart.js and window.chartData sent by Flask)
   ========================================================================== */

document.addEventListener("DOMContentLoaded", function () {

  /* ---------- 1. Mobile sidebar ---------- */
  var sidebar = document.getElementById("sidebar");
  var overlay = document.getElementById("overlay");
  var menuBtn = document.getElementById("menuBtn");

  function toggleSidebar(open) {
    if (!sidebar || !overlay) return;
    sidebar.classList.toggle("open", open);
    overlay.classList.toggle("show", open);
  }
  if (menuBtn) menuBtn.addEventListener("click", function () {
    toggleSidebar(!sidebar.classList.contains("open"));
  });
  if (overlay) overlay.addEventListener("click", function () { toggleSidebar(false); });

  /* ---------- 2. Ask "Are you sure?" before deleting ---------- */
  document.querySelectorAll("form[data-confirm]").forEach(function (form) {
    form.addEventListener("submit", function (event) {
      if (!window.confirm(form.getAttribute("data-confirm"))) {
        event.preventDefault();   // user pressed Cancel
      }
    });
  });

  /* ---------- 3. Small helpers ---------- */
  // Month pickers reload the page automatically when changed
  document.querySelectorAll("input[data-autosubmit]").forEach(function (input) {
    input.addEventListener("change", function () {
      if (input.value) input.form.submit();
    });
  });

  // Print button on the Reports page
  document.querySelectorAll("[data-print]").forEach(function (btn) {
    btn.addEventListener("click", function () { window.print(); });
  });

  // Success messages fade away after a few seconds
  document.querySelectorAll(".alert-success").forEach(function (box) {
    setTimeout(function () {
      box.classList.add("fade-out");
      setTimeout(function () { box.remove(); }, 700);
    }, 5000);
  });

  /* ---------- 4. Charts ---------- */
  // Chart.js is loaded from a CDN, so it needs an internet connection.
  // If it could not load, show a friendly note instead of an empty box.
  if (typeof Chart === "undefined") {
    document.querySelectorAll(".chart-box").forEach(function (box) {
      box.innerHTML = '<p class="empty">The chart could not be loaded. ' +
                      'Please check your internet connection and refresh the page.</p>';
    });
    return;
  }
  if (!window.chartData) return;

  var data = window.chartData;
  var currency = data.currency || "";

  function formatMoney(value) {
    return currency + Number(value).toLocaleString("en-IN", {
      minimumFractionDigits: 2, maximumFractionDigits: 2
    });
  }

  // Doughnut chart: spending by category
  var categoryCanvas = document.getElementById("categoryChart");
  if (categoryCanvas && data.categories && data.categories.labels.length) {
    new Chart(categoryCanvas, {
      type: "doughnut",
      data: {
        labels: data.categories.labels,
        datasets: [{
          data: data.categories.values,
          backgroundColor: data.categories.colors,
          borderWidth: 2,
          borderColor: "#ffffff"
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        cutout: "60%",
        plugins: {
          legend: { position: "bottom", labels: { usePointStyle: true, padding: 16 } },
          tooltip: {
            callbacks: {
              label: function (ctx) { return " " + ctx.label + ": " + formatMoney(ctx.parsed); }
            }
          }
        }
      }
    });
  }

  // Bar chart: expenditure for each month of the year (+ salary line)
  var monthlyCanvas = document.getElementById("monthlyChart");
  if (monthlyCanvas && data.monthly) {
    new Chart(monthlyCanvas, {
      data: {
        labels: data.monthly.labels,
        datasets: [
          {
            type: "bar",
            label: "Expenditure",
            data: data.monthly.spend,
            backgroundColor: "#6366f1",
            borderRadius: 6
          },
          {
            type: "line",
            label: "Salary",
            data: data.monthly.salary,
            borderColor: "#16a34a",
            backgroundColor: "#16a34a",
            borderDash: [6, 4],
            pointRadius: 3,
            tension: 0.2
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { position: "bottom", labels: { usePointStyle: true, padding: 16 } },
          tooltip: {
            callbacks: {
              label: function (ctx) { return " " + ctx.dataset.label + ": " + formatMoney(ctx.parsed.y); }
            }
          }
        },
        scales: {
          y: {
            beginAtZero: true,
            ticks: { callback: function (v) { return currency + Number(v).toLocaleString("en-IN"); } }
          },
          x: { grid: { display: false } }
        }
      }
    });
  }
});
