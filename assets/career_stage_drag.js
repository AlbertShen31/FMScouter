/**
 * HTML5 drag-and-drop: Careers staging cards → season mid/end slots.
 * Publishes drops to Dash store ``cr-stage-drop``.
 */
(function () {
  var DRAG_TYPE = "application/x-cr-staging-id";

  function cardFrom(target) {
    return target && target.closest
      ? target.closest(".cr-stage-card-drag[data-staging-id]")
      : null;
  }

  function slotFrom(target) {
    return target && target.closest
      ? target.closest(".cr-slot-drop[data-season-id][data-slot]")
      : null;
  }

  function clearDropTargets() {
    var nodes = document.querySelectorAll(".cr-slot-drop.is-drop-target");
    Array.prototype.forEach.call(nodes, function (node) {
      node.classList.remove("is-drop-target");
    });
  }

  function publishDrop(payload) {
    if (!payload || !payload.staging_id || !payload.season_id || !payload.slot) return;
    if (!window.dash_clientside || !dash_clientside.set_props) return;
    dash_clientside.set_props("cr-stage-drop", {
      data: {
        staging_id: payload.staging_id,
        season_id: payload.season_id,
        slot: payload.slot,
        season_label: payload.season_label || "",
        year_start: payload.year_start || null,
        year_end: payload.year_end || null,
        ts: Date.now(),
      },
    });
  }

  document.addEventListener(
    "dragstart",
    function (event) {
      var card = cardFrom(event.target);
      if (!card) return;
      var stagingId = card.getAttribute("data-staging-id") || "";
      if (!stagingId) return;
      event.dataTransfer.effectAllowed = "move";
      try {
        event.dataTransfer.setData(DRAG_TYPE, stagingId);
        event.dataTransfer.setData("text/plain", stagingId);
      } catch (err) {
        /* older browsers */
      }
      card.classList.add("is-dragging");
      document.body.classList.add("cr-stage-dragging");
    },
    true
  );

  document.addEventListener(
    "dragend",
    function (event) {
      var card = cardFrom(event.target);
      if (card) card.classList.remove("is-dragging");
      clearDropTargets();
      document.body.classList.remove("cr-stage-dragging");
    },
    true
  );

  document.addEventListener(
    "dragover",
    function (event) {
      var slot = slotFrom(event.target);
      if (!slot) return;
      event.preventDefault();
      event.dataTransfer.dropEffect = "move";
      clearDropTargets();
      slot.classList.add("is-drop-target");
    },
    true
  );

  document.addEventListener(
    "dragleave",
    function (event) {
      var slot = slotFrom(event.target);
      if (!slot) return;
      var related = event.relatedTarget;
      if (related && slot.contains(related)) return;
      slot.classList.remove("is-drop-target");
    },
    true
  );

  document.addEventListener(
    "drop",
    function (event) {
      var slot = slotFrom(event.target);
      if (!slot) return;
      event.preventDefault();
      clearDropTargets();
      document.body.classList.remove("cr-stage-dragging");

      var stagingId = "";
      try {
        stagingId =
          event.dataTransfer.getData(DRAG_TYPE) ||
          event.dataTransfer.getData("text/plain") ||
          "";
      } catch (err) {
        stagingId = "";
      }
      var dragging = document.querySelector(".cr-stage-card-drag.is-dragging");
      if (!stagingId && dragging) {
        stagingId = dragging.getAttribute("data-staging-id") || "";
      }
      if (dragging) dragging.classList.remove("is-dragging");

      publishDrop({
        staging_id: stagingId,
        season_id: slot.getAttribute("data-season-id") || "",
        slot: slot.getAttribute("data-slot") || "",
        season_label: slot.getAttribute("data-label") || "",
        year_start: slot.getAttribute("data-year-start") || null,
        year_end: slot.getAttribute("data-year-end") || null,
      });
    },
    true
  );
})();
