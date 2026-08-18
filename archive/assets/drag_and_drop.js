document.addEventListener('DOMContentLoaded', () => {
    // Add drag and drop event listeners to all draggable elements
    function addDragListeners() {
        const draggables = document.querySelectorAll('.draggable');
        const droppables = document.querySelectorAll('.droppable');

        draggables.forEach(draggable => {
            draggable.addEventListener('dragstart', dragStart);
            draggable.addEventListener('dragend', dragEnd);
        });

        droppables.forEach(droppable => {
            droppable.addEventListener('dragover', dragOver);
            droppable.addEventListener('drop', drop);
        });
    }

    function dragStart(e) {
        e.dataTransfer.setData('text/plain', e.target.id);
        e.target.classList.add('dragging');
    }

    function dragEnd(e) {
        e.target.classList.remove('dragging');
    }

    function dragOver(e) {
        e.preventDefault();
        e.stopPropagation();
    }

    function drop(e) {
        e.preventDefault();
        e.stopPropagation();

        const id = e.dataTransfer.getData('text/plain');
        const draggableElement = document.getElementById(id);
        const dropZone = e.currentTarget;

        // Prevent dropping in the same container
        if (dropZone.contains(draggableElement)) return;

        // Check if the drop zone already has a child (only allow one player)
        if (dropZone.children.length > 0) {
            // Swap the draggable element with the existing child
            const existingChild = dropZone.children[0];
            const existingChildId = existingChild.id; // Store the ID of the existing child

            // Remove the existing child from its parent
            if (existingChild.parentNode) {
                existingChild.parentNode.removeChild(existingChild);
            }

            // Append the existing child to the draggable element's previous parent
            if (draggableElement.parentNode) {
                draggableElement.parentNode.appendChild(existingChild);
            }

            // Now, add the dragged element to the drop zone
            dropZone.appendChild(draggableElement);
            return; // Exit the function after swapping
        }

        // Remove from previous parent if not swapping
        if (draggableElement.parentNode) {
            draggableElement.parentNode.removeChild(draggableElement);
        }

        // Add to new parent
        dropZone.appendChild(draggableElement);
    }

    // Initial setup
    addDragListeners();

    // Optional: Re-add listeners if content changes dynamically
    const observer = new MutationObserver(addDragListeners);
    observer.observe(document.body, { 
        childList: true, 
        subtree: true 
    });
}); 