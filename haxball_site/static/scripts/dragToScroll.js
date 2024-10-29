document.addEventListener('DOMContentLoaded', () => {
    const elements = document.getElementsByClassName('draggable-container');

    for (const element of elements) {
        let element = elements[i];
        element.style.cursor = 'grab';

        let pos = { top: 0, left: 0, x: 0, y: 0 };
    
        const mouseDownHandler = (evt) => {
            element.style.cursor = 'grabbing';
            element.style.userSelect = 'none';
    
            pos = {
                left: element.scrollLeft,
                top: element.scrollTop,
                // Get the current mouse position
                x: evt.clientX,
                y: evt.clientY,
            };
    
            document.addEventListener('mousemove', mouseMoveHandler);
            document.addEventListener('mouseup', mouseUpHandler);
        };
    
        const mouseMoveHandler = (evt) => {
            // How far the mouse has been moved
            const dx = evt.clientX - pos.x;
            const dy = evt.clientY - pos.y;
    
            element.scrollTop = pos.top - dy;
            element.scrollLeft = pos.left - dx;
        };
    
        const mouseUpHandler = () => {
            element.style.cursor = 'grab';
            element.style.removeProperty('user-select');
    
            document.removeEventListener('mousemove', mouseMoveHandler);
            document.removeEventListener('mouseup', mouseUpHandler);
        };
    
        element.addEventListener('mousedown', mouseDownHandler);
    }
});