/* globals ace */
hqDefine('userreports/js/base', function() {
    $(function () {
        $('.jsonwidget').each(function () {
            var $element = $(this),
                editorElement = $element.after('<pre />').next()[0];
            $element.hide();
            var editor = ace.edit(
                editorElement,
                {
                    showPrintMargin: false,
                    maxLines: 40,
                    minLines: 3,
                    fontSize: 14,
                    wrap: true,
                    useWorker: true,
                }
            );
            editor.session.setMode('ace/mode/json');
            editor.getSession().setValue($element.val());
            editor.getSession().on('change', function(){
                $element.val(editor.getSession().getValue());
            });
        });
    });
});
