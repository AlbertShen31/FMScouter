/**
 * HTML5 drag-and-drop for Player stats league detail-level columns.
 * Publishes moves to Dash store ``st-detail-level-drop``.
 */
(function () {
  var DRAG_TYPE = "application/x-st-detail-division";

  function chipFrom(target) {
    return target && target.closest
      ? target.closest(".st-detail-level-chip[data-division]")
      : null;
  }

  function columnFrom(target) {
    return target && target.closest
      ? target.closest(".st-detail-level-column[data-level]")
      : null;
  }

  function clearDropTargets() {
    var nodes = document.querySelectorAll(".st-detail-level-column.is-drop-target");
    Array.prototype.forEach.call(nodes, function (node) {
      node.classList.remove("is-drop-target");
    });
  }

  function publishDrop(division, fromLevel, toLevel) {
    if (!division || !toLevel || fromLevel === toLevel) return;
    if (!window.dash_clientside || !dash_clientside.set_props) return;
    dash_clientside.set_props("st-detail-level-drop", {
      data: {
        division: division,
        from_level: fromLevel || "",
        to_level: toLevel,
        ts: Date.now(),
      },
    });
  }

  document.addEventListener(
    "dragstart",
    function (event) {
      var chip = chipFrom(event.target);
      if (!chip) return;
      var division = chip.getAttribute("data-division") || "";
      var fromLevel = chip.getAttribute("data-level") || "";
      if (!division) return;
      event.dataTransfer.effectAllowed = "move";
      try {
        event.dataTransfer.setData(DRAG_TYPE, division);
        event.dataTransfer.setData("text/plain", division);
      } catch (err) {
        /* IE / older Safari */
      }
      chip.classList.add("is-dragging");
      chip.setAttribute("data-from-level", fromLevel);
      document.body.classList.add("st-detail-level-dragging");
    },
    true
  );

  document.addEventListener(
    "dragend",
    function (event) {
      var chip = chipFrom(event.target);
      if (chip) {
        chip.classList.remove("is-dragging");
        chip.removeAttribute("data-from-level");
      }
      clearDropTargets();
      document.body.classList.remove("st-detail-level-dragging");
    },
    true
  );

  document.addEventListener(
    "dragover",
    function (event) {
      var column = columnFrom(event.target);
      if (!column) return;
      event.preventDefault();
      event.dataTransfer.dropEffect = "move";
      clearDropTargets();
      column.classList.add("is-drop-target");
    },
    true
  );

  document.addEventListener(
    "dragleave",
    function (event) {
      var column = columnFrom(event.target);
      if (!column) return;
      var related = event.relatedTarget;
      if (related && column.contains(related)) return;
      column.classList.remove("is-drop-target");
    },
    true
  );

  document.addEventListener(
    "drop",
    function (event) {
      var column = columnFrom(event.target);
      if (!column) return;
      event.preventDefault();
      var toLevel = column.getAttribute("data-level") || "";
      var division = "";
      try {
        division = event.dataTransfer.getData(DRAG_TYPE) || event.dataTransfer.getData("text/plain");
      } catch (err) {
        division = "";
      }
      var dragging = document.querySelector(".st-detail-level-chip.is-dragging");
      var fromLevel = dragging
        ? dragging.getAttribute("data-from-level") || dragging.getAttribute("data-level") || ""
        : "";
      if (!division && dragging) {
        division = dragging.getAttribute("data-division") || "";
      }
      clearDropTargets();
      document.body.classList.remove("st-detail-level-dragging");
      if (dragging) {
        dragging.classList.remove("is-dragging");
      }
      publishDrop(division, fromLevel, toLevel);
    },
    true
  );
})();
