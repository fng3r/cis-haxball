$(window).on("load", function() {
    $("#exceeded_limit_modal").modal("show");
});

$(document).ready(function() {
    hideEmptyColumns($("#postponements-table"));
});

function hideEmptyColumns(table) {
    var numCols = $("th", table).length;
    // show at least 6 postponement columns (+ team column)
    for (var i=8; i<=numCols; i++) {
        var empty = true;
        //grab all the <td>'s of the column at i
        $("td:nth-child(" + i + ")", table).each(function(index, el) {
            //check if the <span> of this <td> is empty
            console.log(i);
            if (!elementIsEmpty(el)) {
                empty = false;
                return false; //break out of each() early
            }
        });
        console.log(i, empty);
        if (empty) {
            $("td:nth-child(" + i + ")", table).hide(); //hide <td>'s
            $("th:nth-child(" + i + ")", table).hide(); //hide header <th>
        }
    }
}

function elementIsEmpty(el) {
    return /^(\s|&nbsp;)*$/.test(el.innerHTML);
}
