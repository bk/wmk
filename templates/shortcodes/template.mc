<%page args="template, *args, **kwargs" />\
<%
tpl = LOOKUP.get_template(template)
output = tpl.render(*args, **kwargs) or ''
%>\
${ output }\
