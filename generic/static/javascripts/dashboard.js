function addModule(column, url, title, pk) {
    //create module div
    var module_head = "";
    var module_content = $("<div>").addClass('widget-content').load(url);
    var widget = $("<div>").addClass("widget").attr('id', String(pk)).appendTo("#" + column);
    var title = "<h3>" + title + "<a href='javascript:void(0)' class='close'>[X]</a></h3>";
    $("<div>").addClass("widget-head  module").append(title).appendTo(widget).append(module_content);

}
function loadModule(elem, module_name) {
    form = $('#form_' + module_name);
    form.children('.input_action').val('createmodule');
    form.children('.input_module_type').val($('#add_module').val());
    form_data = form.serializeArray();
    $.post('./', form_data, function(data, i, j) {
        $('#mod').children('.column')[0].append(data);    
    });
}

function removeDiv(elem) {
    $(elem).remove();
    sync_data();
}

function sync_data() {
    var columns = $('.column');
    var col_orders = [];
    jQuery.each(columns, function(key, value) {

        var mods = $('#' + value.id).sortable('toArray');
        jQuery.each(mods, function(k, v) {
            col_orders.push(key + '=' + v);

        });
    });
    var data = col_orders.join('&');
    $.post("/cvs/dashboard/", data);

}
$(function() {
    $('.column').sortable({
        items: '> div',
        connectWith: $('.column'),
        handle: '.widget-head',
        placeholder: 'widget-placeholder',
        forcePlaceholderSize: true,
        delay: 100,
        opacity: 0.8,
        dropOnEmpty: true,
        containment: 'document',
        start: function (e, ui) {
            $(ui.helper).addClass('dragging');
            var orig = ui.item;
        },
        stop: function (e, ui) {
            $(ui.item).css({width:''}).removeClass('dragging');
            $('.column').sortable('enable');
        },
        update: function(e, ui) {

            sync_data();
        }
    });
});

