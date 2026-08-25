(function () {
  var dragRow = null;

  function rowFrom(target) {
    return target && target.closest
      ? target.closest(".pf-depth-chart-row[data-profile-id]")
      : null;
  }

  function listFrom(node) {
    return node && node.closest
      ? node.closest(".pf-depth-chart-list[data-role]")
      : null;
  }

  function clearDropMarks(list) {
    if (!list) return;
    list.querySelectorAll(".pf-depth-chart-row.is-drop-before, .pf-depth-chart-row.is-drop-after").forEach(function (row) {
      row.classList.remove("is-drop-before", "is-drop-after");
    });
  }

    function publishOrder(list) {
    if (!list || !window.dash_clientside || !dash_clientside.set_props) {
      return;
    }
    var role = list.getAttribute("data-role") || "";
    var slot = list.getAttribute("data-slot") || "";
    var formation = list.getAttribute("data-formation") || "";
    var ids = Array.prototype.map.call(
      list.querySelectorAll(".pf-depth-chart-row[data-profile-id]"),
      function (row) {
        return row.getAttribute("data-profile-id");
      }
    ).filter(Boolean);
    if (!role || !ids.length) {
      return;
    }
    dash_clientside.set_props("pf-depth-order", {
      data: {
        role: role,
        slot: slot,
        formation: formation,
        ids: ids,
        ts: Date.now(),
      },
    });
  }

  document.addEventListener("dragstart", function (event) {
    var row = rowFrom(event.target);
    if (!row) {
      return;
    }
    if (event.target.closest("button, a, input, textarea, select")) {
      event.preventDefault();
      return;
    }
    dragRow = row;
    row.classList.add("is-dragging");
    try {
      event.dataTransfer.effectAllowed = "move";
      event.dataTransfer.setData("text/plain", row.getAttribute("data-profile-id") || "");
    } catch (_err) {
      /* older browsers */
    }
  });

  document.addEventListener("dragend", function () {
    if (dragRow) {
      dragRow.classList.remove("is-dragging");
    }
    document.querySelectorAll(".pf-depth-chart-list").forEach(clearDropMarks);
    dragRow = null;
  });

  document.addEventListener("dragover", function (event) {
    var over = rowFrom(event.target);
    if (!dragRow || !over || over === dragRow) {
      return;
    }
    var list = listFrom(over);
    if (!list || list !== listFrom(dragRow)) {
      return;
    }
    event.preventDefault();
    try {
      event.dataTransfer.dropEffect = "move";
    } catch (_err) {
      /* ignore */
    }
    clearDropMarks(list);
    var rect = over.getBoundingClientRect();
    var before = event.clientY < rect.top + rect.height / 2;
    over.classList.add(before ? "is-drop-before" : "is-drop-after");
  });

  document.addEventListener("drop", function (event) {
    var over = rowFrom(event.target);
    if (!dragRow || !over || over === dragRow) {
      return;
    }
    var list = listFrom(over);
    if (!list || list !== listFrom(dragRow)) {
      return;
    }
    event.preventDefault();
    var rect = over.getBoundingClientRect();
    var before = event.clientY < rect.top + rect.height / 2;
    if (before) {
      list.insertBefore(dragRow, over);
    } else if (over.nextSibling) {
      list.insertBefore(dragRow, over.nextSibling);
    } else {
      list.appendChild(dragRow);
    }
    clearDropMarks(list);
    list.querySelectorAll(".pf-depth-chart-row").forEach(function (row, index) {
      var rank = row.querySelector(".pf-depth-chart-rank");
      if (rank) {
        rank.textContent = String(index + 1);
      }
      row.classList.toggle("is-odd", index % 2 === 1);
    });
    publishOrder(list);
  });
})();
