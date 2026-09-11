/**
 * Pointer-based depth-chart reordering.
 *
 * Rows stay put while dragging (no live DOM reshuffle → no flicker).
 * A drop line shows the insert gap; commit happens once on pointerup.
 */
(function () {
  var state = null;
  var publishTimer = null;
  var suppressClick = false;
  var DRAG_THRESHOLD_PX = 5;

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

  function collectIds(list) {
    if (!list) return [];
    return Array.prototype.map
      .call(list.querySelectorAll(".pf-depth-chart-row[data-profile-id]"), function (row) {
        return row.getAttribute("data-profile-id");
      })
      .filter(Boolean);
  }

  function sameIds(a, b) {
    if (!a || !b || a.length !== b.length) return false;
    for (var i = 0; i < a.length; i += 1) {
      if (a[i] !== b[i]) return false;
    }
    return true;
  }

  function renumber(list) {
    if (!list) return;
    var rows = list.querySelectorAll(".pf-depth-chart-row[data-profile-id]");
    Array.prototype.forEach.call(rows, function (row, index) {
      var rank = row.querySelector(".pf-depth-chart-rank");
      if (rank) {
        rank.textContent = String(index + 1);
      }
      row.classList.toggle("is-odd", index % 2 === 1);
    });
  }

  function ensureEndZone(list) {
    if (!list) return null;
    var end = list.querySelector(".pf-depth-chart-drop-end");
    if (!end) {
      end = document.createElement("div");
      end.className = "pf-depth-chart-drop-end";
      end.setAttribute("aria-hidden", "true");
      list.appendChild(end);
    } else if (end !== list.lastElementChild) {
      list.appendChild(end);
    }
    return end;
  }

  function ensureDropLine(list) {
    var line = list.querySelector(".pf-depth-chart-drop-line");
    if (!line) {
      line = document.createElement("div");
      line.className = "pf-depth-chart-drop-line";
      line.setAttribute("aria-hidden", "true");
      list.insertBefore(line, list.firstChild);
    }
    return line;
  }

  function hideDropLine(list) {
    if (!list) return;
    var line = list.querySelector(".pf-depth-chart-drop-line");
    if (line) {
      line.classList.remove("is-visible");
    }
  }

  /**
   * Insert-before node among other rows (drag row excluded from targets).
   * Returns the end-zone node to append at the bottom.
   */
  function resolveInsertBefore(list, dragRow, clientY) {
    var others = Array.prototype.filter.call(
      list.querySelectorAll(".pf-depth-chart-row[data-profile-id]"),
      function (row) {
        return row !== dragRow;
      }
    );
    for (var i = 0; i < others.length; i += 1) {
      var rect = others[i].getBoundingClientRect();
      if (clientY < rect.top + rect.height * 0.5) {
        return others[i];
      }
    }
    return ensureEndZone(list);
  }

  function placeDropLine(list, insertBefore) {
    var line = ensureDropLine(list);
    var listRect = list.getBoundingClientRect();
    var y;
    if (
      insertBefore &&
      insertBefore.classList &&
      insertBefore.classList.contains("pf-depth-chart-drop-end")
    ) {
      var rows = list.querySelectorAll(".pf-depth-chart-row[data-profile-id]");
      var last = rows.length ? rows[rows.length - 1] : null;
      if (last) {
        y = last.getBoundingClientRect().bottom - listRect.top + list.scrollTop;
      } else {
        y = list.scrollTop + 4;
      }
    } else if (insertBefore) {
      y = insertBefore.getBoundingClientRect().top - listRect.top + list.scrollTop;
    } else {
      return;
    }
    // Center the 4px line on the gap.
    line.style.top = Math.max(0, y - 2) + "px";
    line.classList.add("is-visible");
  }

  function publishOrder(list, startIds) {
    if (!list || !list.isConnected) return;
    var role = list.getAttribute("data-role") || "";
    var slot = list.getAttribute("data-slot");
    var formation = list.getAttribute("data-formation") || "";
    var ids = collectIds(list);
    if (!role || !ids.length) return;
    if (startIds && sameIds(startIds, ids)) return;

    var payload = {
      role: role,
      slot: slot,
      formation: formation,
      ids: ids,
      ts: Date.now(),
    };
    var listRef = list;

    function send() {
      // Abort if Auto-rank / refresh replaced the list after drag ended.
      if (!listRef.isConnected) {
        return true;
      }
      if (window.dash_clientside && dash_clientside.set_props) {
        dash_clientside.set_props("pf-depth-order", { data: payload });
        return true;
      }
      return false;
    }

    if (send()) return;
    if (publishTimer) clearInterval(publishTimer);
    var attempts = 0;
    publishTimer = setInterval(function () {
      attempts += 1;
      if (send() || attempts >= 40) {
        clearInterval(publishTimer);
        publishTimer = null;
      }
    }, 50);
  }

  function commitInsert(list, dragRow, insertBefore) {
    if (!list || !dragRow || !insertBefore) return;
    if (dragRow === insertBefore || dragRow.nextElementSibling === insertBefore) {
      return;
    }
    list.insertBefore(dragRow, insertBefore);
    renumber(list);
  }

  function endDrag(publish) {
    if (!state) return;
    var list = state.list;
    var row = state.row;
    var startIds = state.startIds;
    var insertBefore = state.insertBefore;
    var wasActive = !!state.active;
    try {
      if (row && state.pointerId != null) {
        row.releasePointerCapture(state.pointerId);
      }
    } catch (_err) {
      /* already released */
    }
    if (row) {
      row.classList.remove("is-dragging");
    }
    document.body.classList.remove("pf-depth-dragging");
    hideDropLine(list);
    if (publish && list && insertBefore) {
      commitInsert(list, row, insertBefore);
      publishOrder(list, startIds);
    }
    // Drop can land the pointer over another row's name button; swallow that click
    // so the scout modal does not open for the wrong player.
    if (wasActive) {
      suppressClick = true;
    }
    state = null;
  }

  document.addEventListener(
    "pointerdown",
    function (event) {
      if (event.button != null && event.button !== 0) return;
      hideTip();
      if (event.target.closest("button, a, input, textarea, select, label, .pf-depth-chart-check")) {
        return;
      }
      var row = rowFrom(event.target);
      if (!row || !row.classList.contains("is-sortable")) return;
      var list = listFrom(row);
      if (!list || list.classList.contains("pf-depth-chart-xi")) return;

      state = {
        row: row,
        list: list,
        startIds: collectIds(list),
        pointerId: event.pointerId,
        startX: event.clientX,
        startY: event.clientY,
        active: false,
        insertBefore: null,
      };
      ensureEndZone(list);
      ensureDropLine(list);
      try {
        row.setPointerCapture(event.pointerId);
      } catch (_err) {
        /* ignore */
      }
    },
    true
  );

  document.addEventListener(
    "pointermove",
    function (event) {
      if (!state || event.pointerId !== state.pointerId) return;
      var dx = event.clientX - state.startX;
      var dy = event.clientY - state.startY;
      if (!state.active) {
        if (dx * dx + dy * dy < DRAG_THRESHOLD_PX * DRAG_THRESHOLD_PX) {
          return;
        }
        state.active = true;
        hideTip();
        state.row.classList.add("is-dragging");
        document.body.classList.add("pf-depth-dragging");
      }
      event.preventDefault();

      var insertBefore = resolveInsertBefore(
        state.list,
        state.row,
        event.clientY
      );
      // Only redraw the line when the gap changes (avoids indicator chatter).
      if (insertBefore !== state.insertBefore) {
        state.insertBefore = insertBefore;
        placeDropLine(state.list, insertBefore);
      }
    },
    true
  );

  document.addEventListener(
    "pointerup",
    function (event) {
      if (!state || event.pointerId !== state.pointerId) return;
      endDrag(state.active);
    },
    true
  );

  document.addEventListener(
    "pointercancel",
    function (event) {
      if (!state || event.pointerId !== state.pointerId) return;
      endDrag(false);
    },
    true
  );

  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape" && state) {
      endDrag(false);
    }
  });

  document.addEventListener(
    "click",
    function (event) {
      if (!suppressClick) return;
      suppressClick = false;
      // Only block the ghost name-button click after a drop — never × /
      // Remove selected / checkboxes / other chrome.
      var nameBtn =
        event.target && event.target.closest
          ? event.target.closest(".pf-depth-chart-name")
          : null;
      if (!nameBtn) return;
      // Set-piece rows reuse similar styling but must stay clickable after depth drags.
      if (
        !nameBtn.closest(".pf-depth-chart-row.is-sortable[data-profile-id]")
      ) {
        return;
      }
      event.preventDefault();
      event.stopPropagation();
      if (typeof event.stopImmediatePropagation === "function") {
        event.stopImmediatePropagation();
      }
    },
    true
  );

  /* Delayed custom tips — native title attrs don't fire reliably on drag rows. */
  var tipEl = null;
  var tipTimer = null;
  var tipHost = null;
  var TIP_DELAY_MS = 350;

  function ensureTipEl() {
    if (tipEl && tipEl.isConnected) return tipEl;
    tipEl = document.createElement("div");
    tipEl.className = "pf-depth-tip";
    tipEl.setAttribute("role", "tooltip");
    tipEl.hidden = true;
    document.body.appendChild(tipEl);
    return tipEl;
  }

  function hideTip() {
    if (tipTimer) {
      clearTimeout(tipTimer);
      tipTimer = null;
    }
    tipHost = null;
    if (tipEl) {
      tipEl.hidden = true;
      tipEl.textContent = "";
    }
  }

  function placeTip(host) {
    var el = ensureTipEl();
    var text = host && host.getAttribute("data-pf-tip");
    if (!text) {
      hideTip();
      return;
    }
    el.textContent = text;
    el.hidden = false;
    var rect = host.getBoundingClientRect();
    var tipRect = el.getBoundingClientRect();
    var left = rect.left + rect.width / 2 - tipRect.width / 2;
    var top = rect.top - tipRect.height - 8;
    if (top < 8) {
      top = rect.bottom + 8;
    }
    left = Math.max(8, Math.min(left, window.innerWidth - tipRect.width - 8));
    el.style.left = Math.round(left) + "px";
    el.style.top = Math.round(top) + "px";
  }

  function tipTargetFrom(node) {
    return node && node.closest ? node.closest("[data-pf-tip]") : null;
  }

  document.addEventListener(
    "pointerover",
    function (event) {
      if (state) return;
      if (document.body.classList.contains("pf-depth-dragging")) return;
      var host = tipTargetFrom(event.target);
      if (!host || host === tipHost) return;
      hideTip();
      tipHost = host;
      tipTimer = setTimeout(function () {
        tipTimer = null;
        if (tipHost === host && !state) {
          placeTip(host);
        }
      }, TIP_DELAY_MS);
    },
    true
  );

  document.addEventListener(
    "pointerout",
    function (event) {
      var host = tipHost;
      if (!host) return;
      var next = event.relatedTarget;
      if (next && host.contains(next)) return;
      if (next === tipEl || (tipEl && tipEl.contains(next))) return;
      hideTip();
    },
    true
  );

  document.addEventListener(
    "scroll",
    function () {
      hideTip();
    },
    true
  );
})();