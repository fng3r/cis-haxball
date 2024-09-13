$(window).on("load", function() {
    $("#exceeded_limit_modal").modal("show");
});

$(document).ready(function() {
    hideEmptyColumns($("#postponements-table"));
});

document.body.addEventListener('htmx:afterRequest', (event) => {
    hideEmptyColumns($('#postponements-table'));
})

document.body.addEventListener('htmx:afterRequest', (event) => {
    $('body').removeClass('modal-open');
    $('.modal-backdrop').remove();
})


function hideEmptyColumns(table) {
    var numCols = $("th", table).length;
    // show at least 6 postponement columns (+ team column)
    for (var i=8; i<=numCols; i++) {
        var empty = true;
        //grab all the <td>'s of the column at i
        $(`td:nth-child(${i})`, table).each(function(index, el) {
            if (!elementIsEmpty(el)) {
                empty = false;
                return false; //break out of each() early
            }
        });

        if (empty) {
            $(`td:nth-child(${i})`, table).hide();
            $(`th:nth-child(${i})`, table).hide();
        }
    }
}

function elementIsEmpty(el) {
    return /^(\s|&nbsp;)*$/.test(el.innerHTML);
}
