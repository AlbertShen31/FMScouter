(function () {
  function headerFrom(target) {
    return target.closest("#rs-table th, #rs-table .dash-header");
  }

  function sortControl(header) {
    return (
      header.querySelector(".column-header--sort") ||
      header.querySelector("[class*='column-header--sort']")
    );
  }

  document.addEventListener(
    "click",
    function (event) {
      const header = headerFrom(event.target);
      if (!header) {
        return;
      }
      if (
        event.target.closest(
          "input, .column-header--select, .dash-filter, .column-header--clear"
        )
      ) {
        return;
      }
      const sort = sortControl(header);
      if (!sort) {
        return;
      }
      if (sort === event.target || sort.contains(event.target)) {
        return;
      }
      event.preventDefault();
      event.stopPropagation();
      sort.click();
    },
    true
  );
})();
